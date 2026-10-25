"""Real scoped identity reads, exact public pin and authenticated SDK transport."""
from three_mm_platform_wire import COMPATIBILITY_ACTIONS

import json
import os
from pathlib import Path
import tempfile
from contextlib import ExitStack
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, event, select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.authority import CoreAuthorityGuard
from backend.db.installation_identity import CoreInstallationIdentity as CoreIdentity
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import installation_identity as identity_service
from backend.services.application_identity_read import read_application_identity
from backend.services.application_platform import ApplicationPlatformServer
from backend.tests.test_application_authority_management import (
    identity, installed as managed_installed,
)
from backend.tests.test_application_authority_subjects import installed as source_subject
from backend.tests.test_application_authority_subjects import source_installed
from backend.tests.test_application_checkpoint_authority import checkpoint_app
from backend.tests.test_application_identity_authority import (
    identity_app, activate_identity_grant,
)
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError
from three_mm_protocol.diagnostics import DiagnosticSession


pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real POSIX review key/guard")


def frame(**changes):
    return {
        "version": 1, "request_id": "platform_" + identity(), "timestamp": 1,
        "instance_id": "a" * 24, "signature": "b" * 64,
        "action": "installation.identity.get", **changes,
    }


def call(state, **changes):
    with Session(state.engine) as db:
        return read_application_identity(db, db.get(Installation, 1), frame(**changes))


def forbid_private_identity(*_args, **_kwargs):
    pytest.fail("Scoped public read attempted identity initialization/private-key use")


def test_read_returns_reviewed_public_binding_without_crypto_identity_write_or_audit(identity_app, monkeypatch):
    state = identity_app
    activate_identity_grant(state)
    monkeypatch.delenv("AI_SETTINGS_MASTER_KEY", raising=False)
    for name in ("_cipher", "_load_or_create", "_decode_identity", "installation_identity", "prove_installation_identity"):
        monkeypatch.setattr(identity_service, name, forbid_private_identity)
    with Session(state.engine) as db:
        before = {row.request_id: row.payload for row in db.scalars(select(Action))}
    statements = []

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if "core_installation_identity" in statement.lower():
            statements.append(statement)

    event.listen(state.engine, "before_cursor_execute", observe)
    try:
        first = call(state)
        assert call(state) == first
    finally:
        event.remove(state.engine, "before_cursor_execute", observe)
    public = first["identity"]
    assert set(public) == {"identity_version", "algorithm", "installation_id", "key_id", "public_key", "key_generation", "created_at"}
    assert public["installation_id"] == "inst_" + "5" * 32
    assert first["sdk_version"] == "1.3"
    assert statements and all(sql.lstrip().upper().startswith("SELECT") for sql in statements)
    assert all("encrypted_private_key" not in sql for sql in statements)
    assert "PRIVATE_MUST_NOT_APPEAR" not in json.dumps(first)
    with Session(state.engine) as db:
        assert {row.request_id: row.payload for row in db.scalars(select(Action))} == before


@pytest.mark.parametrize("change", ["revoke", "disabled", "review_required", "configuration", "incarnation", "recovery", "review_key", "missing", "corrupt", "public_drift"])
def test_no_read_with_revoked_stale_inactive_or_changed_identity(identity_app, monkeypatch, change):
    state = identity_app
    activate_identity_grant(state)
    if change == "revoke":
        state.manager.revoke(1, actor_token=state.token, request_id=identity(),
            expected_revision=state.manager.inspect(1)["grant_record_revision"])
    elif change == "review_key":
        state.keys.rotate(expected_key_id=state.keys.identity().key_id)
    else:
        with state.engine.begin() as db:
            if change == "missing":
                db.execute(delete(CoreIdentity))
            elif change == "corrupt":
                db.execute(update(CoreIdentity).values(key_id="f" * 64))
            elif change == "public_drift":
                db.execute(update(CoreIdentity).values(created_at=datetime(2025, 1, 1, tzinfo=UTC)))
            elif change == "recovery":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            else:
                values = {
                    "disabled": {"enabled": False, "status": "disabled"},
                    "review_required": {"authority_mode": "review_required"},
                    "configuration": {"configuration": {**state.configuration, "PRIVATE_NOTE": "changed"}},
                    "incarnation": {"authority_incarnation": identity()},
                }[change]
                db.execute(update(Installation).values(**values))
    monkeypatch.setattr(identity_service, "_load_or_create", forbid_private_identity)
    with pytest.raises(ValueError):
        call(state)
    if change == "missing":
        with Session(state.engine) as db:
            assert db.scalar(select(CoreIdentity.singleton_id)) is None


@pytest.mark.parametrize("changes", [
    {"owner": "foreign"}, {"installation_id": "inst_" + "f" * 32},
    {"path": "/private"}, {"proof_request": {}}, {"version": True},
    {"public_key": "caller"}, {"instance_id": "f" * 24},
])
def test_extra_or_foreign_transport_metadata_does_not_select_a_public_identity(identity_app, changes):
    activate_identity_grant(identity_app)
    with pytest.raises(ValueError):
        call(identity_app, **changes)


@pytest.mark.parametrize("action", [
    "installation.identity.prove", "installation.status.get", "installation.peers.enroll",
    "installation.peers.list", "installation.peers.approve", "installation.peers.report",
])
def test_read_grant_does_not_admit_signing_status_or_peer_operations(identity_app, action):
    activate_identity_grant(identity_app)
    request = frame(action=action, **({"link_id": "peer_" + "a" * 32} if action == "installation.status.get" else {}))
    reason = "unavailable or stale" if action == "installation.status.get" else "no supported resource grant"
    with Session(identity_app.engine) as db, pytest.raises(ValueError, match=reason):
        ApplicationPlatformServer(None, None, allowed_actions=COMPATIBILITY_ACTIONS)._dispatch(db, db.get(Installation, 1), request)


def test_scoped_helper_refuses_compatibility_instead_of_initializing_a_key(identity_app, monkeypatch):
    monkeypatch.setattr(identity_service, "_load_or_create", forbid_private_identity)
    with pytest.raises(ValueError, match="Scoped installation identity read is unavailable"):
        call(identity_app)


@pytest.mark.parametrize("identity_app", [("1.3", True)], indirect=True)
def test_mixed_identity_and_checkpoint_reads_use_v7_without_repairing_sql(identity_app, monkeypatch):
    state = identity_app
    activate_identity_grant(state)
    monkeypatch.setattr(identity_service, "_load_or_create", forbid_private_identity)
    assert call(state)["identity"]["installation_id"] == "inst_" + "5" * 32
    with Session(state.engine) as db:
        result = ApplicationPlatformServer(None, None, allowed_actions=COMPATIBILITY_ACTIONS)._dispatch(
            db, db.get(Installation, 1), frame(action="checkpoint.get", checkpoint_id="catalog"),
        )
    assert result == {"checkpoint_id": "catalog", "revision": 0, "value": {}}
    # Public/checkpoint reads neither prepare the separately protected SQL
    # runtime nor turn its conservative generic status into an effective grant.
    assert state.manager.inspect(1)["runtime_blockers"] == ["relational_runtime_unavailable"]


@pytest.mark.parametrize("pending", ["dirty", "new", "nested"])
def test_scoped_read_never_flushes_or_discards_caller_changes(identity_app, pending):
    activate_identity_grant(identity_app)
    with Session(identity_app.engine) as db:
        app = db.get(Installation, 1)
        if pending == "dirty":
            app.configuration = {"caller": "not saved"}
        elif pending == "new":
            db.add(CoreIdentity(singleton_id=2))
        else:
            db.begin_nested()
        with pytest.raises(ValueError, match="clean session"):
            read_application_identity(db, app, frame())
        assert bool(db.dirty or db.new or db.in_nested_transaction())


def test_revocation_after_package_preflight_is_observed_before_public_read(identity_app, monkeypatch):
    state = identity_app
    activate_identity_grant(state)
    status = state.manager.inspect(1)
    prepare = state.manager._prepare

    def interleave(installation_id):
        prepared = prepare(installation_id)
        state.manager.revoke(1, actor_token=state.token, request_id=identity(),
            expected_revision=status["grant_record_revision"])
        return prepared

    monkeypatch.setattr(state.manager, "_prepare", interleave)
    with pytest.raises(ValueError):
        call(state)


def test_real_signed_sdk_read_has_no_private_key_dependency_or_implicit_retry(identity_app, monkeypatch):
    import backend.database

    state = identity_app
    activate_identity_grant(state)
    monkeypatch.setattr(backend.database, "SessionLocal", sessionmaker(bind=state.engine))
    monkeypatch.setattr(identity_service, "_load_or_create", forbid_private_identity)
    monkeypatch.setattr(identity_service, "_cipher", forbid_private_identity)
    secret = b"x" * 32
    with tempfile.TemporaryDirectory(prefix="ir-", dir="/tmp") as directory:
        root = Path(directory)
        (root / ("a" * 24 + ".key")).write_bytes(secret)
        server = ApplicationPlatformServer(root / "p.sock", root, group="missing-test-group", allowed_actions=COMPATIBILITY_ACTIONS)
        server.start()
        client = ApplicationPlatformClient(server.socket_path, "a" * 24, secret)
        try:
            expected = client.get_installation_identity()
            assert expected == call(state)
            forged = ApplicationPlatformClient(server.socket_path, "a" * 24, b"y" * 32)
            # Unauthenticated peers receive no signed response or dispatch.
            with pytest.raises(ApplicationPlatformError, match="response is invalid"):
                forged.get_installation_identity()
            state.manager.revoke(1, actor_token=state.token, request_id=identity(),
                expected_revision=state.manager.inspect(1)["grant_record_revision"])
            with pytest.raises(ApplicationPlatformError):
                client.get_installation_identity()
        finally:
            server.stop()


@pytest.mark.parametrize("collector", ["absent", "slow", "failed", "full", "disabled"])
def test_signed_identity_trace_preserves_revocation_and_survives_collector_failure(
        identity_app, monkeypatch, collector):
    import backend.database

    state = identity_app
    activate_identity_grant(state)
    monkeypatch.setattr(backend.database, "SessionLocal", sessionmaker(bind=state.engine))
    monkeypatch.setattr(identity_service, "_load_or_create", forbid_private_identity)
    monkeypatch.setattr(identity_service, "_cipher", forbid_private_identity)
    allocation = 1 if collector == "full" else 1024 * 1024
    core_records = DiagnosticSession("core", "0.3.0-beta.57", max_bytes=allocation)
    sdk_records = DiagnosticSession("sdk", "1.3", max_bytes=allocation)
    if collector != "disabled":
        core_records.start()
        sdk_records.start()
    fields = []
    secret = b"x" * 32
    with tempfile.TemporaryDirectory(prefix="dt-", dir="/tmp") as directory, ExitStack() as collectors:
        root = Path(directory)
        (root / ("a" * 24 + ".key")).write_bytes(secret)
        server = ApplicationPlatformServer(root / "p.sock", root, group="missing-test-group",
                                           diagnostics=core_records, allowed_actions=COMPATIBILITY_ACTIONS)
        original_read = server._read

        def observe_fields(connection, deadline=None):
            request = original_read(connection, deadline)
            fields.append(set(request))
            return request

        monkeypatch.setattr(server, "_read", observe_fields)
        if collector == "slow":
            # Keep a snapshot open without consuming it while Core does work.
            collectors.enter_context(core_records.export())
        if collector == "failed":
            with pytest.raises(OSError):
                with core_records.export():
                    raise OSError("collector failed with password=must-not-leak")
        client = ApplicationPlatformClient(server.socket_path, "a" * 24, secret, diagnostics=sdk_records)
        server.start()
        try:
            assert client.get_installation_identity() == call(state)
            state.manager.revoke(1, actor_token=state.token, request_id=identity(),
                expected_revision=state.manager.inspect(1)["grant_record_revision"])
            with pytest.raises(ApplicationPlatformError):
                client.get_installation_identity()
        finally:
            server.stop()
        collectors.close()
        assert fields == [set(frame()), set(frame())]
    exported = []
    for session in (core_records, sdk_records):
        with session.export() as chunks:
            exported.extend(chunks)
    content = b"".join(exported)
    assert all(value not in content for value in (
        secret, b"PRIVATE_MUST_NOT_APPEAR", b"public_key", b"signature",
        b"password", b"must-not-leak", state.token.encode(),
    ))
    if collector in {"full", "disabled"}:
        assert core_records.status()["records"] == sdk_records.status()["records"] == 0
        if collector == "full":
            assert core_records.status()["dropped"]["full"] >= 4
        return
    events = [json.loads(line) for line in exported if "session" not in json.loads(line)]
    sdk_events = [e for e in events if e["component"] == "sdk"]
    assert len(sdk_events) == 2  # No implicit retry.
    success, denied = sdk_events
    assert success["result"] == "ok"
    assert denied["result"] == "denied"
    successful = {e["span_id"]: e for e in events if e["trace_id"] == success["trace_id"]}
    assert set(successful) == {"sdk.call", "core.request", "authority.admission", "identity.read"}
    assert all(e["result"] == "ok" for e in successful.values())
    assert successful["identity.read"]["parent_span_id"] == "authority.admission"
    refusals = [e for e in events if e["trace_id"] == denied["trace_id"]]
    assert any(e["span_id"] == "authority.admission" and e["reason"] == "authority_unavailable"
               and e["result"] == "denied" for e in refusals)
    assert not any(e["span_id"] == "identity.read" for e in refusals)
