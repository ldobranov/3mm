"""C14: common configuration/health semantics without Fleet or real hardware."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from backend.tests.test_capability_contracts import (
    core,
    pair,
    application,
    request,
)  # noqa: F401
from backend.tests.test_migration_history import _alembic
from backend.db.device import (
    Device,
    DeviceCapabilityProvider,
    DeviceCapabilityHealth,
    DeviceHeartbeat,
    DeviceCommand,
)
from backend.services.device_capability_registry import (
    registered_capabilities,
    has_registered_capability,
    capability_catalog,
)
from backend.services.device_commands import (
    queue_command,
    deliver_next_command,
    DeviceCommandError,
)
from backend.services.application_commands import submit_command, authorize_execution
from backend.services.device_protocol import DeviceOperations, authenticate_device
from examples.mock_embedded.client import MockEmbeddedClient, CAPABILITY, PROVIDER
from examples.mock_embedded.contracts import control_contract
from backend.tests.test_mock_embedded_protocol import approve, ORIGIN
from three_mm_protocol import AgentHeartbeat
from three_mm_protocol.capability_availability import CapabilityAvailabilityReportV1


def snapshot(client, admin, prefix):
    response = client.get(prefix + "/capabilities?registry_version=3", headers=admin)
    assert response.status_code == 200, response.text
    return response.json()


def select_capabilities(client, admin, prefix, revision, ids):
    return client.post(
        prefix + f"/capability-providers/embedded_firmware/{PROVIDER}/configuration",
        headers=admin,
        json={"expected_revision": revision, "capability_ids": ids},
    )


@pytest.mark.parametrize("role", ["standalone", "hub"])
def test_explicit_discovery_configuration_health_and_same_application(
    pair, tmp_path, role
):
    core, _, local, publisher, runtime, gpio, _ = pair
    client, db, admin, viewer, transport = core
    local.role = role
    db.commit()
    publisher.capability_availability = True
    publisher._runtime_features._last_check = float("-inf")
    publisher._negotiated_inventory_version()
    publisher.transport.publish(
        AgentHeartbeat(
            device_id=local.device_id, sent_at=datetime.now(UTC), uptime_seconds=1
        )
    )
    publisher._publish_capability_availability()
    assert any(
        row.available is True
        for row in capability_catalog(db, local)
        if row.capability_id == CAPABILITY
    )
    node = MockEmbeddedClient(
        ORIGIN,
        tmp_path / "explicit",
        transport=transport,
        contract=control_contract(),
        explicit_capabilities=True,
    )
    try:
        approve(core, node)
        assert node.tick() == "approved"
        firmware = db.scalar(select(Device).where(Device.device_id == node.device_id))
        row = snapshot(client, admin, node.prefix)[0]
        assert row["supported"] and not row["registered"] and row["available"] is False
        assert not has_registered_capability(db, firmware, CAPABILITY)
        app = application(db, tmp_path, node.device_id)
        with pytest.raises(ValueError):
            submit_command(db, app, request("unconfigured"))
        assert (
            select_capabilities(
                client, viewer, node.prefix, 1, [CAPABILITY]
            ).status_code
            == 403
        )
        assert (
            select_capabilities(client, admin, node.prefix, 0, [CAPABILITY]).status_code
            == 409
        )
        assert (
            select_capabilities(
                client, admin, node.prefix, 1, ["inventory.fake"]
            ).status_code
            == 409
        )
        assert select_capabilities(client, admin, node.prefix, 1, [CAPABILITY]).json()[
            "configured_capability_ids"
        ] == [CAPABILITY]
        assert node.tick() == "approved"
        assert snapshot(client, admin, node.prefix)[0]["available"] is True
        for target, execute in (
            (local.device_id, publisher._poll_command),
            (node.device_id, node.poll),
        ):
            app.configuration = {"OUTPUT_DEVICE_ID": target}
            db.commit()
            submitted = submit_command(db, app, request(target))
            execute()
            node.flush()
            command = db.scalar(
                select(DeviceCommand).where(
                    DeviceCommand.command_id == submitted["command_id"]
                )
            )
            assert (
                command.status == "succeeded"
                and command.result["execution_state"] == "executed"
            )
        identity = node.identity.copy()
        node.close()
        node = MockEmbeddedClient(
            ORIGIN,
            tmp_path / "explicit",
            transport=transport,
            contract=control_contract(),
            explicit_capabilities=True,
        )
        assert node.identity == identity and node.tick() == "approved"
        assert has_registered_capability(db, firmware, CAPABILITY)
    finally:
        node.close()


def test_offline_unhealthy_expired_health_defer_only_new_work(pair, tmp_path):
    core, node, device, publisher, runtime, _, _ = pair
    client, db, admin, *_ = core
    publisher.capability_availability = True
    publisher._runtime_features._last_check = float("-inf")
    publisher._negotiated_inventory_version()
    app = application(db, tmp_path, device.device_id)
    submitted = submit_command(db, app, request("deferred"))
    command = db.scalar(
        select(DeviceCommand).where(DeviceCommand.command_id == submitted["command_id"])
    )
    assert deliver_next_command(db, device=device) is None
    assert command.status == "queued" and command.delivery_attempts == 0
    assert has_registered_capability(db, device, CAPABILITY)
    assert (
        next(
            row
            for row in capability_catalog(db, device)
            if row.capability_id == CAPABILITY
        ).unavailable_reason
        == "device_offline"
    )
    publisher.transport.publish(
        AgentHeartbeat(
            device_id=device.device_id, sent_at=datetime.now(UTC), uptime_seconds=1
        )
    )
    publisher._publish_capability_availability()
    health = db.scalar(
        select(DeviceCapabilityHealth).where(
            DeviceCapabilityHealth.device_id == device.id
        )
    )
    health.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert deliver_next_command(db, device=device) is None
    assert (
        next(
            row
            for row in capability_catalog(db, device)
            if row.capability_id == CAPABILITY
        ).unavailable_reason
        == "health_stale"
    )
    publisher._publish_capability_availability()
    delivered = deliver_next_command(db, device=device)
    assert delivered.command_id == submitted["command_id"]
    # A state value of False is a valid measurement, never a health signal.
    assert runtime.capability_healthy(CAPABILITY)
    service = runtime._services[CAPABILITY]
    service.is_available = lambda: False
    publisher._publish_capability_availability()
    when = delivered.delivered_at
    with pytest.raises(ValueError, match="temporarily unavailable"):
        authorize_execution(db, device, delivered.command_id)
    db.rollback()
    db.refresh(delivered)
    assert delivered.status == "delivered" and delivered.delivered_at == when
    assert has_registered_capability(db, device, CAPABILITY)
    service.is_available = lambda: True
    publisher._publish_capability_availability()
    assert authorize_execution(db, device, delivered.command_id)["authorized"] is True


def test_inventory_spoof_firmware_addition_and_no_device_configuration_authority(pair):
    core, node, *_ = pair
    client, db, admin, _, transport = core
    node.explicit_capabilities = True
    node.negotiate()
    provider = node.register_capability()  # Opt-in preserves the existing v1 selection.
    assert provider.configured_capability_ids == (CAPABILITY,)
    body = provider.model_dump(
        mode="json",
        exclude={"revision", "enabled", "reported_at", "configured_capability_ids"},
    )
    body["expected_revision"] = provider.revision
    body["provider_version"] = "0.3.0"
    body["capabilities"].append({"capability_id": "new.action"})
    path = node.prefix + f"/capability-providers/embedded_firmware/{PROVIDER}"
    updated = client.put(
        path,
        headers={
            "Authorization": f"Device {node.identity['credential_id']}:{node.identity['secret']}"
        },
        json=body,
    )
    assert updated.status_code == 200, updated.text
    firmware = db.scalar(select(Device).where(Device.device_id == node.device_id))
    assert has_registered_capability(db, firmware, CAPABILITY)
    assert not has_registered_capability(db, firmware, "new.action")
    catalog = {
        row["capability_id"]: row for row in snapshot(client, admin, node.prefix)
    }
    assert (
        catalog["new.action"]["supported"] and not catalog["new.action"]["registered"]
    )
    # Supported inventory never creates registration, even through the raw queue.
    inventory = client.get(node.prefix, headers=admin).json()["latest_inventory"]
    inventory["capabilities"].append("inventory.fake")
    headers = {
        "Authorization": f"Device {node.identity['credential_id']}:{node.identity['secret']}"
    }
    assert (
        client.post(
            node.prefix + "/inventory", headers=headers, json=inventory
        ).status_code
        == 202
    )
    assert any(
        row["unavailable_reason"] == "inventory_only"
        for row in snapshot(client, admin, node.prefix)
    )
    for capability in ("new.action", "inventory.fake"):
        response = client.post(
            node.prefix + "/commands",
            headers=admin,
            json={
                "command_type": "capability.invoke",
                "payload": {
                    "capability_id": capability,
                    "action": "set",
                    "arguments": {},
                },
                "idempotency_key": capability,
            },
        )
        assert response.status_code == 409
    assert (
        client.post(
            path + "/configuration",
            headers=headers,
            json={
                "expected_revision": updated.json()["revision"],
                "capability_ids": [CAPABILITY, "new.action"],
            },
        ).status_code
        == 401
    )
    # Older report format cannot bypass Core-owned mode or the selected set.
    body["schema_version"] = 1
    body["expected_revision"] = updated.json()["revision"]
    assert client.put(path, headers=headers, json=body).json()[
        "configured_capability_ids"
    ] == [CAPABILITY]
    # Core-owned mode also survives withdrawal of the runtime feature and a
    # new provider identity; old wire format cannot activate fresh offers.
    from backend.services.device_runtime_features import read_runtime_features

    runtime = read_runtime_features(db, firmware)
    runtime.declaration = {
        **runtime.declaration,
        "features": [
            item
            for item in runtime.declaration["features"]
            if item != "capability_availability.v1"
        ],
    }
    db.commit()
    bypass = {
        **body,
        "provider_id": "bypass.provider",
        "expected_revision": 0,
        "capabilities": [{"capability_id": "bypass.action"}],
    }
    response = client.put(
        node.prefix + "/capability-providers/embedded_firmware/bypass.provider",
        headers=headers,
        json=bypass,
    )
    assert response.status_code == 200, response.text
    assert response.json()["configured_capability_ids"] == []
    assert not has_registered_capability(db, firmware, "bypass.action")


def test_health_identity_declaration_bounds_replay_and_non_http_service(pair):
    core, node, device, publisher, runtime, _, _ = pair
    client, db, admin, viewer, _ = core
    report = next(runtime.availability_reports(device.device_id))
    payload = report.model_dump(mode="json")
    path = f"/api/v1/devices/{device.device_id}/capability-availability"
    headers = publisher.headers
    assert client.post(path, json=payload).status_code == 401
    assert client.post(path, headers=admin, json=payload).status_code == 401
    other = {
        "Authorization": f"Device {node.identity['credential_id']}:{node.identity['secret']}"
    }
    assert client.post(path, headers=other, json=payload).status_code == 403
    for field, value in (
        ("declaration_digest", "0" * 64),
        ("provider_version", "wrong"),
    ):
        assert (
            client.post(
                path, headers=headers, json={**payload, field: value}
            ).status_code
            == 409
        )
    assert (
        client.post(
            path,
            headers=headers,
            json={
                **payload,
                "observed_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            },
        ).status_code
        == 409
    )
    for value in (0, 301, True):
        with pytest.raises(ValidationError):
            CapabilityAvailabilityReportV1.model_validate(
                {**payload, "valid_for_seconds": value}
            )
    # Same logical message/services without HTTP, plus retry without lease extension.
    operations = DeviceOperations(
        db,
        authenticate_device(
            db,
            publisher.credential.credential_id,
            publisher.credential.credential_secret,
        ),
    )
    health = operations.availability(report)
    expires = health.expires_at
    operations.availability(report)
    assert health.expires_at == expires
    conflicting = deepcopy(payload)
    conflicting["capabilities"][0]["healthy"] = False
    assert client.post(path, headers=headers, json=conflicting).status_code == 409
    assert (
        client.get(
            f"/api/v1/devices/{device.device_id}/capabilities?registry_version=3",
            headers=viewer,
        ).status_code
        == 403
    )


def test_c14_populated_migration_preserves_legacy_and_refuses_unsafe_downgrade(
    tmp_path,
):
    url = f"sqlite:///{(tmp_path / 'c14.db').as_posix()}"
    _alembic(url, "upgrade", "859de4f5a6b7")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO devices(id,device_id,role,protocol_version,approved_at) VALUES (1,:d,'node','1.0','2026-10-03')"
            ),
            {"d": "dev_" + "1" * 32},
        )
        connection.execute(
            text(
                "INSERT INTO device_capability_providers(device_id,provider_type,provider_id,provider_version,revision,enabled,capabilities,reported_at) VALUES (1,'native','test','0.1',3,1,:c,'2026-10-03')"
            ),
            {"c": '[{"capability_id":"test.action","metadata":{}}]'},
        )
        before = connection.execute(
            text(
                "SELECT device_id,provider_type,provider_id,provider_version,revision,enabled,capabilities,reported_at FROM device_capability_providers"
            )
        ).all()
    engine.dispose()
    _alembic(url, "upgrade", "head")
    _alembic(url, "check")
    engine = create_engine(url)
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT device_id,provider_type,provider_id,provider_version,revision,enabled,capabilities,reported_at FROM device_capability_providers"
                )
            ).all()
            == before
        )
        assert (
            connection.execute(
                text(
                    "SELECT configured_capability_ids FROM device_capability_providers"
                )
            ).scalar()
            is None
        )
    with Session(engine) as db:
        assert (
            registered_capabilities(db, db.get(Device, 1))[0]["capability_id"]
            == "test.action"
        )
    engine.dispose()
    _alembic(url, "downgrade", "859de4f5a6b7")
    _alembic(url, "upgrade", "head")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE device_capability_providers SET configured_capability_ids='[]'"
            )
        )
    engine.dispose()
    import subprocess

    with pytest.raises(subprocess.CalledProcessError):
        _alembic(url, "downgrade", "859de4f5a6b7")
