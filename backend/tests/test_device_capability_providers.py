"""Common Core routers only: no Fleet extension or Agent module runtime."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401
from backend.db.audit_log import AuditLog
from backend.db.base import Base
from backend.db.authority import CoreAuthorityGuard
from backend.db.device import (
    Device,
    DeviceCapabilityProvider,
    DeviceCapabilityState,
    DeviceCredential,
    DeviceEvent,
    DevicePlatformState,
)
from backend.db.module import ModuleInstallation, ModulePackage
from backend.db.user import User
from backend.routes.device_capabilities import router
from backend.routes.device_capability_state import router as state_router
from backend.routes.device_commands import router as commands_router
from backend.routes.ai_extension_builder_routes import router as builder_router
from backend.services.ai_capability_context import build_automation_capability_context
from backend.services.device_capability_registry import registered_capabilities
from backend.services.device_pairing import credential_secret_hash
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token
from three_mm_protocol import AutomationDefinitionV1, validate_automation_capabilities


@pytest.fixture
def core(monkeypatch):
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    admin = User(
        username="admin",
        email="admin@example.com",
        hashed_password=hash_password("test"),
        role="admin",
    )
    viewer = User(
        username="viewer",
        email="viewer@example.com",
        hashed_password=hash_password("test"),
        role="viewer",
    )
    devices = [
        Device(
            device_id="dev_" + char * 32,
            role="standalone" if char == "1" else "node",
            protocol_version="1.0",
            approved_at=datetime.now(UTC),
        )
        for char in ("1", "2")
    ]
    db.add_all([admin, viewer, *devices, CoreAuthorityGuard(singleton_id=1)])
    db.flush()
    credentials = [
        DeviceCredential(
            device_id=device.id,
            credential_id="cred_" + str(i),
            secret_hash=credential_secret_hash("test-secret"),
        )
        for i, device in enumerate(devices)
    ]
    db.add_all([*credentials, *(DevicePlatformState(device_id=device.id) for device in devices)])
    db.commit()
    app = FastAPI()
    for item in (router, state_router, commands_router, builder_router):
        app.include_router(item)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield SimpleNamespace(
            db=db,
            engine=engine,
            client=client,
            devices=devices,
            credentials=credentials,
            admin={
                "Authorization": f"Bearer {create_access_token(str(admin.id), {'role': 'admin'})}"
            },
            viewer={
                "Authorization": f"Bearer {create_access_token(str(viewer.id), {'role': 'viewer'})}"
            },
            device_headers=[
                {"Authorization": f"Device {c.credential_id}:test-secret"}
                for c in credentials
            ],
        )
    db.close()
    engine.dispose()


def provider_url(core, provider_id="org.example.runtime", index=0):
    return f"/api/v1/devices/{core.devices[index].device_id}/capability-providers/native/{provider_id}"


def report(
    core,
    *,
    revision=0,
    capabilities=None,
    provider_id="org.example.runtime",
    index=0,
    version="0.1",
):
    return {
        "schema_version": 1,
        "device_id": core.devices[index].device_id,
        "provider_type": "native",
        "provider_id": provider_id,
        "provider_version": version,
        "expected_revision": revision,
        "capabilities": (
            capabilities
            if capabilities is not None
            else [
                {
                    "capability_id": "gpio.digital.control",
                    "metadata": {
                        "automation_channels": "gpio.output.1",
                        "automation_actions": "pulse",
                    },
                }
            ]
        ),
    }


def register(core, **kwargs):
    return core.client.put(
        provider_url(
            core,
            kwargs.get("provider_id", "org.example.runtime"),
            kwargs.get("index", 0),
        ),
        headers=core.device_headers[kwargs.get("index", 0)],
        json=report(core, **kwargs),
    )


def capabilities(core, index=0, version=2):
    return core.client.get(
        f"/api/v1/devices/{core.devices[index].device_id}/capabilities?registry_version={version}",
        headers=core.admin,
    )


def install_module(core, capability_id="gpio.digital.input", enabled=True):
    package = ModulePackage(
        module_id="org.example.module",
        version="1.0.0",
        manifest={},
        sha256="a" * 64,
        size_bytes=1,
        file_path="unused",
        registrations=[{"kind": "capability", "registration_id": capability_id}],
    )
    core.db.add(package)
    core.db.flush()
    installation = ModuleInstallation(
        device_id=core.devices[0].id,
        module_package_id=package.id,
        module_id=package.module_id,
        desired_version=package.version,
        status="succeeded",
        enabled=enabled,
    )
    core.db.add(installation)
    core.db.commit()
    return installation


@pytest.mark.parametrize("role", ["standalone", "hub", "node"])
def test_provider_uses_existing_command_and_state_contracts_without_packages_or_fleet(
    core, role
):
    device = core.devices[0]
    device.role = role
    core.db.commit()
    assert register(core).status_code == 200
    assert not core.db.scalars(select(ModulePackage)).all()
    assert not core.db.scalars(select(ModuleInstallation)).all()
    assert (
        capabilities(core, version=1).json() == []
    )  # Never fabricate a legacy module ID.
    rows = capabilities(core).json()
    assert rows[0]["provider_type"] == "native" and rows[0]["status"] == "active"
    assert rows[0]["capability_id"] == "gpio.digital.control"
    root = f"/api/v1/devices/{device.device_id}"
    queued = core.client.post(
        root + "/capabilities/invoke",
        headers=core.admin,
        json={
            "capability_id": "gpio.digital.control",
            "action": "pulse",
            "arguments": {"channel": "gpio.output.1"},
        },
    )
    assert queued.status_code == 200
    delivered = core.client.get(
        root + "/commands/next", headers=core.device_headers[0]
    ).json()
    assert delivered["command_type"] == "capability.invoke"
    assert delivered["payload"]["capability_id"] == "gpio.digital.control"
    finished = core.client.post(
        root + f"/commands/{delivered['command_id']}/result",
        headers=core.device_headers[0],
        json={
            "command_id": delivered["command_id"],
            "device_id": device.device_id,
            "status": "succeeded",
            "completed_at": datetime.now(UTC).isoformat(),
            "output": {"mock": True},
        },
    )
    assert finished.status_code == 200 and finished.json()["status"] == "succeeded"
    state_url = root + "/capabilities/gpio.digital.control/state"
    state = {
        "device_id": device.device_id,
        "capability_id": "gpio.digital.control",
        "observed_at": datetime.now(UTC).isoformat(),
        "values": {"gpio.output.1": False},
    }
    assert (
        core.client.post(
            state_url, headers=core.device_headers[0], json=state
        ).status_code
        == 200
    )
    assert (
        core.client.get(state_url, headers=core.admin).json()["values"]
        == state["values"]
    )
    before = (device.device_id, core.credentials[0].secret_hash)
    core.db.close()  # New session/reconnect keeps identity, credential and registry.
    replacement = Session(core.engine)
    try:
        restored = replacement.get(Device, device.id)
        assert (
            registered_capabilities(replacement, restored)[0]["provider_id"]
            == "org.example.runtime"
        )
        assert (
            restored.device_id,
            replacement.get(DeviceCredential, core.credentials[0].id).secret_hash,
        ) == before
    finally:
        replacement.close()


def test_legacy_view_and_builder_share_one_registry(core):
    module = install_module(core)
    assert register(core).status_code == 200
    assert capabilities(core, version=1).json() == [
        {
            "capability_id": "gpio.digital.input",
            "module_id": "org.example.module",
            "version": "1.0.0",
            "metadata": {},
        }
    ]
    assert {row["provider_type"] for row in capabilities(core).json()} == {
        "native",
        "agent_module",
    }
    context = build_automation_capability_context(core.db)
    assert context.context_version == 2
    assert len(context.capabilities) == 2
    assert "module_id" not in context.capabilities[0].model_dump()
    response = core.client.get("/api/ai/extensions/capabilities", headers=core.admin)
    assert response.status_code == 200 and response.json()["context_version"] == 2
    definition = AutomationDefinitionV1.model_validate(
        {
            "name": "example",
            "execution": "local",
            "trigger": {
                "device_id": core.devices[0].device_id,
                "capability_id": "gpio.digital.input",
                "event": "changed",
            },
            "actions": [
                {
                    "device_id": core.devices[0].device_id,
                    "capability_id": "gpio.digital.control",
                    "action": "pulse",
                    "arguments": {"channel": "gpio.output.1"},
                }
            ],
        }
    )
    assert validate_automation_capabilities(definition, context) == ()
    module.enabled = False
    core.db.commit()
    assert len(capabilities(core).json()) == 1


def test_revisions_retry_atomic_conflict_and_withdrawal(core):
    assert register(core).json()["revision"] == 1
    assert register(core).json()["revision"] == 1
    assert len(core.db.scalars(select(DeviceEvent)).all()) == 1
    assert register(core, revision=0, version="changed").status_code == 409
    collision = [{"capability_id": "other"}, {"capability_id": "gpio.digital.control"}]
    assert (
        register(core, provider_id="other.provider", capabilities=collision).status_code
        == 409
    )
    assert len(core.db.scalars(select(DeviceCapabilityProvider)).all()) == 1
    assert register(core, revision=1, capabilities=[]).json()["revision"] == 2
    assert capabilities(core).json() == []
    assert (
        register(core).status_code == 409
    )  # Old retry cannot resurrect a withdrawn capability.
    assert (
        core.client.get(provider_url(core), headers=core.device_headers[0]).json()[
            "revision"
        ]
        == 2
    )


def test_disable_survives_new_device_report_and_clears_stale_state(core):
    register(core)
    core.db.add(
        DeviceCapabilityState(
            device_id=core.devices[0].id,
            capability_id="gpio.digital.control",
            values={"old": True},
            observed_at=datetime.now(UTC),
        )
    )
    core.db.commit()
    disabled = core.client.post(
        provider_url(core) + "/enabled",
        headers=core.admin,
        json={"expected_revision": 1, "enabled": False},
    )
    assert disabled.status_code == 200 and disabled.json()["revision"] == 2
    assert not core.db.scalars(select(DeviceCapabilityState)).all()
    updated = register(core, revision=2, version="0.2")
    assert updated.status_code == 200 and updated.json()["enabled"] is False
    assert capabilities(core).json() == []
    assert register(core, provider_id="bypass").status_code == 409
    enabled = core.client.post(
        provider_url(core) + "/enabled",
        headers=core.admin,
        json={"expected_revision": 3, "enabled": True},
    )
    assert enabled.json()["revision"] == 4
    assert len(core.db.scalars(select(AuditLog)).all()) == 2
    assert (
        core.client.get(
            f"/api/v1/devices/{core.devices[0].device_id}/capabilities/gpio.digital.control/state",
            headers=core.admin,
        ).status_code
        == 404
    )


def test_conflicting_later_module_activation_fails_closed(core):
    register(core)
    module = install_module(core, "gpio.digital.control")
    assert capabilities(core).json() == []
    assert capabilities(core, version=1).json() == []
    module.enabled = False
    core.db.commit()
    assert capabilities(core).json()[0]["provider_type"] == "native"


def test_device_identity_credentials_roles_and_module_spoofing_are_enforced(core):
    body = report(core)
    assert core.client.put(provider_url(core), json=body).status_code == 401
    assert (
        core.client.put(
            provider_url(core), headers=core.device_headers[1], json=body
        ).status_code
        == 403
    )
    assert (
        core.client.put(provider_url(core), headers=core.admin, json=body).status_code
        == 401
    )
    spoof = {**body, "provider_type": "agent_module"}
    assert (
        core.client.put(
            provider_url(core).replace("/native/", "/agent_module/"),
            headers=core.device_headers[0],
            json=spoof,
        ).status_code
        == 422
    )
    assert (
        core.client.get(
            f"/api/v1/devices/{core.devices[0].device_id}/capabilities?registry_version=2",
            headers=core.viewer,
        ).status_code
        == 403
    )
    register(core)
    assert (
        core.client.post(
            provider_url(core) + "/enabled",
            headers=core.viewer,
            json={"expected_revision": 1, "enabled": False},
        ).status_code
        == 403
    )
    assert (
        core.client.post(
            provider_url(core) + "/enabled",
            headers=core.device_headers[0],
            json={"expected_revision": 1, "enabled": False},
        ).status_code
        == 401
    )
    core.credentials[0].revoked_at = datetime.now(UTC)
    core.db.commit()
    assert register(core, revision=1).status_code == 401
    core.devices[0].revoked_at = datetime.now(UTC)
    core.db.commit()
    assert capabilities(core).json() == []


def test_module_ownership_and_device_provider_limits(core):
    install_module(core, "gpio.digital.control")
    assert register(core).status_code == 409
    for i in range(16):
        assert (
            register(core, provider_id=f"provider.{i}", capabilities=[]).status_code
            == 200
        )
    assert (
        register(core, provider_id="provider.overflow", capabilities=[]).status_code
        == 409
    )


def test_replacement_version_change_clears_state_and_total_capability_quota(core):
    for i in range(4):
        assert (
            register(
                core,
                provider_id=f"p.{i}",
                capabilities=[{"capability_id": f"cap.{i}.{j}"} for j in range(64)],
            ).status_code
            == 200
        )
    assert (
        register(
            core, provider_id="p.overflow", capabilities=[{"capability_id": "overflow"}]
        ).status_code
        == 409
    )
    core.db.add(
        DeviceCapabilityState(
            device_id=core.devices[0].id,
            capability_id="cap.0.0",
            values={"old": True},
            observed_at=datetime.now(UTC),
        )
    )
    core.db.commit()
    update = register(
        core,
        provider_id="p.0",
        revision=1,
        version="0.2",
        capabilities=[{"capability_id": "replacement"}],
    )
    assert update.json()["revision"] == 2
    assert not core.db.scalars(select(DeviceCapabilityState)).all()
    assert (
        register(
            core, provider_id="p.overflow", capabilities=[{"capability_id": "overflow"}]
        ).status_code
        == 200
    )


def test_path_body_mismatch_and_stale_admin_control_cannot_change_provider(core):
    assert (
        core.client.put(
            provider_url(core),
            headers=core.device_headers[0],
            json=report(core, provider_id="mismatch"),
        ).status_code
        == 409
    )
    assert (
        core.client.put(
            provider_url(core),
            headers=core.device_headers[0],
            json=report(core, index=1),
        ).status_code
        == 403
    )
    register(core)
    assert (
        core.client.post(
            provider_url(core) + "/enabled",
            headers=core.admin,
            json={"expected_revision": 0, "enabled": False},
        ).status_code
        == 409
    )
    assert capabilities(core).json()[0]["status"] == "active"


def test_admin_can_inspect_disabled_provider_revision_without_device_credentials(core):
    register(core)
    core.client.post(
        provider_url(core) + "/enabled",
        headers=core.admin,
        json={"expected_revision": 1, "enabled": False},
    )
    url = f"/api/v1/devices/{core.devices[0].device_id}/capability-providers"
    response = core.client.get(url, headers=core.admin)
    assert response.status_code == 200
    assert (
        response.json()[0]["revision"] == 2 and response.json()[0]["enabled"] is False
    )
    assert response.json()[0]["reported_at"].endswith("Z")
    assert core.client.get(url, headers=core.viewer).status_code == 403
    assert core.client.get(url, headers=core.device_headers[0]).status_code == 401


def test_local_module_and_another_nodes_firmware_share_core_context(core):
    install_module(core, "gpio.digital.control")
    assert register(core, index=1).status_code == 200
    context = build_automation_capability_context(core.db)
    assert {(row.device_id, row.provider_type) for row in context.capabilities} == {
        (core.devices[0].device_id, "agent_module"),
        (core.devices[1].device_id, "native"),
    }
    assert (
        capabilities(core, index=0).json()[0]["capability_id"] == "gpio.digital.control"
    )
    assert (
        capabilities(core, index=1).json()[0]["capability_id"] == "gpio.digital.control"
    )
    assert (
        core.client.get(
            provider_url(core, index=1), headers=core.device_headers[0]
        ).status_code
        == 403
    )
