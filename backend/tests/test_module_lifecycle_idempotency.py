"""Focused coverage for retried and repeated module lifecycle episodes."""

import io
import json
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace

import backend.database  # noqa: F401
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.db.device import Device, DeviceCommand
from backend.db.module import ModuleInstallation, ModulePackage
from backend.routes.device_commands import submit_command_result
from backend.routes.modules import router
from backend.services.module_packages import validate_module_package
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from three_mm_protocol import AgentCommandResult


DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"
MODULE_ID = "org.3mm.lifecycle-test"


@pytest.fixture
def lifecycle(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    device = Device(device_id=DEVICE_ID, role="node", protocol_version="1.0", approved_at=datetime.now(timezone.utc))
    db.add(device)
    db.commit()
    app = FastAPI()
    app.include_router(router)
    admin = SimpleNamespace(id=1)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: admin

    def add_package(version="1.0.0"):
        output = io.BytesIO()
        manifest = {
            "manifest_version": 2, "module_id": MODULE_ID, "name": "Lifecycle test",
            "version": version, "runtimes": ["agent"], "entrypoints": {},
            "compatibility": {"protocol": "1.0", "architectures": ["any"]},
            "permissions": [], "capabilities": {"provides": [], "consumes": []},
            "health_check": {"type": "file_exists", "path": "health/ready"},
            "registrations": [],
        }
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("health/ready", "ready")
        blob = output.getvalue()
        validated = validate_module_package(blob)
        path = tmp_path / f"{version}.zip"
        path.write_bytes(blob)
        record = ModulePackage(module_id=MODULE_ID, version=version, manifest=manifest,
            sha256=validated.sha256, size_bytes=len(blob), file_path=str(path), registrations=[])
        db.add(record)
        db.commit()
        return record

    def complete(command_id, status="succeeded"):
        command = db.scalar(select(DeviceCommand).where(DeviceCommand.command_id == command_id))
        command.status = "delivered"
        db.commit()
        submit_command_result(DEVICE_ID, command_id,
            AgentCommandResult(command_id=command_id, device_id=DEVICE_ID, status=status,
                completed_at=datetime.now(timezone.utc), error="test failure" if status == "failed" else None),
            device=device, db=db)

    package = add_package()
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=db, admin=admin, package=package,
            add_package=add_package, complete=complete,
            install=f"/api/v1/modules/packages/{package.sha256}/devices/{DEVICE_ID}/install",
            disable=f"/api/v1/modules/{MODULE_ID}/devices/{DEVICE_ID}/disable")
    db.close()
    engine.dispose()


def _request(lifecycle, path, key=None):
    headers = {"Idempotency-Key": key} if key is not None else {}
    response = lifecycle.client.post(path, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_legacy_retries_are_stable_but_completed_opposite_starts_new_episode(lifecycle):
    command_ids = []
    for path in (lifecycle.install, lifecycle.disable, lifecycle.install, lifecycle.disable):
        first = _request(lifecycle, path)
        command_id = first["command_id"]
        assert command_id not in command_ids
        assert _request(lifecycle, path)["command_id"] == command_id
        lifecycle.complete(command_id)
        assert _request(lifecycle, path)["command_id"] == command_id
        command_ids.append(command_id)
    commands = list(lifecycle.db.scalars(select(DeviceCommand)))
    assert len(commands) == 4
    assert len({command.idempotency_key for command in commands}) == 4
    assert all(len(command.idempotency_key) <= 128 for command in commands)
    installation = lifecycle.db.scalar(select(ModuleInstallation))
    assert installation.enabled is False
    assert installation.data_retained is True


def test_explicit_key_replay_does_not_restore_stale_installation_state(lifecycle):
    installed = _request(lifecycle, lifecycle.install, "install-1")
    assert _request(lifecycle, lifecycle.install, "install-1") == installed
    lifecycle.complete(installed["command_id"])
    disabled = _request(lifecycle, lifecycle.disable, "disable-1")
    lifecycle.complete(disabled["command_id"])
    stale_install = _request(lifecycle, lifecycle.install, "install-1")
    assert stale_install["command_id"] == disabled["command_id"]
    assert stale_install["enabled"] is False

    reinstalled = _request(lifecycle, lifecycle.install, "install-2")
    lifecycle.complete(reinstalled["command_id"])
    stale_disable = _request(lifecycle, lifecycle.disable, "disable-1")
    assert stale_disable["command_id"] == reinstalled["command_id"]
    assert stale_disable["enabled"] is True
    second_disable = _request(lifecycle, lifecycle.disable, "disable-2")
    assert second_disable["command_id"] != disabled["command_id"]
    assert len(list(lifecycle.db.scalars(select(DeviceCommand)))) == 4


def test_client_identity_is_scoped_and_conflicting_install_content_is_rejected(lifecycle):
    key = "x" * 128
    first = _request(lifecycle, lifecycle.install, key)
    assert _request(lifecycle, lifecycle.install, key)["command_id"] == first["command_id"]
    replacement = lifecycle.add_package("2.0.0")
    replacement_path = f"/api/v1/modules/packages/{replacement.sha256}/devices/{DEVICE_ID}/install"
    conflict = lifecycle.client.post(replacement_path, headers={"Idempotency-Key": key})
    assert conflict.status_code == 409
    assert "different content" in conflict.json()["detail"]
    assert lifecycle.db.scalar(select(ModuleInstallation)).desired_version == "1.0.0"

    # Identical client keys in another caller or action scope are independent.
    lifecycle.admin.id = 2
    second = _request(lifecycle, lifecycle.install, key)
    assert second["command_id"] != first["command_id"]
    disabled = _request(lifecycle, lifecycle.disable, key)
    assert disabled["command_id"] not in {first["command_id"], second["command_id"]}
    commands = list(lifecycle.db.scalars(select(DeviceCommand)))
    assert len(commands) == 3
    assert all(len(command.idempotency_key) <= 128 for command in commands)


@pytest.mark.parametrize("key", ["fleet:" + "a" * 32, "x" * 48, "x" * 49])
def test_short_client_keys_remain_correlatable_in_command_history(lifecycle, key):
    first = _request(lifecycle, lifecycle.install, key)
    assert _request(lifecycle, lifecycle.install, key)["command_id"] == first["command_id"]
    command = lifecycle.db.scalar(select(DeviceCommand))
    assert len(command.idempotency_key) <= 128
    assert command.idempotency_key.endswith(":" + key) is (len(key) <= 48)


@pytest.mark.parametrize("key", ["", "has spaces", "@invalid", "x" * 129])
@pytest.mark.parametrize("action", ["install", "disable"])
def test_invalid_client_keys_are_rejected_before_queueing(lifecycle, key, action):
    response = lifecycle.client.post(getattr(lifecycle, action), headers={"Idempotency-Key": key})
    assert response.status_code == 422
    assert list(lifecycle.db.scalars(select(DeviceCommand))) == []
