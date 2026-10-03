"""C8 historic persisted rows fail closed while remaining recoverable."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from backend.db.device import Device, DeviceCommand, DeviceState
from backend.tests.test_mock_embedded_protocol import (
    ORIGIN,
    MockEmbeddedClient,
    approve,
    core,
)  # noqa: F401
from three_mm_protocol.node_security import NODE_MESSAGE_BYTES


def test_legacy_linux_wire_and_firmware_provider_share_updated_core(
    core, monkeypatch, tmp_path
):
    from backend.tests import test_mock_embedded_protocol as reference
    from backend.services.device_runtime_features import runtime_features_snapshot

    original = reference.CorePublisher

    def legacy_publisher(**kwargs):
        return original(
            **(kwargs | {"feature_negotiation": False, "inventory_schema_version": 1})
        )

    monkeypatch.setattr(reference, "CorePublisher", legacy_publisher)
    # Reuse the actual HTTP/module/driver coexistence flow with its legacy wire
    # adapter. This is not execution of a separately packaged historic release.
    reference.test_linux_local_agent_and_embedded_node_share_core_without_fleet(
        core, monkeypatch, tmp_path, "standalone"
    )
    _, db, *_ = core
    local = db.query(Device).filter_by(role="standalone").one()
    assert runtime_features_snapshot(db, local).source == "legacy_unadvertised"


def test_historical_large_state_remains_preserved_and_can_be_repaired_explicitly(
    core, tmp_path
):
    client, db, admin, _, transport = core
    node = MockEmbeddedClient(ORIGIN, tmp_path, transport=transport)
    try:
        approve(core, node)
        device = db.scalar(select(Device).where(Device.device_id == node.device_id))
        original = {"historical": "x" * NODE_MESSAGE_BYTES}
        row = DeviceState(
            device_id=device.id,
            desired_revision=7,
            desired_state=original,
            reported_revision=6,
        )
        db.add(row)
        db.commit()
        for response in (
            node._request("GET", node.prefix + "/desired-state"),
            client.get(node.prefix + "/state", headers=admin),
        ):
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "stored_desired_state_invalid"
            assert response.json()["detail"]["revision"] == 7
        db.refresh(row)
        assert row.desired_state == original and row.desired_revision == 7
        repaired = client.put(
            node.prefix + "/desired-state",
            headers=admin,
            json={"expected_revision": 7, "state": {"inventory_generation": 3}},
        )
        assert repaired.status_code == 200 and repaired.json()["revision"] == 8
        assert node._request("GET", node.prefix + "/desired-state").status_code == 200
    finally:
        node.close()


@pytest.mark.parametrize("already_delivered", [False, True])
def test_historical_invalid_command_preserves_dispatch_evidence(
    core, tmp_path, already_delivered
):
    client, db, admin, _, transport = core
    node = MockEmbeddedClient(ORIGIN, tmp_path, transport=transport)
    try:
        approve(core, node)
        device = db.scalar(select(Device).where(Device.device_id == node.device_id))
        now = datetime.now(UTC)
        payload = {"historical": "x" * NODE_MESSAGE_BYTES}
        row = DeviceCommand(
            device_id=device.id,
            command_id="cmd_" + "a" * 32,
            command_type="capability.invoke",
            idempotency_key="legacy",
            payload=payload,
            status="delivered" if already_delivered else "queued",
            created_at=now,
            expires_at=now + timedelta(seconds=300),
            delivered_at=now - timedelta(seconds=31) if already_delivered else None,
            delivery_attempts=1 if already_delivered else 0,
        )
        db.add(row)
        db.commit()
        response = node._request("GET", node.prefix + "/commands/next")
        assert response.status_code == 409
        db.refresh(row)
        assert row.payload == payload and row.delivery_attempts == int(
            already_delivered
        )
        if already_delivered:
            assert row.status == "delivered" and row.result is None
        else:
            assert (
                row.status == "failed"
                and row.result["execution_state"] == "not_dispatched"
            )
            assert row.delivered_at is None
            assert (
                node._request("GET", node.prefix + "/commands/next").status_code == 204
            )
        history = client.get(node.prefix + "/commands", headers=admin).json()["items"][
            0
        ]
        assert (
            history["command_id"] == row.command_id and history["status"] == row.status
        )
    finally:
        node.close()
