"""Bounded M20 management writers; no grant issuer or effect-admission claim."""

from dataclasses import replace
import threading

import backend.database  # noqa: F401
import pytest
import requests
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session

from backend.db.application_command import ApplicationCommandEpoch
from backend.db.audit_log import AuditLog
from backend.db.authority import CoreAuthorityGuard
from backend.db.base import Base
from backend.db.module import (
    ApplicationConnectorBinding,
    ApplicationExtensionInstallation,
    ApplicationSecretReference,
    ModulePackage,
)
from backend.db.user import User
from backend.routes.application_operations import router, _authority_write
from backend.services.application_connectors import (
    bind_application_connector,
    execute_connector_request,
    prepare_application_connector_binding,
)
from backend.services.application_secrets import (
    read_secret_authority,
    rotate_secret_reference,
)
from backend.services.authority_metadata import (
    AuthorityMetadataError,
    authority_transaction,
    read_application_authority,
    read_authority_guard,
)
from backend.tests.test_application_connectors import definition
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token


@pytest.fixture
def writers(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(
        "backend.services.application_connectors.load_application_definition",
        lambda _package: definition(),
    )
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'writers.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 3},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(
        engine,
        tables=[
            Base.metadata.tables[name]
            for name in (
                "users",
                "sessions",
                "audit_logs",
                "core_authority_guard",
                "module_packages",
                "application_extension_installations",
                "application_secret_references",
                "application_connector_bindings",
                "application_connector_attempts",
                "application_command_epochs",
            )
        ],
    )
    with Session(engine) as db, db.begin():
        db.add(CoreAuthorityGuard(singleton_id=1))
        for index, role in ((1, "admin"), (2, "user")):
            db.add(
                User(
                    id=index,
                    username=f"user{index}",
                    email=f"u{index}@example.test",
                    hashed_password="unused",
                    role=role,
                )
            )
            db.add(
                ModulePackage(
                    id=index,
                    module_id=f"org.example.writer{index}",
                    version="1.0.0",
                    manifest={},
                    sha256=str(index) * 64,
                    size_bytes=1,
                    file_path="unused",
                )
            )
        db.flush()
        for index in (1, 2):
            db.add(
                ApplicationExtensionInstallation(
                    id=index,
                    module_id=f"org.example.writer{index}",
                    module_package_id=index,
                    instance_id=str(index) * 24,
                    active_version="1.0.0",
                    status="active",
                    enabled=True,
                    socket_path="unused",
                )
            )
        db.flush()
        db.add(ApplicationCommandEpoch(installation_id=1, generation="c" * 32))
    app = FastAPI()
    app.include_router(router)

    def database():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app, raise_server_exceptions=False) as client:
        yield engine, client
    engine.dispose()


BASE = "/api/v1/application-extensions/org.example.writer1"
AUTH = {"Authorization": f"Bearer {create_access_token('1', {'role': 'admin'})}"}
CREDENTIAL = {
    "label": "API",
    "credential_kind": "basic",
    "value": {"username": "private-user", "password": "private-password"},
}


def state(engine):
    with Session(engine) as db:
        return (
            read_authority_guard(db),
            read_application_authority(db, 1),
            list(
                db.execute(
                    select(*ApplicationConnectorBinding.__table__.c).order_by(
                        ApplicationConnectorBinding.id
                    )
                )
            ),
            list(
                db.execute(
                    select(*ApplicationSecretReference.__table__.c).order_by(
                        ApplicationSecretReference.id
                    )
                )
            ),
            list(db.execute(select(*AuditLog.__table__.c).order_by(AuditLog.id))),
            db.get(ApplicationCommandEpoch, 1).generation,
        )


def create_secret(client, *, base=BASE, payload=None):
    response = client.post(f"{base}/secrets", headers=AUTH, json=payload or CREDENTIAL)
    assert response.status_code == 201, response.text
    return response.json()["secret_ref"]


def bind(client, secret_ref, origin="https://example.test"):
    return client.put(
        f"{BASE}/connectors/business_api",
        headers=AUTH,
        json={"destination_origin": origin, "secret_ref": secret_ref},
    )


def bound(writers):
    engine, client = writers
    secret_ref = create_secret(client)
    assert bind(client, secret_ref).status_code == 200
    return engine, client, secret_ref


def test_real_admin_flow_advances_only_effective_authority_and_redacts(writers):
    engine, client = writers
    original = state(engine)
    secret_ref = create_secret(client)
    created = state(engine)
    assert created[:2] == original[:2]  # An unused secret grants nothing.
    response = bind(client, secret_ref, "https://EXAMPLE.test/")
    assert response.status_code == 200
    assert response.json() == {
        "connector_id": "business_api",
        "destination_origin": "https://example.test",
        "enabled": True,
        "uses_credential": True,
    }
    first = state(engine)
    assert first[0].revision == original[0].revision + 1
    assert first[1].epoch != original[1].epoch
    assert first[1].incarnation == original[1].incarnation
    assert bind(client, secret_ref).status_code == 200
    retry = state(engine)
    assert retry[:4] == first[:4]  # No metadata, ciphertext or binding telemetry drift.
    for origin in ("https://other.test", "https://example.test"):
        before = state(engine)
        assert bind(client, secret_ref, origin).status_code == 200
        after = state(engine)
        assert after[0].revision == before[0].revision + 1
        assert after[1].epoch != before[1].epoch
        assert after[2][0] != before[2][0]
    secret_path = f"{BASE}/secrets/{secret_ref}"
    before = state(engine)
    rotated = client.put(
        secret_path,
        headers=AUTH,
        json={
            "value": {
                "username": "new-private-user",
                "password": "new-private-password",
            }
        },
    )
    assert rotated.status_code == 200 and rotated.json()["version"] == 2
    after = state(engine)
    assert after[0].revision == before[0].revision + 1
    assert after[1].epoch != before[1].epoch and after[2] == before[2]
    assert client.delete(secret_path, headers=AUTH).status_code == 200
    revoked = state(engine)
    assert revoked[0].revision == after[0].revision + 1
    assert revoked[1].epoch != after[1].epoch
    assert client.delete(secret_path, headers=AUTH).status_code == 200
    assert state(engine)[:4] == revoked[:4]
    # Existing API semantics: an explicit rotation can reactivate a revoked secret.
    restored = client.put(
        secret_path, headers=AUTH, json={"value": CREDENTIAL["value"]}
    )
    assert restored.status_code == 200
    assert restored.json()["version"] == 3 and not restored.json()["revoked"]
    final = state(engine)
    assert final[0].revision == revoked[0].revision + 1
    assert final[5] == original[5]  # No change to physical command authority.
    rendered = repr(final[4]) + response.text + rotated.text + restored.text
    assert all(
        value not in rendered
        for value in ("private-user", "private-password", "encrypted_value", "gAAAA")
    )
    assert {row.action for row in _audits(engine)} == {
        "APPLICATION_SECRET_CREATED",
        "APPLICATION_CONNECTOR_CONFIGURED",
        "APPLICATION_SECRET_ROTATED",
        "APPLICATION_SECRET_REVOKED",
    }


def _audits(engine):
    with Session(engine) as db:
        return list(db.scalars(select(AuditLog)))


@pytest.mark.parametrize("change", ["credential", "enable"])
def test_credential_rebind_and_reenable_advance_binding_revision(writers, change):
    engine, client, secret_ref = bound(writers)
    if change == "credential":
        secret_ref = create_secret(client)
    else:
        with Session(engine) as db, db.begin():
            db.execute(update(ApplicationConnectorBinding).values(enabled=False))
    before = state(engine)
    assert bind(client, secret_ref).status_code == 200
    after = state(engine)
    assert after[0].revision == before[0].revision + 1
    assert after[1].epoch != before[1].epoch
    with Session(engine) as db:
        assert (
            db.scalar(select(ApplicationConnectorBinding.authority_revision))
            != before[2][0].authority_revision
        )


@pytest.mark.parametrize("operation", ["create", "bind", "rotate", "revoke"])
def test_audit_failure_rolls_back_resource_and_every_revision(writers, operation):
    engine, client, secret_ref = bound(writers)
    before = state(engine)

    def fail_audit(_mapper, _connection, _target):
        raise RuntimeError("injected audit failure")

    event.listen(AuditLog, "before_insert", fail_audit)
    try:
        if operation == "create":
            response = client.post(f"{BASE}/secrets", headers=AUTH, json=CREDENTIAL)
        elif operation == "bind":
            response = bind(client, secret_ref, "https://changed.test")
        elif operation == "rotate":
            response = client.put(
                f"{BASE}/secrets/{secret_ref}",
                headers=AUTH,
                json={"value": {"username": "changed", "password": "changed"}},
            )
        else:
            response = client.delete(f"{BASE}/secrets/{secret_ref}", headers=AUTH)
        assert response.status_code == 500
    finally:
        event.remove(AuditLog, "before_insert", fail_audit)
    assert state(engine) == before


@pytest.mark.parametrize("kind", ["foreign", "wrong_kind", "revoked"])
def test_unavailable_connector_credentials_never_change_state(writers, kind):
    engine, client, secret_ref = bound(writers)
    if kind == "foreign":
        secret_ref = create_secret(client, base=BASE.replace("writer1", "writer2"))
    elif kind == "wrong_kind":
        secret_ref = create_secret(
            client,
            payload={
                "label": "Other",
                "credential_kind": "bearer",
                "value": {"token": "private-token"},
            },
        )
    else:
        assert (
            client.delete(f"{BASE}/secrets/{secret_ref}", headers=AUTH).status_code
            == 200
        )
    before = state(engine)
    assert bind(client, secret_ref, "https://changed.test").status_code == 422
    assert state(engine) == before
    if kind == "foreign":
        for method in ("put", "delete"):
            kwargs = {"json": {"value": CREDENTIAL["value"]}} if method == "put" else {}
            assert (
                getattr(client, method)(
                    f"{BASE}/secrets/{secret_ref}", headers=AUTH, **kwargs
                ).status_code
                == 404
            )
        assert state(engine) == before


@pytest.mark.parametrize("actor", ["anonymous", "user"])
def test_all_writers_remain_admin_only(writers, actor):
    engine, client, secret_ref = bound(writers)
    headers = (
        {}
        if actor == "anonymous"
        else {"Authorization": f"Bearer {create_access_token('2', {'role': 'user'})}"}
    )
    before = state(engine)
    responses = [
        client.post(f"{BASE}/secrets", headers=headers, json=CREDENTIAL),
        client.put(
            f"{BASE}/secrets/{secret_ref}",
            headers=headers,
            json={"value": CREDENTIAL["value"]},
        ),
        client.delete(f"{BASE}/secrets/{secret_ref}", headers=headers),
        client.put(
            f"{BASE}/connectors/business_api",
            headers=headers,
            json={
                "destination_origin": "https://changed.test",
                "secret_ref": secret_ref,
            },
        ),
    ]
    assert all(
        response.status_code == (401 if actor == "anonymous" else 403)
        for response in responses
    )
    assert state(engine) == before


def test_missing_guard_is_not_lazily_created_by_endpoint(writers):
    engine, client = writers
    with Session(engine) as db, db.begin():
        db.execute(CoreAuthorityGuard.__table__.delete())
    response = client.post(f"{BASE}/secrets", headers=AUTH, json=CREDENTIAL)
    assert response.status_code == 409
    with Session(engine) as db:
        assert db.get(CoreAuthorityGuard, 1) is None
        assert db.scalar(select(ApplicationSecretReference.id)) is None
        assert db.scalar(select(AuditLog.id)) is None


@pytest.mark.parametrize("drift", ["epoch", "package", "incarnation"])
def test_stale_prepared_binding_cannot_apply_even_if_row_id_is_same(writers, drift):
    engine, client, secret_ref = bound(writers)
    with Session(engine) as db:
        installation = db.get(ApplicationExtensionInstallation, 1)
        plan = prepare_application_connector_binding(
            db, installation, "business_api", "https://changed.test", secret_ref
        )
    if drift == "epoch":
        assert (
            client.put(
                f"{BASE}/secrets/{secret_ref}",
                headers=AUTH,
                json={"value": CREDENTIAL["value"]},
            ).status_code
            == 200
        )
    else:
        with Session(engine) as db, db.begin():
            if drift == "package":
                db.execute(
                    update(ModulePackage)
                    .where(ModulePackage.id == 1)
                    .values(sha256="f" * 64)
                )
            else:
                # Isolate incarnation checking even when all other metadata matches.
                db.execute(
                    update(ApplicationExtensionInstallation)
                    .where(ApplicationExtensionInstallation.id == 1)
                    .values(authority_incarnation="d" * 32)
                )
    before = state(engine)
    with Session(engine) as db:
        with pytest.raises(AuthorityMetadataError):
            with authority_transaction(db) as authority:
                bind_application_connector(db, plan, authority=authority)
    assert state(engine) == before


@pytest.mark.parametrize("drift", ["version", "kind", "owner"])
def test_stale_secret_snapshot_poison_survives_a_caught_error(writers, drift):
    engine, _client, secret_ref = bound(writers)
    with Session(engine) as db:
        application = read_application_authority(db, 1)
        expected = read_secret_authority(db, application, secret_ref)
        if drift == "version":
            expected = replace(expected, version=expected.version + 1)
        elif drift == "kind":
            expected = replace(expected, credential_kind="bearer")
        else:
            expected = replace(expected, application=read_application_authority(db, 2))
    before = state(engine)
    with Session(engine) as db:
        with pytest.raises(AuthorityMetadataError):
            with authority_transaction(db) as authority:
                with pytest.raises(AuthorityMetadataError):
                    rotate_secret_reference(
                        db, expected, CREDENTIAL["value"], authority=authority
                    )
    assert state(engine) == before


def test_endpoint_scope_never_discards_pending_work(writers):
    engine, _client = writers
    with Session(engine) as db:
        user = db.get(User, 1)
        user.username = "pending-only"
        with pytest.raises(HTTPException) as exc:
            with _authority_write(db):
                pytest.fail("pending write admitted")
        assert exc.value.status_code == 409
        assert user in db.dirty and user.username == "pending-only"
        db.rollback()


def test_service_cannot_use_another_sessions_mutation(writers):
    engine, _client, secret_ref = bound(writers)
    with Session(engine) as db:
        expected = read_secret_authority(
            db, read_application_authority(db, 1), secret_ref
        )
    before = state(engine)
    with Session(engine) as db, Session(engine) as other:
        with pytest.raises(AuthorityMetadataError):
            with authority_transaction(db) as authority:
                with pytest.raises(AuthorityMetadataError):
                    rotate_secret_reference(
                        other, expected, CREDENTIAL["value"], authority=authority
                    )
    assert state(engine) == before


def test_package_io_finishes_before_first_write_and_telemetry_is_not_authority(
    writers, monkeypatch
):
    engine, client = writers
    secret_ref = create_secret(client)
    seen, loaded = [], []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().startswith(("UPDATE", "INSERT", "DELETE")):
            seen.append(statement)

    def load(_package):
        assert not seen  # No guard/resource lock during ZIP validation.
        loaded.append(True)
        return definition()

    event.listen(engine, "before_cursor_execute", capture)
    monkeypatch.setattr(
        "backend.services.application_connectors.load_application_definition", load
    )
    try:
        assert bind(client, secret_ref).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert loaded == [True] and seen[0].startswith("UPDATE core_authority_guard")
    monkeypatch.setattr(
        "backend.services.application_connectors.load_application_definition",
        lambda _package: definition(),
    )
    before = state(engine)

    def timeout(*_args, **_kwargs):
        raise requests.ReadTimeout()

    with Session(engine) as db:
        arguments = dict(
            connector_id="business_api",
            request_id="connector_" + "a" * 32,
            method="POST",
            path="/api/records",
            headers={},
            body=b"{}",
            idempotency_key="record-1",
            transport=timeout,
        )
        installation = db.get(ApplicationExtensionInstallation, 1)
        assert (
            execute_connector_request(db, installation, **arguments)["outcome"]
            == "ambiguous"
        )
        assert execute_connector_request(db, installation, **arguments)["duplicate"]
    after = state(engine)
    assert after[:2] == before[:2] and after[3:] == before[3:]
    with Session(engine) as db:
        assert (
            db.scalar(select(ApplicationConnectorBinding.authority_revision))
            == before[2][0].authority_revision
        )


def test_real_two_connection_rotation_race_rechecks_after_guard_wait(writers):
    engine, client, secret_ref = bound(writers)
    with Session(engine) as db:
        expected = read_secret_authority(
            db, read_application_authority(db, 1), secret_ref
        )
    before = state(engine)
    attempted, done = threading.Event(), threading.Event()
    result = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        if (
            threading.current_thread().name == "credential-writer"
            and statement.startswith("UPDATE core_authority_guard")
        ):
            attempted.set()

    def rotate():
        try:
            with Session(engine) as db, authority_transaction(db) as authority:
                rotate_secret_reference(
                    db, expected, CREDENTIAL["value"], authority=authority
                )
            result.append("unexpected commit")
        except AuthorityMetadataError:
            result.append("stale")
        except BaseException as exc:
            result.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=rotate, name="credential-writer")
    event.listen(engine, "before_cursor_execute", capture)
    try:
        with Session(engine) as db, authority_transaction(db) as authority:
            rotate_secret_reference(
                db, expected, CREDENTIAL["value"], authority=authority
            )
            thread.start()
            assert attempted.wait(2) and not done.wait(0.05)
        assert done.wait(4)
    finally:
        if thread.ident is not None:
            thread.join(4)
        event.remove(engine, "before_cursor_execute", capture)
    assert result == ["stale"]
    after = state(engine)
    assert after[0].revision == before[0].revision + 1
    with Session(engine) as db:
        assert (
            db.scalar(select(ApplicationSecretReference.version))
            == expected.version + 1
        )
