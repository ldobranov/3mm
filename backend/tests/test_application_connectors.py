from datetime import UTC, datetime

import backend.database  # noqa: F401
import pytest
import requests
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.db.base import Base
from backend.db.module import (
    ApplicationConnectorAttempt,
    ApplicationExtensionInstallation,
    ModulePackage,
)
from backend.services.application_connectors import (
    ApplicationConnectorError,
    bind_application_connector,
    execute_connector_request,
)
from backend.services.application_secrets import (
    create_secret_reference,
    decrypt_secret_reference,
    rotate_secret_reference,
)
from three_mm_protocol import ApplicationExtensionV1


def definition() -> ApplicationExtensionV1:
    return ApplicationExtensionV1.model_validate(
        {
            "application_extension_version": 1,
            "module_id": "org.3mm.connector-test",
            "version": "1.0.0",
            "service": {"artifact": "service/test.whl", "artifact_sha256": "a" * 64, "entrypoint": "test:create", "health_operation_id": "health"},
            "operations": [{"operation_id": "health", "kind": "query", "audiences": ["internal"], "idempotency": "forbidden", "output_schema": {"type": "object", "properties": {"status": {"type": "string", "enum": ["ready"]}}, "required": ["status"], "additionalProperties": False}}],
            "connectors": [{"connector_id": "business_api", "destination_config_key": "API_URL", "allowed_schemes": ["http", "https"], "path_prefix": "/api/", "authentication": "basic", "credential_ref_config_key": "API_CREDENTIAL", "supports_mutations": True}],
            "storage": {"schema_revision": "0001", "migration_entrypoint": "test:migrations"},
        }
    )


@pytest.fixture
def connector_db(monkeypatch):
    monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr("backend.services.application_connectors.load_application_definition", lambda _package: definition())
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    package = ModulePackage(module_id="org.3mm.connector-test", version="1.0.0", manifest={}, sha256="b" * 64, size_bytes=1, file_path="unused", registrations=[])
    db.add(package); db.flush()
    installation = ApplicationExtensionInstallation(module_id=package.module_id, module_package_id=package.id, instance_id="1" * 24, active_version="1.0.0", status="active", enabled=True, socket_path="unused")
    db.add(installation); db.commit()
    yield db, installation
    db.close(); engine.dispose()


def test_secret_rotation_and_connector_success_do_not_disclose_credentials(connector_db):
    db, installation = connector_db
    secret = create_secret_reference(db, installation_id=installation.id, label="Test", credential_kind="basic", value={"username": "api-user", "password": "private-pass"})
    assert "private-pass" not in secret.encrypted_value
    assert decrypt_secret_reference(secret)["username"] == "api-user"
    rotate_secret_reference(db, secret, {"username": "new-user", "password": "new-pass"})
    binding = bind_application_connector(db, installation, "business_api", "http://127.0.0.1:9999", secret.secret_ref)
    captured = {}

    class Response:
        status_code = 201
        content = b'{"ok":true}'
        headers = {"Content-Type": "application/json", "Set-Cookie": "must-not-return"}

    def transport(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return Response()

    result = execute_connector_request(db, installation, connector_id="business_api", request_id="connector_" + "a" * 32, method="POST", path="/api/records", headers={"Content-Type": "application/json"}, body=b"{}", idempotency_key="record-1", transport=transport)

    assert result["outcome"] == "succeeded"
    assert result["headers"] == {"Content-Type": "application/json"}
    assert captured["auth"] == ("new-user", "new-pass")
    assert captured["headers"]["Idempotency-Key"] == "record-1"
    assert binding.last_outcome == "succeeded"
    attempt = db.scalar(select(ApplicationConnectorAttempt))
    assert "pass" not in repr(attempt.__dict__).lower()


def test_mutation_timeout_is_ambiguous_and_is_not_blindly_replayed(connector_db):
    db, installation = connector_db
    secret = create_secret_reference(db, installation_id=installation.id, label="Test", credential_kind="basic", value={"username": "u", "password": "p"})
    bind_application_connector(db, installation, "business_api", "https://example.test", secret.secret_ref)
    calls = []

    def timeout(*args, **kwargs):
        calls.append((args, kwargs))
        raise requests.ReadTimeout("unknown remote outcome")

    arguments = dict(connector_id="business_api", request_id="connector_" + "b" * 32, method="POST", path="/api/records", headers={}, body=b"{}", idempotency_key="record-2", transport=timeout)
    first = execute_connector_request(db, installation, **arguments)
    second = execute_connector_request(db, installation, **arguments)

    assert first["outcome"] == "ambiguous"
    assert second["duplicate"] is True
    assert len(calls) == 1
    with pytest.raises(ApplicationConnectorError, match="outside"):
        execute_connector_request(db, installation, connector_id="business_api", request_id="connector_" + "c" * 32, method="GET", path="/private", headers={}, body=b"", idempotency_key=None, transport=timeout)
