import hashlib
import json
import time
from pathlib import Path

import backend.database
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.installation_identity import CoreInstallationIdentity
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.services.application_platform import ApplicationPlatformServer
from backend.services.module_packages import validate_module_package
from backend.tests.test_module_packages import (
    application_definition,
    application_manifest,
    application_package,
)
from three_mm_application_sdk import (
    ApplicationPlatformClient,
    ApplicationPlatformError,
    verify_installation_proof,
)
from three_mm_protocol.tests.test_installation_identity import proof_request


@pytest.fixture
def platform(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", Fernet.generate_key().decode())
    definition = application_definition(
        platform_permissions=[
            "installation.identity.read",
            "installation.identity.prove",
        ]
    )
    definition["service"]["sdk_version"] = "1.1"
    manifest = application_manifest()
    manifest["permissions"] += definition["platform_permissions"]
    blob = application_package(definition=definition, manifest_value=manifest)
    path = tmp_path / "package.zip"
    path.write_bytes(blob)
    validated = validate_module_package(blob)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(backend.database, "SessionLocal", sessions)
    db = sessions()
    package = ModulePackage(
        module_id=manifest["module_id"],
        version=manifest["version"],
        manifest=manifest,
        sha256=validated.sha256,
        size_bytes=len(blob),
        file_path=str(path),
        registrations=[],
    )
    db.add(package)
    db.flush()
    installation = ApplicationExtensionInstallation(
        module_id=package.module_id,
        module_package_id=package.id,
        instance_id="3" * 24,
        active_version="1.0.0",
        status="active",
        enabled=True,
        socket_path="unused",
    )
    db.add(installation)
    db.commit()
    key_root = tmp_path / "keys"
    key_root.mkdir()
    secret = b"s" * 32
    (key_root / f"{installation.instance_id}.key").write_bytes(secret)
    server = ApplicationPlatformServer(tmp_path / "platform.sock", key_root)
    yield db, installation, package, server, secret
    db.close()
    engine.dispose()


def test_two_extension_instances_share_whole_core_identity(platform):
    db, installation, _, server, _ = platform
    first = server._dispatch(db, installation, {"action": "installation.identity.get"})
    installation.instance_id = "4" * 24
    db.commit()
    second = server._dispatch(db, installation, {"action": "installation.identity.get"})
    assert second == first
    from three_mm_application_sdk import SDK_VERSION
    assert first["sdk_version"] == SDK_VERSION
    assert set(first["identity"]) == {
        "identity_version",
        "installation_id",
        "algorithm",
        "key_id",
        "public_key",
        "key_generation",
        "created_at",
    }


@pytest.mark.parametrize("failure", ["undeclared", "inactive", "tampered"])
def test_permission_and_active_package_gate_precedes_identity_creation(
    platform, failure
):
    db, installation, package, server, _ = platform
    if failure == "undeclared":
        blob = application_package()
        Path(package.file_path).write_bytes(blob)
        package.sha256 = hashlib.sha256(blob).hexdigest()
    elif failure == "inactive":
        installation.enabled = False
    else:
        package.sha256 = "f" * 64
    db.commit()
    for action in ("installation.identity.get", "installation.identity.prove"):
        with pytest.raises((ValueError, RuntimeError)):
            server._dispatch(db, installation, {"action": action})
    assert db.get(CoreInstallationIdentity, 1) is None


class MemoryConnection:
    """Exercise signed platform envelopes without OS-specific Unix socket paths."""

    def __init__(self, message):
        self.message = message
        self.response = b""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def recv(self, _size):
        message, self.message = self.message, b""
        return message

    def sendall(self, message):
        self.response += message


def test_signed_sdk_read_and_proof_use_existing_authenticated_boundary(
    platform, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    db, installation, _, server, secret = platform

    class ClientSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def sendall(self, message):
            connection = MemoryConnection(message)
            server._handle(connection)
            self.response = connection.response

        def recv(self, _limit):
            result, self.response = self.response, b""
            return result

    monkeypatch.setattr(
        "three_mm_application_sdk.socket.socket", lambda *_args: ClientSocket()
    )
    # Windows has no AF_UNIX in this runtime; this test exercises envelopes with
    # an in-memory socket, not a claim of Unix-socket availability on Windows.
    monkeypatch.setattr("three_mm_application_sdk.socket.AF_UNIX", 1, raising=False)
    client = ApplicationPlatformClient(
        server.socket_path, installation.instance_id, secret
    )
    identity = client.get_installation_identity()["identity"]
    now = datetime.now(UTC)
    request = proof_request(
        created_at=now, expires_at=now + timedelta(seconds=90)
    ).model_dump(mode="json")
    proof = client.prove_installation_identity(request)
    assert (
        verify_installation_proof(
            proof, expected_identity=identity, expected_request=request, now=now
        ).installation_id
        == identity["installation_id"]
    )
    installation.enabled = False
    db.commit()
    with pytest.raises(ApplicationPlatformError, match="not active"):
        client.get_installation_identity()


def test_spoofed_platform_signature_cannot_create_identity(platform):
    db, installation, _, server, _ = platform
    request = {
        "version": 1,
        "request_id": "spoof",
        "timestamp": int(time.time()),
        "instance_id": installation.instance_id,
        "action": "installation.identity.get",
        "signature": "0" * 64,
    }
    connection = MemoryConnection(json.dumps(request).encode() + b"\n")
    server._handle(connection)
    response = json.loads(connection.response)
    assert response["ok"] is False
    assert "authentication failed" in response["error"]
    assert db.get(CoreInstallationIdentity, 1) is None
