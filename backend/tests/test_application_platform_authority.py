"""Existing broker authority baseline; not an OS isolation/sandbox proof."""

import hashlib
import hmac
import json
import socket
import time
from types import SimpleNamespace

import backend.database
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.db.module import (
    ApplicationExtensionInstallation,
    ApplicationSyncCheckpoint,
    ModulePackage,
)
from backend.services.application_platform import ApplicationPlatformServer
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError


pytestmark = pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="Platform transport requires Unix sockets"
)


@pytest.fixture
def authority(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(backend.database, "SessionLocal", sessions)
    db = sessions()
    keys = tmp_path / "keys"
    keys.mkdir()
    instances = ["a" * 24, "b" * 24]
    secrets = [b"a" * 32, b"b" * 32]
    installations = []
    for index, instance in enumerate(instances):
        package = ModulePackage(
            module_id=f"org.example.authority{index}",
            version="1.0.0",
            manifest={},
            sha256=str(index) * 64,
            size_bytes=1,
            file_path="unused.zip",
            registrations=[],
        )
        db.add(package)
        db.flush()
        installation = ApplicationExtensionInstallation(
            module_id=package.module_id,
            module_package_id=package.id,
            instance_id=instance,
            active_version="1.0.0",
            status="active",
            enabled=True,
            socket_path="unused.sock",
        )
        db.add(installation)
        installations.append(installation)
        (keys / f"{instance}.key").write_bytes(secrets[index])
    db.commit()
    server = ApplicationPlatformServer(
        tmp_path / "p.sock", keys, group="missing-test-group"
    )
    server.start()
    clients = [
        ApplicationPlatformClient(server.socket_path, instance, secret)
        for instance, secret in zip(instances, secrets)
    ]
    try:
        yield SimpleNamespace(
            db=db,
            server=server,
            clients=clients,
            instances=instances,
            secrets=secrets,
            installations=installations,
        )
    finally:
        server.stop()
        db.close()
        engine.dispose()


def test_same_checkpoint_name_has_separate_installation_ownership(authority):
    first, second = authority.clients
    first.put_checkpoint("shared_name", {"owner": "first"}, expected_revision=0)
    assert second.get_checkpoint("shared_name") == {
        "checkpoint_id": "shared_name",
        "revision": 0,
        "value": {},
    }
    second.put_checkpoint("shared_name", {"owner": "second"}, expected_revision=0)
    assert first.get_checkpoint("shared_name")["value"] == {"owner": "first"}
    assert second.get_checkpoint("shared_name")["value"] == {"owner": "second"}


@pytest.mark.parametrize("case", ["foreign_identity", "wrong_key", "unknown_identity"])
def test_forged_broker_identity_cannot_write_checkpoints(authority, case):
    instance, secret = authority.instances[0], authority.secrets[0]
    if case == "foreign_identity":
        instance = authority.instances[1]
    elif case == "wrong_key":
        secret = b"x" * 32
    else:
        instance = "c" * 24
    forged = ApplicationPlatformClient(authority.server.socket_path, instance, secret)
    with pytest.raises(ApplicationPlatformError):
        forged.put_checkpoint("forged", {"unsafe": True}, expected_revision=0)
    assert list(authority.db.scalars(select(ApplicationSyncCheckpoint))) == []


def test_disable_rejects_new_checkpoint_work_but_retains_existing_data(authority):
    client = authority.clients[0]
    client.put_checkpoint("saved", {"keep": True}, expected_revision=0)
    authority.installations[0].enabled = False
    authority.db.commit()
    with pytest.raises(ApplicationPlatformError, match="not active"):
        client.put_checkpoint("saved", {"keep": False}, expected_revision=1)
    checkpoint = authority.db.scalar(select(ApplicationSyncCheckpoint))
    assert checkpoint.revision == 1
    assert checkpoint.value == {"keep": True}


def test_identical_checkpoint_mutation_is_fenced_by_revision_not_generic_replay_protection(
    authority,
):
    request = {
        "version": 1,
        "request_id": "baseline-repeated-request",
        "timestamp": int(time.time()),
        "instance_id": authority.instances[0],
        "action": "checkpoint.put",
        "checkpoint_id": "once",
        "expected_revision": 0,
        "value": {"saved": True},
    }
    secret = authority.secrets[0]
    request["signature"] = hmac.new(
        secret, authority.server._canonical(request), hashlib.sha256
    ).hexdigest()
    encoded = json.dumps(request).encode() + b"\n"
    results = []
    for _ in range(2):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(5)
            connection.connect(str(authority.server.socket_path))
            connection.sendall(encoded)
            reply = b""
            while b"\n" not in reply:
                chunk = connection.recv(65536)
                assert chunk, "expected a signed response"
                reply += chunk
            response = json.loads(reply.split(b"\n", 1)[0])
            expected = hmac.new(
                secret, authority.server._canonical(response), hashlib.sha256
            ).hexdigest()
            assert hmac.compare_digest(response["signature"], expected)
            results.append(response)
    assert results[0]["ok"] is True
    assert results[1]["ok"] is False
    assert "conflict" in results[1]["error"]
    assert authority.clients[0].get_checkpoint("once")["revision"] == 1
