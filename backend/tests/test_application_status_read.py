"""Real installed v8 grant/SDK reads, never enrollment or remote reporting."""

import copy
import json
import os
from datetime import UTC, datetime
from pathlib import Path
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.db.base import Base
from backend.db.application_authority_grant import (
    ApplicationAuthorityAction as Action,
    ApplicationAuthorityGrant as Grant,
)
from backend.db.authority import CoreAuthorityGuard
from backend.db.device import Device
from backend.db.installation_identity import CoreInstallationIdentity
from backend.db.installation_peer import InstallationPeerOutbound as Peer
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.routes.application_authority import router
from backend.services import application_status_read as service
from backend.services import installation_identity as identity_service
from backend.services.application_platform import ApplicationPlatformServer
from backend.services.application_authority_sources import _read_snapshot
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
from backend.tests.test_application_identity_authority import (
    activate_identity_grant as activate_status_grant,
)
from backend.tests.test_application_identity_authority import (
    identity_review as status_review,
)
from backend.tests.test_application_status_authority_context import inputs
from backend.utils.db_utils import get_db
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError
from three_mm_protocol.tests.test_application_private_files import file_request
from three_mm_protocol.tests.test_application_relational_storage import (
    relational_request,
)


pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Real POSIX Core review key/lease"
)
LINK = "peer_" + "a" * 32
READ = f"status:{LINK}:read"
NODE = "dev_" + "a" * 32


@pytest.fixture
def status_app(checkpoint_app, request):
    state = checkpoint_app
    mixed = getattr(request, "param", False)
    definition = state.validated.application_extension.model_dump(mode="json")
    definition.update(platform_permissions=["installation.status.read"], checkpoints=[])
    if mixed:
        definition["platform_permissions"].append("installation.identity.read")
        definition["checkpoints"] = [
            {
                "contract_version": 1,
                "checkpoint_id": "cursor",
                "mode": "read",
                "max_value_bytes": 128,
            }
        ]
        definition["storage"]["private_files"] = file_request(mode="read")
        definition["storage"]["relational"] = relational_request(mode="read_write")
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest["permissions"] = [
        "data.read",
        "data.write",
        "process.spawn",
        *definition["platform_permissions"],
    ]
    store_checkpoint_package(state, definition, manifest)
    Base.metadata.create_all(state.engine, tables=[Peer.__table__])
    with Session(state.engine) as db:
        sender = identity_service.read_existing_installation_identity(db).model_dump(
            mode="json"
        )
        receiver = inputs()[0]["status_projections"][0]["receiver_identity"]
        state.sender, state.receiver = sender, receiver
        db.add(
            Peer(
                link_id=LINK,
                module_id=state.validated.manifest.module_id,
                application_instance_id="a" * 24,
                sender_identity=sender,
                receiver_identity=receiver,
                origin="https://receiver.example",
                target_module_id="org.example.receiver",
                consent={
                    "consent_version": 1,
                    "summary_fields": ["sdk_version", "core_version"],
                    "node_ids": [NODE],
                    "node_fields": ["display_name", "online"],
                },
                consent_revision=1,
                state="active",
                credential={"secret": "PRIVATE_PEER_CREDENTIAL"},
                start_request={"private": "PRIVATE_START_REQUEST"},
                report_result={"private": "PRIVATE_REPORT"},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        device = db.scalar(select(Device).where(Device.device_id == NODE))
        if device:
            device.display_name = "Selected fixture node"
        db.commit()
    return state


def frame(**changes):
    return {
        "version": 1,
        "request_id": "platform_" + identity(),
        "timestamp": 1,
        "instance_id": "a" * 24,
        "signature": "b" * 64,
        "action": "installation.status.get",
        "link_id": LINK,
        **changes,
    }


def call(state, **changes):
    with Session(state.engine) as db:
        return service.read_application_status(
            db, db.get(Installation, 1), frame(**changes)
        )


def change_peer(fixture, **changes):
    with fixture.engine.begin() as db:
        db.execute(update(Peer).where(Peer.link_id == LINK).values(**changes))


def forbid_private(*_args, **_kwargs):
    pytest.fail(
        "Local status read tried identity initialization/signing/key decryption"
    )


@pytest.mark.parametrize("status_app", [False, True], indirect=True)
def test_review_is_exact_stopped_adoption_approve_is_not_apply_and_v8_is_sealed(
    status_app,
):
    state = status_app
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    plan = status_review(state)
    assert READ in plan["scopes"]
    resources = plan["resources"]["status_projections"]
    assert len(resources) == 1 and resources[0]["link_id"] == LINK
    assert resources[0]["sender_identity"] == state.sender
    assert resources[0]["receiver_identity"] == state.receiver
    assert resources[0]["consent"]["summary_fields"] == ["core_version", "sdk_version"]
    assert resources[0]["owner"]["application_installation_id"] == "1"
    for private in (
        state.token,
        "PRIVATE_PEER",
        "PRIVATE_START",
        "PRIVATE_REPORT",
        str(state.root),
    ):
        assert private not in json.dumps(plan)
    approved = decide(state, plan, "approve")
    with Session(state.engine) as db:
        assert db.get(Grant, 1) is None
    with pytest.raises(ValueError):
        call(state)
    decide(state, approved, "apply")
    with state.keys.locked() as key, _read_snapshot(state.engine) as db:
        value = state.manager._require_grant(
            db, key, 1, state.manager._prepare(1), READ
        )
        assert value["data"]["subject"]["subject_version"] == 8
        assert value["data"]["selection"]["selection_version"] == 8
    assert state.manager.inspect(1)["grant_effective"] is False


def test_runtime_returns_only_selected_public_projection_without_key_or_private_sql(
    status_app, monkeypatch
):
    state = status_app
    activate_status_grant(state)
    monkeypatch.delenv("AI_SETTINGS_MASTER_KEY", raising=False)
    for name in (
        "_cipher",
        "_load_or_create",
        "_decode_identity",
        "prove_installation_identity",
    ):
        monkeypatch.setattr(identity_service, name, forbid_private)
    queries = []

    def observe(_connection, _cursor, sql, _parameters, _context, _many):
        queries.append(sql.lower())

    with Session(state.engine) as db:
        before = {row.request_id: row.payload for row in db.scalars(select(Action))}
    event.listen(state.engine, "before_cursor_execute", observe)
    try:
        result = call(state)
    finally:
        event.remove(state.engine, "before_cursor_execute", observe)
    assert result["installation_id"] == state.sender["installation_id"]
    assert set(result) == {
        "projection_version",
        "installation_id",
        "consent_revision",
        "generated_at",
        "summary",
        "nodes",
    }
    assert tuple(result["summary"]) == (
        "sdk_version",
        "core_version",
    )  # Existing SDK order retained.
    assert len(result["nodes"]) == 1 and result["nodes"][0]["device_id"] == NODE
    assert set(result["nodes"][0]["fields"]) == {"display_name", "online"}
    assert "PRIVATE" not in json.dumps(result)
    for sql in queries:
        if "from installation_peer_outbound" in sql:
            assert all(
                field not in sql
                for field in (
                    "credential",
                    "start_request",
                    "report_result",
                    "report_projection",
                )
            )
        if "from core_installation_identity" in sql:
            assert "encrypted_private_key" not in sql
    with Session(state.engine) as db:
        assert {
            row.request_id: row.payload for row in db.scalars(select(Action))
        } == before


@pytest.mark.parametrize(
    "change",
    [
        "revoke",
        "disabled",
        "native",
        "key",
        "recovery",
        "configuration",
        "incarnation",
        "artifact",
        "sender",
        "receiver",
        "origin",
        "target",
        "revision",
        "fields",
        "withdraw",
        "instance",
    ],
)
def test_stale_or_revoked_rights_never_admit_a_projection(
    status_app, monkeypatch, change
):
    state = status_app
    activate_status_grant(state)
    if change == "revoke":
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=state.manager.inspect(1)["grant_record_revision"],
        )
    elif change == "native":
        proof = state.manager.inspect(1)["native_reviews"][0]
        state.manager.revoke_native_review(
            1,
            actor_token=state.token,
            request_id=identity(),
            native_review_id=proof["native_review_id"],
            expected_revision=proof["revision"],
        )
    elif change == "key":
        state.keys.rotate(expected_key_id=state.keys.identity().key_id)
    elif change == "artifact":
        definition = state.validated.application_extension.model_dump(mode="json")
        definition["operations"][0]["timeout_seconds"] += 1
        store_checkpoint_package(state, definition)
    elif change in {"disabled", "recovery", "configuration", "incarnation", "sender"}:
        with state.engine.begin() as db:
            if change == "recovery":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            elif change == "sender":
                db.execute(
                    update(CoreInstallationIdentity).values(
                        created_at=datetime(2026, 1, 1, tzinfo=UTC)
                    )
                )
            else:
                db.execute(
                    update(Installation).values(
                        **{
                            "disabled": {"enabled": False, "status": "disabled"},
                            "configuration": {
                                "configuration": {
                                    **state.configuration,
                                    "PRIVATE_NOTE": "changed",
                                }
                            },
                            "incarnation": {"authority_incarnation": identity()},
                        }[change]
                    )
                )
    else:
        changes = {
            "receiver": {
                "receiver_identity": {
                    **state.receiver,
                    "installation_id": "inst_" + "9" * 32,
                }
            },
            "origin": {"origin": "https://new.example"},
            "target": {"target_module_id": "org.example.other"},
            "revision": {"consent_revision": 2},
            "fields": {"consent": {"summary_fields": ["core_version"]}},
            "withdraw": {"state": "revoked"},
            "instance": {"application_instance_id": "b" * 24},
        }[change]
        change_peer(state, **changes)
    monkeypatch.setattr(
        service,
        "bound_installation_projection",
        lambda *_args, **_kwargs: pytest.fail("Stale grant reached data projection"),
    )
    with pytest.raises(ValueError):
        call(state)


@pytest.mark.parametrize(
    "changes",
    [
        {"link_id": "peer_" + "b" * 32},
        {"link_id": "all"},
        {"version": True},
        {"instance_id": "b" * 24},
        {"owner": "foreign"},
        {"origin": "https://caller.example"},
        {"consent": {}},
        {"receiver_identity": {}},
        {"proof_request": {}},
        {"node_ids": [NODE]},
    ],
)
def test_request_cannot_select_wider_status_or_replace_reviewed_public_pins(
    status_app, changes
):
    activate_status_grant(status_app)
    with pytest.raises(ValueError):
        call(status_app, **changes)


@pytest.mark.parametrize(
    "problem", ["absent", "withdrawn", "foreign", "corrupt", "too_many"]
)
def test_missing_or_unresolved_bindings_cannot_approve_a_partial_subject(
    status_app, problem
):
    state = status_app
    if problem in {"absent", "too_many"}:
        with Session(state.engine) as db:
            if problem == "absent":
                db.execute(delete(Peer))
            else:
                row = db.get(Peer, LINK)
                values = {
                    column.name: getattr(row, column.name)
                    for column in Peer.__table__.c
                    if column.name != "link_id"
                }
                for index in range(32):
                    db.add(
                        Peer(link_id="peer_" + f"{index:032x}", **copy.deepcopy(values))
                    )
            db.commit()
    else:
        change_peer(
            state,
            **{
                "withdrawn": {"state": "revoked"},
                "foreign": {"module_id": "org.example.foreign"},
                "corrupt": {
                    "receiver_identity": {**state.receiver, "key_id": "0" * 64}
                },
            }[problem],
        )
    status = state.manager.inspect(1)
    assert (
        not status["review_available"]
        and not status["grant_effective"]
        and status["scopes"] == []
    )
    with pytest.raises(ValueError):
        call(state)


def test_metadata_reorder_is_not_a_wider_permission_and_new_links_need_fresh_review(
    status_app,
):
    state = status_app
    activate_status_grant(state)
    with Session(state.engine) as db:
        row = db.get(Peer, LINK)
        consent = copy.deepcopy(row.consent)
        consent["summary_fields"].reverse()
    change_peer(state, consent=consent)
    assert call(state)["consent_revision"] == 1
    with Session(state.engine) as db:
        row = db.get(Peer, LINK)
        values = {
            column.name: getattr(row, column.name)
            for column in Peer.__table__.c
            if column.name != "link_id"
        }
        db.add(Peer(link_id="peer_" + "b" * 32, **copy.deepcopy(values)))
        db.commit()
    assert state.manager.inspect(1)["grant_effective"] is False
    with pytest.raises(ValueError):
        call(state)


def test_revocation_between_package_preflight_and_admission_wins(
    status_app, monkeypatch
):
    state = status_app
    activate_status_grant(state)
    revision = state.manager.inspect(1)["grant_record_revision"]
    original = state.manager._prepare

    def interleave(installation_id):
        prepared = original(installation_id)
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=revision,
        )
        return prepared

    monkeypatch.setattr(state.manager, "_prepare", interleave)
    with pytest.raises(ValueError):
        call(state)


def test_row_binding_is_rechecked_after_grant_resolution_before_serialization(
    status_app, monkeypatch
):
    state = status_app
    activate_status_grant(state)
    original = service.bound_installation_projection
    checked = []

    def interleave(db, application, expected):
        # Deterministic same-transaction seam: no second SQLite writer can
        # enter while the Core guard is locked. Actual row-lock tests are separate.
        db.execute(update(Peer).where(Peer.link_id == LINK).values(consent_revision=2))
        try:
            return original(db, application, expected)
        except ValueError as exc:
            assert "binding changed" in str(exc)
            checked.append(True)
            raise

    monkeypatch.setattr(service, "bound_installation_projection", interleave)
    with pytest.raises(ValueError, match="unavailable or stale"):
        call(state)
    assert checked == [True]
    with Session(state.engine) as db:
        assert db.get(Peer, LINK).consent_revision == 1


def test_status_read_grant_does_not_authorize_identity_proof_peer_or_reporting(
    status_app,
):
    state = status_app
    activate_status_grant(state)
    for action in (
        "installation.identity.get",
        "installation.identity.prove",
        "installation.peers.list",
        "installation.peers.enroll",
        "installation.peers.rotate",
        "installation.peers.approve",
        "installation.peers.report",
    ):
        request = frame(action=action)
        if action == "installation.identity.get":
            request.pop("link_id")
        with Session(state.engine) as db, pytest.raises(ValueError):
            ApplicationPlatformServer(None, None)._dispatch(
                db, db.get(Installation, 1), request
            )


def test_legacy_sdk_status_is_compatible_but_cannot_opt_in_to_v8_implicitly(status_app):
    state = status_app
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["service"]["sdk_version"] = "1.2"
    store_checkpoint_package(state, definition)
    assert state.manager.inspect(1)["review_available"] is False
    with Session(state.engine) as db:
        result = ApplicationPlatformServer(None, None)._dispatch(
            db, db.get(Installation, 1), frame()
        )
    assert result["installation_id"] == state.sender["installation_id"]


@pytest.mark.parametrize("status_app", [True], indirect=True)
def test_mixed_v8_start_consent_and_other_read_adapters_keep_separate_boundaries(
    status_app,
):
    from backend.services.application_identity_read import read_application_identity
    from backend.services.application_relational_activation import _start_consent

    state = status_app
    activate_status_grant(state)
    assert call(state)["consent_revision"] == 1
    with Session(state.engine) as db:
        identity_frame = frame(action="installation.identity.get")
        identity_frame.pop("link_id")
        assert (
            read_application_identity(db, db.get(Installation, 1), identity_frame)[
                "identity"
            ]
            == state.sender
        )
    prepared = state.manager._prepare(1)
    with state.keys.locked() as key, Session(state.engine) as db:
        grant = state.manager._require_grant(db, key, 1, prepared, READ)
        assert (
            _start_consent(
                state.manager,
                db,
                key,
                1,
                prepared,
                {"grant_record_revision": grant["revision"]},
            )[1].service.sdk_version
            == "1.3"
        )
    assert state.manager.inspect(1)["runtime_blockers"] == [
        "relational_runtime_unavailable"
    ]


def test_http_review_requires_admin_and_refuses_wildcard_or_unresolved_links(
    status_app,
):
    state = status_app
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
    with TestClient(app) as client:
        assert client.get(base).status_code == 401
        assert (
            client.get(
                base, headers={"Authorization": "Bearer " + state.user_token}
            ).status_code
            == 403
        )
        proof = native(state)
        body = {
            "request_id": identity(),
            "native_review_id": proof["native_review_id"],
            "scopes": [READ],
        }
        headers = {"Authorization": "Bearer " + state.token}
        assert (
            client.post(
                base + "/reviews",
                json={**body, "scopes": ["platform:installation.status.read"]},
                headers=headers,
            ).status_code
            == 422
        )
        assert (
            client.post(
                base + "/reviews",
                json={**body, "scopes": ["status:peer_" + "b" * 32 + ":read"]},
                headers=headers,
            ).status_code
            == 409
        )
        response = client.post(base + "/reviews", json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["resources"]["status_projections"][0]["link_id"] == LINK


def test_real_signed_sdk_uses_current_v8_grant_and_never_implicit_retry(
    status_app, monkeypatch
):
    import backend.database

    state = status_app
    activate_status_grant(state)
    monkeypatch.setattr(
        backend.database, "SessionLocal", sessionmaker(bind=state.engine)
    )
    monkeypatch.setattr(identity_service, "_cipher", forbid_private)
    monkeypatch.setattr(identity_service, "_load_or_create", forbid_private)
    secret = b"x" * 32
    with tempfile.TemporaryDirectory(prefix="sr-", dir="/tmp") as directory:
        root = Path(directory)
        (root / ("a" * 24 + ".key")).write_bytes(secret)
        server = ApplicationPlatformServer(
            root / "p.sock", root, group="missing-fixture-group"
        )
        server.start()
        client = ApplicationPlatformClient(server.socket_path, "a" * 24, secret)
        try:
            assert client.get_installation_status(LINK)["consent_revision"] == 1
            forged = ApplicationPlatformClient(server.socket_path, "a" * 24, b"y" * 32)
            with pytest.raises(
                ApplicationPlatformError, match="response signature is invalid"
            ):
                forged.get_installation_status(LINK)
            state.manager.revoke(
                1,
                actor_token=state.token,
                request_id=identity(),
                expected_revision=state.manager.inspect(1)["grant_record_revision"],
            )
            with pytest.raises(ApplicationPlatformError):
                client.get_installation_status(LINK)
        finally:
            server.stop()
