"""Complete exact read path using installed ZIPs, sealed grants and signed IPC."""
from three_mm_platform_wire import COMPATIBILITY_ACTIONS

import copy
import json
import os
from pathlib import Path
import tempfile
import threading

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.authority import CoreAuthorityGuard
from backend.db.installation_peer import InstallationPeerOutbound as Peer
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_peer_read as service
from backend.services import installation_identity as identity_service
from backend.services.application_platform import ApplicationPlatformServer
from backend.tests.test_application_peer_read_authority import (
    peer_app,
    checkpoint_app,
    managed_installed,
    source_subject,
    source_installed,
    adopt,
    review,
    decide,
    native,
    save_peer,
    store_definition,
    identity,
    LINK,
    READ,
    PRIVATE,
)
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError


pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Real POSIX review keys and Unix transport"
)


def frame(**changes):
    return {
        "version": 1,
        "request_id": "platform_" + identity(),
        "timestamp": 1,
        "instance_id": "a" * 24,
        "action": "installation.peers.read",
        "signature": "b" * 64,
        "binding_id": "remote_link",
        **changes,
    }


def call(state, **changes):
    with Session(state.engine) as db:
        return service.read_application_peer(
            db, db.get(Installation, 1), frame(**changes)
        )


@pytest.mark.parametrize("peer_app", [(1, False), (2, False), (2, True)], indirect=True)
def test_signed_sdk_review_apply_read_revoke_reapprove_without_private_or_remote_access(
    peer_app, monkeypatch
):
    import backend.database

    state = peer_app
    proof = adopt(state)
    monkeypatch.setattr(
        backend.database, "SessionLocal", sessionmaker(bind=state.engine)
    )

    def forbidden(*_args, **_kwargs):
        pytest.fail("Peer read reached identity initialization/private signing keys")

    for name in ("_cipher", "_load_or_create", "prove_installation_identity"):
        monkeypatch.setattr(identity_service, name, forbidden)
    statements = []

    def record(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement.lower())

    event.listen(state.engine, "before_cursor_execute", record)
    secret = b"s" * 32
    with tempfile.TemporaryDirectory(prefix="pr-", dir="/tmp") as temporary:
        root = Path(temporary)
        (root / ("a" * 24 + ".key")).write_bytes(secret)
        server = ApplicationPlatformServer(
            root / "p.sock", root, group="missing-fixture-group"
        , allowed_actions=COMPATIBILITY_ACTIONS)
        server.start()
        client = ApplicationPlatformClient(server.socket_path, "a" * 24, secret)
        try:
            before = state.manager.inspect(1)
            assert before["grant_effective"] and not before.get("runtime_blockers")
            value = client.read_installation_peer("remote_link")
            assert value["binding_id"] == "remote_link"
            peer = value["peer"]
            assert peer["link_id"] == LINK and peer["state"] == "active"
            assert (
                peer["consent_revision"] == 1
                and peer["receiver_identity"] == state.receiver
            )
            assert peer["remote_binding_id"] == state.peer_values["remote_binding_id"]
            assert peer["credential_expires_at"] is None
            assert peer.get("peer_version", 1) == state.wire
            assert PRIVATE not in json.dumps(value) and state.token not in json.dumps(
                value
            )
            assert not any(
                "encrypted_private_key" in query
                or "report_result" in query
                or "credential" in query
                for query in statements
            )
            for operation in (
                client.list_installation_peers,
                lambda: client.enroll_installation_peer(LINK),
                lambda: client.read_installation_peer("unknown"),
                lambda: client._call(
                    "installation.peers.read",
                    {"binding_id": "remote_link", "peer_id": LINK},
                ),
            ):
                with pytest.raises(ApplicationPlatformError):
                    operation()
            state.manager.revoke(
                1,
                actor_token=state.token,
                request_id=identity(),
                expected_revision=before["grant_record_revision"],
            )
            with pytest.raises(ApplicationPlatformError):
                client.read_installation_peer("remote_link")
            decide(state, decide(state, review(state, proof), "approve"), "apply")
            assert (
                client.read_installation_peer("remote_link")["peer"]["link_id"] == LINK
            )
            assert state.manager.inspect(1)["grant_effective"]
        finally:
            server.stop()
            event.remove(state.engine, "before_cursor_execute", record)


@pytest.mark.parametrize("stage", ["compatibility", "approved", "stopped", "empty"])
def test_no_read_before_real_apply_or_without_selected_active_right(peer_app, stage):
    state = peer_app
    if stage == "empty":
        adopt(state, scopes=[])
    elif stage != "compatibility":
        with state.engine.begin() as db:
            db.execute(update(Installation).values(enabled=False, status="disabled"))
        plan = decide(state, review(state), "approve")
        if stage == "stopped":
            decide(state, plan, "apply")
    with pytest.raises(ValueError):
        call(state)


@pytest.mark.parametrize(
    "fault",
    [
        "origin",
        "consent",
        "target",
        "revoked",
        "instance",
        "configuration",
        "epoch",
        "key",
        "recovery",
        "grant",
    ],
)
def test_actual_read_rechecks_current_resources_and_grant(peer_app, fault):
    state = peer_app
    adopt(state)
    if fault in {"origin", "consent", "target"}:
        save_peer(
            state,
            **{
                "origin": {"origin": "https://changed.example"},
                "consent": {"consent_revision": 2},
                "target": {"target_module_id": "org.example.changed"},
            }[fault],
        )
    elif fault == "key":
        state.keys.rotate(expected_key_id=state.keys.identity().key_id)
    else:
        with state.engine.begin() as db:
            if fault == "revoked":
                db.execute(update(Peer).values(state="revoked"))
            elif fault == "recovery":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            elif fault == "grant":
                db.execute(update(Grant).values(payload="{}"))
            else:
                changes = {
                    "instance": {"instance_id": "d" * 24},
                    "configuration": {
                        "configuration": {
                            **state.configuration,
                            "PRIVATE_NOTE": "changed",
                        }
                    },
                    "epoch": {"authority_epoch": identity()},
                }[fault]
                db.execute(update(Installation).values(**changes))
    with pytest.raises(ValueError, match="unavailable|not authorized"):
        call(state)


def test_subset_checks_complete_family_and_only_returns_the_selected_logical_peer(
    peer_app,
):
    state = peer_app
    save_peer(state, link_id="peer_" + "b" * 32)
    definition = state.validated.application_extension.model_dump(mode="json")
    second = copy.deepcopy(definition["peer_bindings"][0])
    second.update(binding_id="other_link", peer_id_config_key="OTHER_LINK")
    definition["peer_bindings"].append(second)
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest["configuration_schema"]["properties"]["OTHER_LINK"] = {"type": "string"}
    from backend.tests.test_application_checkpoint_authority import (
        store_checkpoint_package,
    )

    store_checkpoint_package(state, definition, manifest)
    state.configuration = {**state.configuration, "OTHER_LINK": "peer_" + "b" * 32}
    with state.engine.begin() as db:
        db.execute(update(Installation).values(configuration=state.configuration))
    adopt(state, scopes=[READ])
    assert call(state)["peer"]["link_id"] == LINK
    with pytest.raises(ValueError):
        call(state, binding_id="other_link")
    # Removing an omitted declaration's peer invalidates the whole approved set.
    with state.engine.begin() as db:
        db.execute(
            update(Peer)
            .where(Peer.link_id == state.configuration["OTHER_LINK"])
            .values(state="revoked")
        )
    with pytest.raises(ValueError):
        call(state)


@pytest.mark.parametrize(
    "changes",
    [
        {"peer_id": LINK},
        {"origin": "https://attacker.example"},
        {"version": True},
        {"action": "installation.peers.list"},
        {"binding_id": "remote_link\n"},
        {"binding_id": "*"},
        {"instance_id": "d" * 24},
    ],
)
def test_closed_request_never_accepts_caller_resource_or_wider_action(
    peer_app, changes
):
    adopt(peer_app)
    with pytest.raises(ValueError):
        call(peer_app, **changes)


def test_live_observations_are_read_without_renaming_approved_resources(peer_app):
    state = peer_app
    adopt(state)
    before = state.manager.inspect(1)
    with state.engine.begin() as db:
        db.execute(
            update(Peer).values(state="pending", remote_binding_id="peer_" + "f" * 32)
        )
    result = call(state)
    assert result["peer"]["state"] == "pending"
    assert result["peer"]["remote_binding_id"] == "peer_" + "f" * 32
    assert (
        state.manager.inspect(1)["grant_record_revision"]
        == before["grant_record_revision"]
    )


def test_peer_writer_cannot_change_the_admitted_snapshot_before_reply_commit(
    peer_app, monkeypatch
):
    state = peer_app
    adopt(state)
    admitted, finish, writer_started, writer_done = (
        threading.Event() for _ in range(4)
    )
    original = state.manager._require_grant

    def pause(*args, **kwargs):
        result = original(*args, **kwargs)
        admitted.set()
        assert finish.wait(10)
        return result

    monkeypatch.setattr(state.manager, "_require_grant", pause)
    results, failures = [], []

    def reader():
        try:
            results.append(call(state))
        except Exception as error:
            failures.append(error)

    def writer():
        try:
            writer_started.set()
            with state.engine.begin() as db:
                db.execute(update(Peer).values(state="revoked"))
            writer_done.set()
        except Exception as error:
            failures.append(error)

    reading, writing = threading.Thread(target=reader), threading.Thread(target=writer)
    reading.start()
    try:
        assert admitted.wait(10)
        writing.start()
        assert writer_started.wait(5)
        assert not writer_done.wait(0.1)
    finally:
        finish.set()
        reading.join(10)
        if writing.ident is not None:
            writing.join(10)
    assert not reading.is_alive() and not writing.is_alive() and not failures
    assert results[0]["peer"]["state"] == "active" and writer_done.is_set()
    monkeypatch.setattr(state.manager, "_require_grant", original)
    with pytest.raises(ValueError):
        call(state)


def test_committed_peer_revocation_wins_before_new_read_admission(peer_app):
    state = peer_app
    adopt(state)
    started, result = threading.Event(), []

    def reader():
        started.set()
        try:
            call(state)
            result.append("unexpected-read")
        except ValueError:
            result.append("denied")

    with state.engine.connect() as writer:
        transaction = writer.begin()
        writer.execute(update(Peer).values(state="revoked"))
        reading = threading.Thread(target=reader)
        reading.start()
        assert started.wait(5)
        transaction.commit()
    reading.join(10)
    assert not reading.is_alive() and result == ["denied"]
