"""Sealed installed v9 peer review; dedicated reader is tested separately."""
from three_mm_platform_wire import COMPATIBILITY_ACTIONS

import base64
import copy
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.db.audit_log import AuditLog
from backend.db.authority import CoreAuthorityGuard
from backend.db.base import Base
from backend.db.application_authority_grant import (
    ApplicationAuthorityAction as Action,
    ApplicationAuthorityGrant as Grant,
    ApplicationAuthorityPlan as Plan,
    ApplicationNativeReview as Native,
)
from backend.db.installation_identity import CoreInstallationIdentity
from backend.db.installation_peer import InstallationPeerOutbound as Peer
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.session import UserSession
from backend.db.user import User
from backend.services import application_authority_management as authority
from backend.services import application_authority_subjects as subjects
from backend.services import application_authority_sources as sources
from backend.services import installation_identity as identity_service
from backend.services.application_platform import ApplicationPlatformServer
from backend.services.application_authority_sources import _read_snapshot
from backend.routes.application_authority import router
from backend.utils.db_utils import get_db
from backend.tests.test_application_authority_management import identity, native, decide
from backend.tests.test_application_authority_management import (
    installed as managed_installed,
)
from backend.tests.test_application_authority_subjects import (
    installed as source_subject,
    source_installed,
)
from backend.tests.test_application_checkpoint_authority import (
    checkpoint_app,
    store_checkpoint_package,
)
from backend.tests.test_application_status_authority_context import (
    inputs as status_inputs,
)
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError
from three_mm_protocol.installation_identity import (
    InstallationIdentityV1,
    InstallationProofRequestV1,
)
from three_mm_protocol.installation_peer import (
    PEER_SCOPE,
    PeerEnrollmentStartV1,
    enrollment_resource,
    enrollment_start_bytes,
)
from three_mm_protocol.installation_peer_v2 import enrollment_metadata, peer_model
from three_mm_protocol.tests.test_application_relational_storage import (
    relational_request,
)


pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Real POSIX sealed Core key/guard"
)
LINK = "peer_" + "a" * 32
READ = "peer:remote_link:read"
PRIVATE = "PRIVATE_PEER_MUST_NOT_APPEAR"


def store_definition(state, **changes):
    definition = state.validated.application_extension.model_dump(mode="json")
    definition.update(changes)
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest["permissions"] = [
        "data.read",
        "data.write",
        "process.spawn",
        "network.outbound",
        *definition["platform_permissions"],
    ]
    store_checkpoint_package(state, definition, manifest)


def save_peer(state, **changes):
    """A real public start signed by a fixture-only sender, never a Core key read."""
    values = copy.deepcopy(state.peer_values)
    values.update(changes)
    metadata = (
        enrollment_metadata(
            "opaque_fixture_intent", values["consent"], values["consent_revision"]
        )
        if state.wire == 2
        else None
    )
    if metadata:
        values["consent"] = metadata.consent.model_dump(mode="json")
    now = datetime.now(UTC)
    sender = InstallationIdentityV1.model_validate(values["sender_identity"])
    challenge = InstallationProofRequestV1(
        challenge=base64.urlsafe_b64encode(b"c" * 32).decode().rstrip("="),
        receiver_installation_id=sender.installation_id,
        receiver_key_id=sender.key_id,
        receiver_key_generation=1,
        audience=values["origin"],
        resource=enrollment_resource(
            values["link_id"], values["target_module_id"], (PEER_SCOPE,), metadata
        ),
        created_at=now,
        expires_at=now + timedelta(seconds=60),
    )
    start = peer_model(PeerEnrollmentStartV1, state.wire)(
        request_id=values["link_id"],
        target_module_id=values["target_module_id"],
        sender=sender,
        receiver=values["receiver_identity"],
        receiver_challenge=challenge,
        signature=base64.b64encode(b"s" * 64).decode(),
        **({"enrollment_metadata": metadata} if metadata else {}),
    )
    start = start.model_copy(
        update={
            "signature": base64.b64encode(
                state.signer.sign(enrollment_start_bytes(start))
            ).decode()
        }
    )
    values["start_request"] = start.model_dump(mode="json")
    values["updated_at"] = now
    with Session(state.engine) as db, db.begin():
        row = db.get(Peer, values["link_id"])
        if row is None:
            db.add(Peer(**values))
        else:
            db.execute(
                update(Peer).where(Peer.link_id == values["link_id"]).values(**values)
            )
    state.peer_values = values


@pytest.fixture
def peer_app(checkpoint_app, request):
    state = checkpoint_app
    state.wire, mixed = getattr(request, "param", (1, False))
    state.signer = Ed25519PrivateKey.generate()
    public = state.signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    with state.engine.begin() as db:
        db.execute(
            update(CoreInstallationIdentity).values(
                public_key=base64.b64encode(public).decode(),
                key_id=hashlib.sha256(public).hexdigest(),
            )
        )
    with Session(state.engine) as db:
        state.sender = identity_service.read_existing_installation_identity(
            db
        ).model_dump(mode="json")
    state.receiver = status_inputs()[0]["status_projections"][0]["receiver_identity"]
    definition = state.validated.application_extension.model_dump(mode="json")
    definition.update(
        peer_receiver=None,
        peer_bindings=[
            {
                "contract_version": 1,
                "binding_id": "remote_link",
                "direction": "outbound",
                "peer_id_config_key": "PEER_LINK",
                "operations": ["read"],
            }
        ],
        platform_permissions=["installation.peers.enroll"],
        checkpoints=[],
    )
    if mixed:
        definition["platform_permissions"] += [
            "installation.identity.read",
            "installation.status.read",
        ]
        definition["checkpoints"] = [
            {
                "contract_version": 1,
                "checkpoint_id": "cursor",
                "mode": "read",
                "max_value_bytes": 128,
            }
        ]
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest["permissions"] = [
        "data.read",
        "data.write",
        "process.spawn",
        "network.outbound",
        *definition["platform_permissions"],
    ]
    manifest["configuration_schema"]["properties"]["PEER_LINK"] = {"type": "string"}
    store_checkpoint_package(state, definition, manifest)
    state.configuration = {**state.configuration, "PEER_LINK": LINK}
    with state.engine.begin() as db:
        db.execute(update(Installation).values(configuration=state.configuration))
    Base.metadata.create_all(state.engine, tables=[Peer.__table__])
    state.peer_values = {
        "link_id": LINK,
        "module_id": state.validated.manifest.module_id,
        "application_instance_id": "a" * 24,
        "sender_identity": state.sender,
        "receiver_identity": state.receiver,
        "origin": "https://receiver.example",
        "target_module_id": "org.example.receiver",
        "consent_revision": 1,
        "consent": {
            "consent_version": 1,
            "summary_fields": ["sdk_version", "core_version"],
            "node_ids": [],
            "node_fields": [],
        },
        "state": "active",
        "remote_binding_id": "peer_" + "d" * 32,
        "credential": {"secret": PRIVATE},
        "report_result": {"secret": PRIVATE},
        "created_at": datetime.now(UTC),
    }
    save_peer(state)
    return state


def review(state, proof=None, scopes=None, request_id=None):
    proof = proof or native(state)
    return state.manager.create_review(
        1,
        actor_token=state.token,
        request_id=request_id or identity(),
        native_review_id=proof["native_review_id"],
        scopes=state.manager.inspect(1)["scopes"] if scopes is None else scopes,
    )


def adopt(state, scopes=None):
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    proof = native(state)
    decide(state, decide(state, review(state, proof, scopes), "approve"), "apply")
    with state.engine.begin() as db:
        db.execute(
            update(Installation).values(
                enabled=True, status="active", authority_epoch=identity()
            )
        )
    decide(state, decide(state, review(state, proof, scopes), "approve"), "apply")
    return proof


def require(state, scope=READ):
    prepared = state.manager._prepare(1)
    with state.keys.locked() as key, _read_snapshot(state.engine) as db:
        return state.manager._require_grant(db, key, 1, prepared, scope)


@pytest.mark.parametrize("peer_app", [(1, False), (2, False), (2, True)], indirect=True)
def test_real_installed_source_v9_approve_is_not_apply_and_sealed_grant_is_not_runtime(
    peer_app,
):
    state = peer_app
    result = sources.resolve_installed_authority_sources(
        state.engine, 1, uploads_root=state.root, core_version="0.3.0"
    )
    assert result.sources_resolved and len(result.peer_reads) == 1
    assert not {"peer_authority_unresolved", "unsupported_scope_family"} & {
        i.reason for i in result.issues
    }
    assert result.reviewable is False and result.permission_approval == "not_evaluated"
    status = state.manager.inspect(1)
    assert status["review_available"] and READ in status["scopes"]
    assert not status["grant_effective"] and not status.get("runtime_blockers")
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    proof = native(state)
    plan = review(state, proof)
    resource = plan["resources"]["peer_reads"][0]
    assert resource["peer_id"] == LINK and resource["sender_identity"] == state.sender
    assert (
        resource["receiver_identity"] == state.receiver
        and resource["peer_version"] == state.wire
    )
    assert resource["package_artifact_sha256"] == state.validated.sha256
    assert (
        resource["service_artifact_sha256"]
        == state.validated.application_extension.service.artifact_sha256
    )
    assert resource["declaration"]["operations"] == ["read"]
    assert PRIVATE not in json.dumps(plan) and state.token not in json.dumps(plan)
    assert str(state.root) not in json.dumps(plan)
    approved = decide(state, plan, "approve")
    with Session(state.engine) as db:
        assert db.get(Grant, 1) is None
    decide(state, approved, "apply")
    grant = require(state)
    assert grant["data"]["subject"]["subject_version"] == 9
    assert grant["data"]["selection"]["selection_version"] == 9
    assert grant["data"]["policy"]["adapter_revision"] == 9
    assert not state.manager.inspect(1)["grant_effective"]  # Still stopped.
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=True, status="active"))
    assert require(state)["state"] == "active"
    assert state.manager.inspect(1)["grant_effective"] is True


def test_first_adoption_requires_actual_disabled_state(peer_app):
    state = peer_app
    plan = decide(state, review(state), "approve")
    with pytest.raises(
        authority.AuthorityManagementError, match="disabled_adoption_required"
    ):
        decide(state, plan, "apply")
    with Session(state.engine) as db:
        assert (
            db.get(Grant, 1) is None
            and db.get(Installation, 1).authority_mode == "compatibility"
        )


def test_exact_peer_subset_never_grants_other_declared_or_unconfigured_links(peer_app):
    state = peer_app
    other_id = "peer_" + "b" * 32
    save_peer(state, link_id=other_id)
    definition = state.validated.application_extension.model_dump(mode="json")
    second = copy.deepcopy(definition["peer_bindings"][0])
    second.update(binding_id="other_link", peer_id_config_key="OTHER_LINK")
    definition["peer_bindings"].append(second)
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest["configuration_schema"]["properties"]["OTHER_LINK"] = {"type": "string"}
    store_checkpoint_package(state, definition, manifest)
    state.configuration = {**state.configuration, "OTHER_LINK": other_id}
    with state.engine.begin() as db:
        db.execute(update(Installation).values(configuration=state.configuration))
    adopt(state, scopes=[READ])
    grant = require(state)
    assert len(grant["data"]["subject"]["peer_reads"]) == 2
    assert grant["data"]["selection"]["scopes"] == [READ]
    with pytest.raises(authority.AuthorityManagementError, match="grant_not_current"):
        require(state, "peer:other_link:read")
    save_peer(state, link_id="peer_" + "c" * 32)
    assert require(state)["revision"] == grant["revision"]


@pytest.mark.parametrize("peer_app", [(2, True)], indirect=True)
def test_peer_subsets_do_not_relax_older_families_required_selection(peer_app):
    with pytest.raises(
        authority.AuthorityManagementError, match="selection_not_allowed"
    ):
        review(peer_app, scopes=[READ])


def test_observations_change_without_rebinding_the_exact_approved_peer(peer_app):
    state = peer_app
    adopt(state)
    before = require(state)
    with state.engine.begin() as db:
        db.execute(
            update(Peer).values(state="pending", remote_binding_id="peer_" + "b" * 32)
        )
    after = require(state)
    assert before["revision"] == after["revision"]
    assert (
        before["data"]["subject"]["peer_reads"]
        == after["data"]["subject"]["peer_reads"]
    )
    assert state.manager.inspect(1)["grant_effective"] is True


def test_native_revocation_requires_fresh_review_and_never_restores_compatibility(
    peer_app,
):
    state = peer_app
    proof = adopt(state)
    state.manager.revoke_native_review(
        1,
        actor_token=state.token,
        request_id=identity(),
        native_review_id=proof["native_review_id"],
        expected_revision=proof["native_revision"],
    )
    status = state.manager.inspect(1)
    assert status["mode"] == "review_required" and not status["native_reviews"]
    with pytest.raises(authority.AuthorityManagementError):
        require(state)


@pytest.mark.parametrize("stage", ["approve", "apply"])
@pytest.mark.parametrize(
    "change", ["configuration", "origin", "consent", "revoked", "artifact"]
)
def test_re_resolved_peer_or_artifact_drift_invalidates_pending_decision(
    peer_app, stage, change
):
    state = peer_app
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    plan = review(state)
    if stage == "apply":
        plan = decide(state, plan, "approve")
    if change == "configuration":
        with state.engine.begin() as db:
            db.execute(
                update(Installation).values(
                    configuration={**state.configuration, "PRIVATE_NOTE": "changed"}
                )
            )
    elif change == "origin":
        save_peer(state, origin="https://changed.example")
    elif change == "consent":
        save_peer(state, consent_revision=2)
    elif change == "artifact":
        definition = state.validated.application_extension.model_dump(mode="json")
        definition["peer_bindings"][0]["binding_id"] = "new_link"
        store_definition(state, **definition)
    else:
        with state.engine.begin() as db:
            db.execute(update(Peer).values(state="revoked"))
    with pytest.raises((authority.AuthorityManagementError, ValueError)):
        decide(state, plan, stage)
    with Session(state.engine) as db:
        assert db.get(Grant, 1) is None


@pytest.mark.parametrize(
    "change",
    [
        "configuration",
        "epoch",
        "incarnation",
        "instance",
        "core_key",
        "key",
        "recovery",
        "origin",
        "consent",
        "target",
        "remote_key",
        "revoked",
        "signature",
        "grant",
        "native",
    ],
)
def test_sealed_v9_grant_rechecks_current_resources_and_trust(peer_app, change):
    state = peer_app
    adopt(state)
    assert require(state)["state"] == "active"
    if change == "key":
        state.keys.rotate(expected_key_id=state.keys.identity().key_id)
    elif change == "origin":
        save_peer(state, origin="https://changed.example")
    elif change == "consent":
        save_peer(state, consent_revision=2)
    elif change == "target":
        save_peer(state, target_module_id="org.example.changed")
    elif change == "remote_key":
        remote = copy.deepcopy(state.receiver)
        raw = b"n" * 32
        remote.update(
            public_key=base64.b64encode(raw).decode(),
            key_id=hashlib.sha256(raw).hexdigest(),
        )
        save_peer(state, receiver_identity=remote)
    else:
        with state.engine.begin() as db:
            if change == "configuration":
                db.execute(
                    update(Installation).values(
                        configuration={**state.configuration, "PRIVATE_NOTE": "changed"}
                    )
                )
            elif change in {"epoch", "incarnation", "instance"}:
                column = {
                    "epoch": "authority_epoch",
                    "incarnation": "authority_incarnation",
                    "instance": "instance_id",
                }[change]
                db.execute(
                    update(Installation).values(
                        **{
                            column: (
                                identity()[:24] if change == "instance" else identity()
                            )
                        }
                    )
                )
            elif change == "core_key":
                raw = b"z" * 32
                db.execute(
                    update(CoreInstallationIdentity).values(
                        public_key=base64.b64encode(raw).decode(),
                        key_id=hashlib.sha256(raw).hexdigest(),
                    )
                )
            elif change == "recovery":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            elif change == "revoked":
                db.execute(update(Peer).values(state="revoked"))
            elif change == "signature":
                start = copy.deepcopy(state.peer_values["start_request"])
                start["signature"] = base64.b64encode(b"x" * 64).decode()
                db.execute(update(Peer).values(start_request=start))
            else:
                db.execute(
                    update(Grant if change == "grant" else Native).values(payload="{}")
                )
    with pytest.raises((authority.AuthorityManagementError, ValueError)):
        require(state)
    assert not state.manager.inspect(1)["grant_effective"]


@pytest.mark.parametrize(
    "change", ["role", "session", "foreign_actor", "expire", "reboot"]
)
def test_current_administrator_and_boot_clock_remain_mandatory(
    peer_app, monkeypatch, change
):
    state = peer_app
    plan = review(state)
    if change in {"expire", "reboot"}:
        boot, now = authority._clock()
        monkeypatch.setattr(
            authority,
            "_clock",
            lambda: (identity() if change == "reboot" else boot, now + 900_001),
        )
    else:
        with state.engine.begin() as db:
            if change == "role":
                db.execute(update(User).where(User.id == 1).values(role="user"))
            elif change == "session":
                db.execute(
                    update(UserSession)
                    .where(UserSession.id == 1)
                    .values(is_active=False)
                )
            else:
                state.token = state.user_token
    with pytest.raises(authority.AuthorityManagementError):
        decide(state, plan, "approve")


@pytest.mark.parametrize(
    "scope",
    [
        "peer:foreign:read",
        "peer:*:read",
        "peer:remote_link:report",
        "platform:installation.identity.prove",
    ],
)
def test_scope_selection_cannot_discover_mutate_or_sign(peer_app, scope):
    with pytest.raises((authority.AuthorityManagementError, ValueError)):
        review(peer_app, scopes=[scope])


@pytest.mark.parametrize("adopted", [False, True])
def test_no_generic_peer_effect_lease_exists_even_for_authentic_applied_review(
    peer_app, adopted
):
    state = peer_app
    if adopted:
        adopt(state)
    with (
        Session(state.engine) as db,
        pytest.raises(ValueError, match="Peer reads require the dedicated adapter"),
    ):
        with authority.effect_admission(db, 1, READ):
            pytest.fail("Review metadata became a generic peer runtime lease")


def test_empty_selection_and_revocation_are_sealed_without_implicit_peer_authority(
    peer_app,
):
    state = peer_app
    adopt(state, scopes=[])
    status = state.manager.inspect(1)
    assert status["review_available"] and status["grant_state"] == "active"
    with pytest.raises(authority.AuthorityManagementError, match="grant_not_current"):
        require(state)
    state.manager.revoke(
        1,
        actor_token=state.token,
        request_id=identity(),
        expected_revision=status["grant_record_revision"],
    )
    assert state.manager.inspect(1)["grant_state"] == "revoked"
    with pytest.raises(authority.AuthorityManagementError):
        require(state)


def test_historical_apply_receipt_cannot_reapply_after_revocation(peer_app):
    state = peer_app
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    plan = decide(state, review(state), "approve")
    request_id = identity()
    applied = decide(state, plan, "apply", request_id)
    status = state.manager.inspect(1)
    state.manager.revoke(
        1,
        actor_token=state.token,
        request_id=identity(),
        expected_revision=status["grant_record_revision"],
    )
    replayed = decide(state, plan, "apply", request_id)
    assert (
        replayed["historical"]
        and replayed["replayed"]
        and replayed["grant_revision"] == applied["grant_revision"]
    )
    assert state.manager.inspect(1)["grant_state"] == "revoked"


def test_failed_audit_rolls_back_grant_mode_and_plan_together(peer_app):
    state = peer_app
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    plan = decide(state, review(state), "approve")

    def fail(*_args):
        raise ValueError("fixture audit failure")

    event.listen(AuditLog, "before_insert", fail)
    try:
        with pytest.raises(authority.AuthorityManagementError):
            decide(state, plan, "apply")
    finally:
        event.remove(AuditLog, "before_insert", fail)
    with Session(state.engine) as db:
        assert db.get(Grant, 1) is None
        assert db.get(Installation, 1).authority_mode == "compatibility"
        assert (
            json.loads(db.get(Plan, plan["plan_id"]).payload)["state"]
            == "approved_pending_apply"
        )


@pytest.mark.parametrize(
    "fault",
    [
        "extra_peer_group",
        "mutation",
        "receiver",
        "relational",
        "missing_config",
        "alias",
    ],
)
def test_unsupported_or_partial_profile_cannot_record_native_trust_or_select_supported_subset(
    peer_app, fault
):
    state = peer_app
    old_proof = native(state)
    definition = state.validated.application_extension.model_dump(mode="json")
    if fault == "extra_peer_group":
        definition["platform_permissions"].append("installation.peers.report")
    elif fault == "mutation":
        definition["peer_bindings"][0]["operations"].append("revoke")
    elif fault == "receiver":
        definition["platform_permissions"].append("installation.peers.receive")
        definition["peer_receiver"] = {
            "bootstrap_operation_id": "bootstrap",
            "report_operation_id": "report",
        }
        for op, audience in (
            ("bootstrap", "installation_bootstrap"),
            ("report", "installation_peer"),
        ):
            definition["operations"].append(
                {
                    "operation_id": op,
                    "kind": "command",
                    "audiences": [audience],
                    "idempotency": "required",
                }
            )
    elif fault == "relational":
        definition["storage"]["relational"] = relational_request(mode="read_write")
    elif fault == "alias":
        extra = copy.deepcopy(definition["peer_bindings"][0])
        extra.update(binding_id="alias", peer_id_config_key="OTHER_LINK")
        definition["peer_bindings"].append(extra)
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest["permissions"] = [
        "data.read",
        "data.write",
        "process.spawn",
        "network.outbound",
        *definition["platform_permissions"],
    ]
    if fault == "alias":
        manifest["configuration_schema"]["properties"]["OTHER_LINK"] = {
            "type": "string"
        }
    store_checkpoint_package(state, definition, manifest)
    if fault in {"missing_config", "alias"}:
        config = copy.deepcopy(state.configuration)
        if fault == "alias":
            config["OTHER_LINK"] = LINK
        else:
            config.pop("PEER_LINK")
        with state.engine.begin() as db:
            db.execute(update(Installation).values(configuration=config))
    with pytest.raises((authority.AuthorityManagementError, ValueError)):
        native(state)
    assert not state.manager.inspect(1)["review_available"]
    with pytest.raises((authority.AuthorityManagementError, ValueError)):
        review(state, old_proof, scopes=[])
    with Session(state.engine) as db:
        assert db.get(Grant, 1) is None


@pytest.mark.parametrize("peer_app", [(2, True)], indirect=True)
def test_signed_sdk_keeps_identity_status_separate_and_old_peer_access_closed(
    peer_app, monkeypatch
):
    import backend.database

    state = peer_app
    adopt(state)
    monkeypatch.setattr(
        backend.database, "SessionLocal", sessionmaker(bind=state.engine)
    )

    def forbidden(*_args, **_kwargs):
        pytest.fail("Peer review/identity/status reached private keys or execution")

    for name in ("_cipher", "_load_or_create", "prove_installation_identity"):
        monkeypatch.setattr(identity_service, name, forbidden)
    secret = b"g" * 32
    with tempfile.TemporaryDirectory(prefix="pg-", dir="/tmp") as temporary:
        root = Path(temporary)
        (root / ("a" * 24 + ".key")).write_bytes(secret)
        server = ApplicationPlatformServer(
            root / "p.sock", root, group="missing-fixture-group"
        , allowed_actions=COMPATIBILITY_ACTIONS)
        server.start()
        client = ApplicationPlatformClient(server.socket_path, "a" * 24, secret)
        try:
            assert client.get_installation_identity()["identity"] == state.sender
            assert client.get_installation_status(LINK)["consent_revision"] == 1
            for operation in (
                client.list_installation_peers,
                lambda: client.enroll_installation_peer(LINK),
            ):
                with pytest.raises(ApplicationPlatformError):
                    operation()
        finally:
            server.stop()
    with Session(state.engine) as db:
        assert db.get(Peer, LINK).state == "active"
        assert all(PRIVATE not in item.payload for item in db.scalars(select(Action)))


def test_http_exact_peer_review_apply_revoke_requires_current_administrator(peer_app):
    state = peer_app
    app = FastAPI()
    app.include_router(router)

    def database():
        with Session(state.engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    base = (
        "/api/v1/application-extensions/"
        + state.validated.manifest.module_id
        + "/authority"
    )
    headers = {"Authorization": "Bearer " + state.token}
    with TestClient(app) as client:
        assert client.get(base).status_code == 401
        assert (
            client.get(
                base, headers={"Authorization": "Bearer " + state.user_token}
            ).status_code
            == 403
        )
        proof = native(state)
        with state.engine.begin() as db:
            db.execute(update(Installation).values(enabled=False, status="disabled"))
        body = {
            "request_id": identity(),
            "native_review_id": proof["native_review_id"],
            "scopes": [READ],
        }
        for scopes in (
            ["peer:*:read"],
            ["peer:remote_link:revoke"],
            ["platform:installation.peers.enroll"],
        ):
            assert (
                client.post(
                    base + "/reviews", json={**body, "scopes": scopes}, headers=headers
                ).status_code
                == 422
            )
        assert (
            client.post(
                base + "/reviews",
                json={**body, "scopes": ["peer:unknown:read"]},
                headers=headers,
            ).status_code
            == 409
        )
        response = client.post(base + "/reviews", json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers["Cache-Control"] == "no-store"
        plan = response.json()
        assert plan["resources"]["peer_reads"][0]["peer_id"] == LINK
        decision = {
            "request_id": identity(),
            "expected_revision": plan["revision"],
            "fingerprint": plan["fingerprint"],
        }
        response = client.post(
            base + "/reviews/" + plan["plan_id"] + "/approve",
            json=decision,
            headers=headers,
        )
        assert response.status_code == 200, response.text
        approved = response.json()
        with Session(state.engine) as db:
            assert db.get(Grant, 1) is None
        decision.update(
            request_id=identity(),
            expected_revision=approved["revision"],
            fingerprint=approved["fingerprint"],
        )
        response = client.post(
            base + "/reviews/" + plan["plan_id"] + "/apply",
            json=decision,
            headers=headers,
        )
        assert response.status_code == 200, response.text
        status = client.get(base, headers=headers).json()
        assert status["grant_state"] == "active" and status["grant_effective"] is False
        assert not status.get("runtime_blockers")
        response = client.post(
            base + "/revoke",
            json={
                "request_id": identity(),
                "expected_revision": status["grant_record_revision"],
            },
            headers=headers,
        )
        assert response.status_code == 200 and response.json()["state"] == "revoked"
        assert PRIVATE not in json.dumps(status)
