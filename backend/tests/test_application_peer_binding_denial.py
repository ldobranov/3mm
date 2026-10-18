"""New exact declarations cannot inherit legacy peers/signing at either Core."""

import copy
import os
from pathlib import Path
import tempfile

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.installation_peer import (
    InstallationPeerInbound,
    InstallationPeerOutbound,
)
from backend.db.module import (
    ApplicationExtensionInstallation as Installation,
    ModulePackage,
)
from backend.services import installation_peers as peers
from backend.services import installation_identity as identities
from backend.services.application_platform import ApplicationPlatformServer
from backend.services.module_packages import validate_module_package
import backend.database
from backend.tests.test_installation_peers import (
    pair,
    activate_pair,
    MODULE,
    ORIGIN,
)
from backend.tests.test_module_packages import application_package
from three_mm_protocol.tests.test_application_peer_bindings import peer_request
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError


def opt_in(pair):
    definition = copy.deepcopy(pair.definition)
    manifest = copy.deepcopy(pair.manifest)
    definition["service"]["sdk_version"] = "1.3"
    definition["platform_permissions"] += [
        "installation.identity.read",
        "installation.identity.prove",
    ]
    definition["peer_bindings"] = [peer_request(operations=["read"])]
    manifest["permissions"] += [
        "installation.identity.read",
        "installation.identity.prove",
    ]
    manifest["configuration_schema"]["properties"]["PEER_LINK"] = {"type": "string"}
    blob = application_package(definition=definition, manifest_value=manifest)
    package = validate_module_package(blob)
    pair.package_path.write_bytes(blob)
    for core in (pair.sender, pair.receiver):
        with core.engine.begin() as db:
            db.execute(
                update(ModulePackage).values(
                    manifest=manifest, sha256=package.sha256, size_bytes=len(blob)
                )
            )


def forbid_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail(
            "Unimplemented peer declaration reached a key, network, audit or extension effect"
        )

    for name in (
        "_load_or_create",
        "prove_installation_identity",
        "peer_http",
        "_audit",
        "_issue",
        "invoke_application",
    ):
        monkeypatch.setattr(peers, name, forbidden)
    monkeypatch.setattr(identities, "prove_installation_identity", forbidden)


@pytest.mark.parametrize("mode", ["compatibility", "review_required", "enforced"])
@pytest.mark.parametrize(
    "action",
    [
        "installation.peers.list",
        "installation.peers.capabilities",
        "installation.peers.enroll",
        "installation.peers.rotate",
        "installation.peers.approve",
        "installation.peers.revoke",
        "installation.peers.report",
        "installation.identity.prove",
    ],
)
def test_all_platform_peer_actions_and_generic_proof_stay_denied_without_fallback(
    pair, monkeypatch, tmp_path, mode, action
):
    opt_in(pair)
    forbid_effects(monkeypatch)
    with pair.sender.engine.begin() as db:
        db.execute(update(Installation).values(authority_mode=mode))
    server = ApplicationPlatformServer(tmp_path / "unused.sock", tmp_path)
    with Session(pair.sender.engine) as db:
        application = db.scalar(select(Installation))
        with pytest.raises(
            (ValueError, peers.InstallationPeerError),
            match="not implemented|no supported resource grant|do not authorize",
        ):
            server._dispatch(
                db,
                application,
                {
                    "action": action,
                    "link_id": pair.sender.link_id,
                    "binding_id": "peer_" + "f" * 32,
                    "peer_id": pair.sender.link_id,
                    "direction": "outbound",
                    "expected_generation": 1,
                },
            )


@pytest.mark.parametrize("operation", ["enroll", "rotate", "report", "receiver"])
def test_direct_core_flows_refuse_opt_in_before_keys_network_or_durable_peer_changes(
    pair, monkeypatch, operation
):
    binding_id = activate_pair(pair)
    with Session(pair.sender.engine) as db:
        outbound = copy.deepcopy(
            db.get(InstallationPeerOutbound, pair.sender.link_id).credential
        )
    opt_in(pair)
    forbid_effects(monkeypatch)
    core = pair.receiver if operation == "receiver" else pair.sender
    with Session(core.engine) as db:
        application = db.scalar(select(Installation))
        with pytest.raises(peers.InstallationPeerError, match="not implemented"):
            if operation == "receiver":
                peers.approve_inbound(db, application, binding_id, 1)
            elif operation == "report":
                peers.report_outbound(
                    db, application, pair.sender.link_id, "report_" + "b" * 32
                )
            else:
                getattr(peers, operation + "_outbound")(
                    db, application, pair.sender.link_id
                )
        db.rollback()
    with Session(pair.sender.engine) as db:
        row = db.get(InstallationPeerOutbound, pair.sender.link_id)
        assert row.state == "active" and row.credential == outbound
        assert row.rotation_request is None and row.report_id is None
    with Session(pair.receiver.engine) as db:
        row = db.get(InstallationPeerInbound, binding_id)
        assert row.state == "active" and row.generation == 1


def test_incoming_bootstrap_cannot_use_the_legacy_receiver_when_exact_requests_are_declared(
    pair, monkeypatch
):
    with Session(pair.sender.engine) as db:
        start = copy.deepcopy(
            db.get(InstallationPeerOutbound, pair.sender.link_id).start_request
        )
    opt_in(pair)
    forbid_effects(monkeypatch)
    with Session(pair.receiver.engine) as db:
        with pytest.raises(peers.InstallationPeerError, match="not implemented"):
            peers.enrollment_start(db, start, origin=ORIGIN)
        assert db.scalar(select(InstallationPeerInbound)) is None


def test_explicit_human_cleanup_remains_available_and_preserves_tombstones(pair):
    opt_in(pair)
    with Session(pair.sender.engine) as db:
        application = db.scalar(select(Installation))
        assert (
            peers.revoke_peer(
                db, application, pair.sender.link_id, "outbound", user_id=1
            )["state"]
            == "revoked"
        )
        assert db.get(InstallationPeerOutbound, pair.sender.link_id).state == "revoked"


@pytest.mark.skipif(os.name != "posix", reason="Real local signed Unix transport")
def test_signed_sdk_transport_refuses_new_peer_contract_before_legacy_effects(
    pair, monkeypatch
):
    opt_in(pair)
    forbid_effects(monkeypatch)
    monkeypatch.setattr(
        backend.database, "SessionLocal", lambda: Session(pair.sender.engine)
    )
    with tempfile.TemporaryDirectory(prefix="peer-binding-") as temporary:
        root = Path(temporary)
        secret = b"s" * 32
        (root / ("a" * 24 + ".key")).write_bytes(secret)
        server = ApplicationPlatformServer(root / "platform.sock", root)
        server.start()
        try:
            client = ApplicationPlatformClient(server.socket_path, "a" * 24, secret)
            with pytest.raises(ApplicationPlatformError, match="not implemented"):
                client.list_installation_peers()
            with pytest.raises(ApplicationPlatformError, match="not implemented"):
                client.enroll_installation_peer(pair.sender.link_id)
        finally:
            server.stop()
