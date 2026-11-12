"""Real lifecycle receipts and a complete administrator Agent inventory."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.db.device import DeviceCommand, DeviceRuntimeFeatures
from backend.db.module import ModuleInstallation
from backend.artifacts import api as modules
from backend.devices.commands.api import submit_command_result
from backend.tests.test_module_lifecycle_idempotency import lifecycle, DEVICE_ID, MODULE_ID, _request
from packages.protocol import AgentCommandResult


def installed(s):
    result = _request(s, s.install)
    s.complete(result["command_id"])
    s.db.add(DeviceRuntimeFeatures(device_id=s.device.id, revision=1,
        declaration={"command_types": ["module.install", "module.disable", "module.uninstall"]},
        received_at=datetime.now(timezone.utc)))
    s.db.commit()
    return result


def removal(s, command_id):
    return dict(package_sha256=s.package.sha256, expected_command_id=command_id,
                request_id="a" * 32, confirmation=MODULE_ID)


def path():
    return f"/api/v1/modules/{MODULE_ID}/devices/{DEVICE_ID}/uninstall"


def test_catalog_includes_uploaded_active_disabled_and_old_agents(lifecycle):
    s = lifecycle
    item = s.client.get("/api/v1/modules/agent-catalog").json()["items"][0]
    assert item["sha256"] == s.package.sha256 and item["installations"] == []
    first = _request(s, s.install)
    s.complete(first["command_id"])
    disabled = _request(s, s.disable); s.complete(disabled["command_id"])
    item = s.client.get("/api/v1/modules/agent-catalog").json()["items"][0]
    assert item["installations"][0]["enabled"] is False
    assert item["installations"][0]["uninstall_supported"] is False
    assert s.client.post(path(), json=removal(s, disabled["command_id"])).status_code == 409


def test_full_removal_requires_exact_confirmation_and_keeps_pending_visible(lifecycle):
    s = lifecycle; first = installed(s)
    body = removal(s, first["command_id"])
    for changed in (dict(confirmation="other"), dict(package_sha256="f"*64), dict(expected_command_id="old")):
        assert s.client.post(path(), json={**body, **changed}).status_code == 409
    queued = s.client.post(path(), json=body)
    assert queued.status_code == 200, queued.text
    assert s.client.post(path(), json=body).json() == queued.json()
    assert s.client.post(path(), json={**body, "request_id": "b"*32}).status_code == 409
    state = s.db.scalar(select(ModuleInstallation))
    assert state.status == "queued" and state.enabled is False and state.data_retained is True
    assert s.client.get("/api/v1/modules/agent-catalog").json()["items"][0]["installations"]
    assert s.client.delete("/api/v1/modules/agent-packages/" + s.package.sha256).status_code == 409


def test_only_exact_agent_receipt_allows_package_deletion(lifecycle, monkeypatch, tmp_path):
    s = lifecycle; first = installed(s)
    uploads = tmp_path / "uploads"; (uploads / "modules").mkdir(parents=True)
    original = __import__("pathlib").Path(s.package.file_path)
    archive = uploads / "modules" / (s.package.sha256 + ".zip")
    archive.write_bytes(original.read_bytes())
    s.package.file_path = str(archive); s.db.commit()
    monkeypatch.setattr(modules, "get_settings", lambda: SimpleNamespace(backend=SimpleNamespace(uploads_dir=uploads)))
    monkeypatch.setattr(modules, "compiled_artifacts_dir", lambda: tmp_path / "compiled")
    body = removal(s, first["command_id"])
    response = s.client.post(path(), json=body)
    assert response.status_code == 200, response.text
    command_id = response.json()["command_id"]
    command = s.db.scalar(select(DeviceCommand).where(DeviceCommand.command_id == command_id))
    command.status = "delivered"; s.db.commit()
    def complete(output):
        return submit_command_result(DEVICE_ID, command_id, AgentCommandResult(
            command_id=command_id, device_id=DEVICE_ID, status="succeeded",
            completed_at=datetime.now(timezone.utc), output=output),
            device=s.device, db=s.db, authorization="Device cred_lifecycle:test-secret")
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        complete({"module_id": "other", "status": "uninstalled"})
    assert archive.exists()
    complete({"module_id": MODULE_ID, "status": "uninstalled", "version": "1.0.0"})
    state = s.db.scalar(select(ModuleInstallation))
    assert state.status == "uninstalled" and state.installed_version is None and state.data_retained is False
    lookup = s.client.get(path() + "-requests/" + body["request_id"])
    assert lookup.json()["status"] == "succeeded"
    assert s.client.delete("/api/v1/modules/agent-packages/" + s.package.sha256).status_code == 200
    assert not archive.exists()
    assert s.db.scalar(select(ModuleInstallation)) is None
    assert all("package_base64" not in c.payload for c in s.db.scalars(select(DeviceCommand)))


def test_revoked_device_cannot_queue_removal(lifecycle):
    s = lifecycle; first = installed(s)
    s.device.revoked_at = datetime.now(timezone.utc); s.db.commit()
    assert s.client.post(path(), json=removal(s, first["command_id"])).status_code == 409
    assert not list(s.db.scalars(select(DeviceCommand).where(DeviceCommand.command_type == "module.uninstall")))


def test_failed_removal_keeps_data_and_other_admin_cannot_read_its_request(lifecycle):
    s = lifecycle; first = installed(s); body = removal(s, first["command_id"])
    queued = s.client.post(path(), json=body).json(); s.complete(queued["command_id"], status="failed")
    state = s.db.scalar(select(ModuleInstallation))
    assert state.data_retained and state.status == "failed"
    assert s.client.delete("/api/v1/modules/agent-packages/" + s.package.sha256).status_code == 409
    s.admin.id = 2
    assert s.client.get(path() + "-requests/" + body["request_id"]).status_code == 404


def test_unknown_prior_delivery_blocks_removal_without_hiding_installation(lifecycle):
    s = lifecycle; first = installed(s)
    prior = s.db.scalar(select(DeviceCommand).where(DeviceCommand.command_id == first["command_id"]))
    prior.status = "expired"; prior.delivered_at = datetime.now(timezone.utc); s.db.commit()
    assert s.client.post(path(), json=removal(s, first["command_id"])).status_code == 409
    catalog = s.client.get("/api/v1/modules/agent-catalog").json()["items"]
    assert catalog[0]["installations"][0]["status"] == "expired"


def test_inventory_removal_and_package_delete_require_administrator(lifecycle):
    from fastapi import HTTPException
    from backend.accounts.dependencies import require_admin
    s = lifecycle
    def denied():
        raise HTTPException(403, "Administrator required")
    s.client.app.dependency_overrides[require_admin] = denied
    assert s.client.get("/api/v1/modules/agent-catalog").status_code == 403
    assert s.client.post(path(), json=removal(s, None)).status_code == 403
    assert s.client.delete("/api/v1/modules/agent-packages/" + s.package.sha256).status_code == 403
    assert not list(s.db.scalars(select(DeviceCommand)))
