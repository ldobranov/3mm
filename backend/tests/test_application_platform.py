from datetime import UTC, datetime
import socket

import backend.database
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.services.application_platform import ApplicationPlatformServer
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError


pytestmark = pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"),
    reason="Application platform sockets are available on the Linux target",
)


def test_signed_platform_checkpoint_is_persistent_and_compare_and_swap(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    db = sessions()
    package = ModulePackage(module_id="org.3mm.platform-test", version="1.0.0", manifest={}, sha256="d" * 64, size_bytes=1, file_path="unused", registrations=[]); db.add(package); db.flush()
    instance_id = "3" * 24
    db.add(ApplicationExtensionInstallation(module_id=package.module_id, module_package_id=package.id, instance_id=instance_id, active_version="1.0.0", status="active", enabled=True, socket_path="unused")); db.commit(); db.close()
    monkeypatch.setattr(backend.database, "SessionLocal", sessions)
    key_root = tmp_path / "keys"; key_root.mkdir(); secret = b"s" * 32; (key_root / f"{instance_id}.key").write_bytes(secret)
    server = ApplicationPlatformServer(tmp_path / "platform" / "platform.sock", key_root, group="missing-test-group")
    server.start()
    try:
        client = ApplicationPlatformClient(server.socket_path, instance_id, secret)
        assert client.get_checkpoint("catalog") == {"checkpoint_id": "catalog", "revision": 0, "value": {}}
        saved = client.put_checkpoint("catalog", {"page": 2}, expected_revision=0)
        assert saved["revision"] == 1
        assert client.get_checkpoint("catalog")["value"] == {"page": 2}
        try:
            client.put_checkpoint("catalog", {"page": 3}, expected_revision=0)
            assert False, "stale update must fail"
        except ApplicationPlatformError as exc:
            assert "conflict" in str(exc)
    finally:
        server.stop(); engine.dispose()
