import base64
from datetime import UTC, datetime, timedelta
import shutil

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import pytest
from sqlalchemy import select

from backend.db.device import Device, DeviceCapabilityState, DeviceCommand, DeviceCredential, DeviceEvent, DeviceHeartbeat, DeviceState
from backend.db.device import DevicePlatformState
from backend.db.authority import CoreAuthorityGuard
from backend.routes.device_commands import router as command_router
from backend.services.device_pairing import credential_secret_hash
from backend.services.device_commands import DeviceCommandError, queue_command
from backend.services.device_capability_registry import replace_provider
from backend.services.node_update_approval import NodeApprovalError, approval_key_path, public_approval_key
from backend.tests.test_node_updates_route import DATA, DEVICE_ID, SHA, TAG, make_client
from backend.utils import jwt_utils
from three_mm_protocol.node_updates import NodeUpdateAuthorization, canonical_node_update_authorization
from three_mm_protocol import CapabilityProviderReportV1


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")
    client, db, engine, admin_token, viewer_token = make_client(tmp_path, monkeypatch)
    client.app.include_router(command_router)
    from backend.routes.node_updates import get_settings
    settings = get_settings()
    settings.updates.policy_file = tmp_path / "durable" / "update-policy.json"
    device = db.scalar(select(Device).where(Device.device_id == DEVICE_ID))
    key = public_approval_key(settings.updates)
    db.add_all([
        CoreAuthorityGuard(singleton_id=1),
        DevicePlatformState(device_id=device.id),
        DeviceHeartbeat(device_id=device.id, protocol_version="1.0", payload={}, received_at=datetime.now(UTC)),
        DeviceCredential(device_id=device.id, credential_id="cred_test", secret_hash=credential_secret_hash("test-secret")),
        DeviceState(device_id=device.id, reported_at=datetime.now(UTC), reported_state={"node_update": {
            "schema_version": 1, "signed_apply_supported": True, "approval_key_id": key.key_id,
            "trusted_device_id": DEVICE_ID,
        }}),
    ])
    db.commit()
    headers = {"Authorization": "Bearer " + admin_token}
    prepared = client.post(f"/api/v1/devices/{DEVICE_ID}/node-updates/prepare", json={}, headers=headers).json()["prepared"]
    preparation = db.scalar(select(DeviceCommand))
    preparation.status = "succeeded"
    preparation.result = {
        "operation_id": prepared["operation_id"], "release_id": TAG,
        "archive_sha256": SHA, "archive_size_bytes": len(DATA),
        "prepared_at": datetime.now(UTC).isoformat(),
    }
    db.commit()
    op = prepared["operation_id"]
    yield client, db, device, settings, headers, viewer_token, op
    db.close()
    engine.dispose()


def approve(setup):
    client, db, _device, _settings, headers, _viewer, op = setup
    response = client.post(f"/api/v1/devices/{DEVICE_ID}/node-updates/{op}/apply",
                           json={"confirmed_install": True}, headers=headers)
    assert response.status_code == 202, response.text
    command = db.scalar(select(DeviceCommand).where(DeviceCommand.command_type == "agent.update.apply"))
    return response, command


def outcome(op, status="running"):
    return {"operation_id": op, "device_id": DEVICE_ID, "release_id": TAG,
            "archive_sha256": SHA, "status": status, "updated_at": datetime.now(UTC).isoformat()}


def report(client, op, payload):
    return client.post(f"/api/v1/devices/{DEVICE_ID}/node-updates/{op}/report", json=payload,
                       headers={"Authorization": "Device cred_test:test-secret"})


def register_test_control(db, device):
    """Valid legacy capability work without adding GPIO/OTA prerequisites."""
    replace_provider(
        db, device, CapabilityProviderReportV1(
            schema_version=1,
            device_id=device.device_id,
            provider_type="native",
            provider_id="test.runtime",
            provider_version="1.0",
            expected_revision=0,
            capabilities=({"capability_id": "test.control"},),
        ),
    )
    db.commit()
    return {"capability_id": "test.control", "action": "set", "arguments": {"value": False}}


def test_admin_confirmation_and_exact_signed_original_deadline(setup):
    client, db, _device, _settings, headers, viewer, op = setup
    url = f"/api/v1/devices/{DEVICE_ID}/node-updates/{op}/apply"
    assert client.post(url, json={"confirmed_install": True}).status_code == 401
    assert client.post(url, json={"confirmed_install": True}, headers={"Authorization": "Bearer " + viewer}).status_code == 403
    for invalid in (False, "true", 1):
        assert client.post(url, json={"confirmed_install": invalid}, headers=headers).status_code == 422
    assert client.post(url, json={"confirmed_install": True, "url": "https://invalid.example"}, headers=headers).status_code == 422
    response, command = approve(setup)
    auth = NodeUpdateAuthorization.model_validate(command.payload)
    key = client.get("/api/v1/devices/node-updates/approval-key").json()
    Ed25519PublicKey.from_public_bytes(base64.b64decode(key["public_key"])).verify(
        base64.b64decode(auth.signature), canonical_node_update_authorization(auth.request, key["key_id"]),
    )
    assert "private" not in str(key)
    assert auth.request.created_at == command.created_at.replace(tzinfo=UTC)
    assert auth.request.expires_at == command.expires_at.replace(tzinfo=UTC)
    assert (auth.request.expires_at - auth.request.created_at).total_seconds() <= 120
    original = dict(command.payload)
    command.status = "expired"
    db.commit()
    replay = client.post(url, json={"confirmed_install": True}, headers=headers)
    assert replay.status_code == 202
    assert replay.json()["command_id"] == response.json()["command_id"]
    assert replay.json()["expires_at"] == response.json()["expires_at"]
    db.refresh(command)
    assert command.payload == original


def test_report_is_independent_of_handoff_and_history_survives_delivery_cleanup(setup):
    client, db, _device, settings, headers, _viewer, op = setup
    _response, command = approve(setup)
    command.status = "delivered"
    command.delivered_at = datetime.now(UTC)
    db.commit()
    final = outcome(op, "succeeded")
    assert report(client, op, final).status_code == 200
    handoff = client.post(f"/api/v1/devices/{DEVICE_ID}/commands/{command.command_id}/result",
        headers={"Authorization": "Device cred_test:test-secret"}, json={
            "command_id": command.command_id, "device_id": DEVICE_ID, "status": "succeeded",
            "completed_at": datetime.now(UTC).isoformat(),
            "output": {"operation_id": op, "handoff_status": "accepted"},
        })
    assert handoff.status_code == 200, handoff.text
    assert handoff.json()["result"]["operation"]["status"] == "succeeded"
    assert handoff.json()["result"]["handoff"]["handoff_status"] == "accepted"
    shutil.rmtree(settings.updates.staging_dir / "node-delivery" / op)
    history = client.get(f"/api/v1/devices/{DEVICE_ID}/node-updates/{op}", headers=headers)
    assert history.status_code == 200
    assert history.json()["installation"]["status"] == "succeeded"
    assert report(client, op, final).status_code == 200
    assert len(list(db.scalars(select(DeviceEvent)))) == 1
    assert report(client, op, outcome(op, "running")).status_code == 409


def test_report_requires_device_identity_and_an_exact_approved_operation(setup):
    client, db, device, _settings, _headers, _viewer, op = setup
    assert report(client, op, outcome(op)).status_code == 409
    approve(setup)
    wrong = outcome(op)
    wrong["device_id"] = "dev_" + "b" * 32
    assert report(client, op, wrong).status_code == 403
    wrong = outcome(op)
    wrong["archive_sha256"] = "0" * 64
    assert report(client, op, wrong).status_code == 409
    assert client.post(f"/api/v1/devices/{DEVICE_ID}/node-updates/{op}/report", json=outcome(op)).status_code == 401
    device.revoked_at = datetime.now(UTC)
    db.commit()
    assert report(client, op, outcome(op)).status_code == 401


def test_generic_unsigned_or_forged_apply_cannot_bypass_explicit_approval(setup):
    client, db, device, _settings, headers, _viewer, op = setup
    forged = NodeUpdateAuthorization(
        key_id="0" * 64, signature=base64.b64encode(b"x" * 64).decode(),
        request={"operation_id": op, "device_id": DEVICE_ID, "release_id": TAG,
                 "archive_sha256": SHA, "confirmed_install": True,
                 "created_at": datetime.now(UTC), "expires_at": datetime.now(UTC) + timedelta(seconds=60)},
    )
    db.add(DeviceCommand(device_id=device.id, command_id="cmd_" + "e" * 32,
        command_type="agent.update.apply", payload=forged.model_dump(mode="json"),
        idempotency_key="node-update-apply:" + op, status="queued",
        created_at=forged.request.created_at, expires_at=forged.request.expires_at))
    db.commit()
    response = client.post(f"/api/v1/devices/{DEVICE_ID}/node-updates/{op}/apply",
                           json={"confirmed_install": True}, headers=headers)
    assert response.status_code == 409
    assert report(client, op, outcome(op)).status_code == 409


@pytest.mark.parametrize("failure", [
    "unprepared", "archive_tampered", "expired", "offline",
    "missing_output", "active_output", "stale_output",
    "unconfirmed_apply", "unsupported", "wrong_key", "stale_support"
])
def test_apply_preconditions_fail_closed(setup, failure, monkeypatch):
    client, db, device, settings, headers, _viewer, op = setup
    if failure == "unprepared":
        db.scalar(select(DeviceCommand)).status = "delivered"
    elif failure == "archive_tampered":
        (settings.updates.staging_dir / "node-delivery" / op / "release.tar.gz").write_bytes(b"tampered")
    elif failure == "expired":
        metadata = settings.updates.staging_dir / "node-delivery" / op / "metadata.json"
        import json
        data = json.loads(metadata.read_text())
        data["prepared_at"] = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        data["expires_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        metadata.write_text(json.dumps(data))
    elif failure == "offline":
        db.scalar(select(DeviceHeartbeat)).received_at = datetime.now(UTC) - timedelta(minutes=3)
    elif failure in {"missing_output", "active_output", "stale_output"}:
        monkeypatch.setattr(
            "backend.services.node_update_execution.has_registered_capability",
            lambda *_args: True,
        )

        if failure != "missing_output":
            db.add(DeviceCapabilityState(
                device_id=device.id,
                capability_id="gpio.digital.control",
                values={
                    "gpio.output.1": failure == "active_output"
                },
                observed_at=datetime.now(UTC) - timedelta(
                    minutes=3
                    if failure == "stale_output"
                    else 0
                ),
            ))
    elif failure in {"unsupported", "wrong_key", "stale_support"}:
        state = db.scalar(select(DeviceState))
        if failure == "stale_support":
            state.reported_at = datetime.now(UTC) - timedelta(minutes=3)
        else:
            support = dict(state.reported_state["node_update"])
            support["signed_apply_supported" if failure == "unsupported" else "approval_key_id"] = False if failure == "unsupported" else "0" * 64
            state.reported_state = {"node_update": support}
    else:
        db.add(DeviceCommand(device_id=device.id, command_id="cmd_" + "d" * 32,
            command_type="agent.update.apply", payload={}, status="failed",
            idempotency_key="node-update-apply:nodeupd_" + "d" * 32,
            created_at=datetime.now(UTC), expires_at=datetime.now(UTC)))
    db.commit()
    response = client.post(f"/api/v1/devices/{DEVICE_ID}/node-updates/{op}/apply",
                           json={"confirmed_install": True}, headers=headers)
    assert response.status_code == 409, response.text
    assert db.scalar(select(DeviceCommand).where(
        DeviceCommand.idempotency_key == "node-update-apply:" + op,
    )) is None


def test_disabled_gpio_does_not_block_ota_with_stale_historical_state(setup):
    client, db, device, _settings, headers, _viewer, op = setup

    db.add(DeviceCapabilityState(
        device_id=device.id,
        capability_id="gpio.digital.control",
        values={"gpio.output.1": False},
        observed_at=datetime.now(UTC) - timedelta(hours=1),
    ))
    db.commit()

    response = client.post(
        f"/api/v1/devices/{DEVICE_ID}/node-updates/{op}/apply",
        json={"confirmed_install": True},
        headers=headers,
    )

    assert response.status_code == 202, response.text


def test_malformed_approval_identity_is_not_silently_replaced(setup):
    _client, _db, _device, settings, _headers, _viewer, _op = setup
    key = public_approval_key(settings.updates)
    assert public_approval_key(settings.updates) == key
    path = approval_key_path(settings.updates)
    path.write_bytes(b"malformed key")
    with pytest.raises(NodeApprovalError):
        public_approval_key(settings.updates)
    assert path.read_bytes() == b"malformed key"


def test_public_approval_key_works_through_actual_core_app_without_login(setup):
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.utils.db_utils import get_db
    _client, db, _device, settings, _headers, _viewer, _op = setup
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get("/api/v1/devices/node-updates/approval-key")
        assert response.status_code == 200, response.text
        assert response.json()["key_id"] == public_approval_key(settings.updates).key_id
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


@pytest.mark.parametrize("command_type", [
    "application.capability.invoke", "agent.gpio.configure", "module.install", "module.disable",
])
def test_pending_physical_or_configuration_work_blocks_ota(setup, command_type):
    client, db, device, _settings, headers, _viewer, op = setup
    payload = (
        register_test_control(db, device)
        if command_type == "application.capability.invoke" else {}
    )
    queue_command(db, device=device, command_type=command_type, payload=payload,
                  idempotency_key="pending", ttl_seconds=300)
    db.commit()
    response = client.post(f"/api/v1/devices/{DEVICE_ID}/node-updates/{op}/apply",
                           headers=headers, json={"confirmed_install": True})
    assert response.status_code == 409
    assert "pending physical commands" in response.text


def test_ota_gate_blocks_new_device_mutations_but_not_replay_and_releases_after_terminal(setup):
    client, db, device, _settings, _headers, _viewer, op = setup
    control_payload = register_test_control(db, device)
    previous = queue_command(db, device=device, command_type="gpio.write", payload={},
                             idempotency_key="previous", ttl_seconds=300)
    previous.status = "succeeded"
    db.commit()
    approve(setup)
    replay = queue_command(db, device=device, command_type="gpio.write", payload={},
                           idempotency_key="previous", ttl_seconds=300)
    assert replay.id == previous.id
    db.rollback()
    for command_type in ("gpio.write", "application.capability.invoke", "agent.gpio.configure", "module.install", "module.disable"):
        with pytest.raises(DeviceCommandError, match="device mutations are paused"):
            payload = (
                control_payload if command_type == "application.capability.invoke" else {}
            )
            queue_command(db, device=device, command_type=command_type, payload=payload,
                          idempotency_key="new-" + command_type, ttl_seconds=300)
        db.rollback()
    assert report(client, op, outcome(op, "succeeded")).status_code == 200
    command = queue_command(db, device=device, command_type="gpio.write", payload={},
                            idempotency_key="after-terminal", ttl_seconds=300)
    assert command.status == "queued"
    command = queue_command(
        db, device=device, command_type="application.capability.invoke",
        payload=control_payload, idempotency_key="capability-after-terminal",
        ttl_seconds=300,
    )
    assert command.status == "queued"
    db.rollback()


def test_unknown_outcome_stays_quarantined_until_newer_terminal_resolution(setup):
    client, _db, _device, _settings, _headers, _viewer, op = setup
    approve(setup)
    unknown = outcome(op, "unknown")
    assert report(client, op, unknown).status_code == 200
    assert report(client, op, unknown).status_code == 200
    assert report(client, op, outcome(op, "running")).status_code == 409
    assert report(client, op, outcome(op, "accepted")).status_code == 409
    assert report(client, op, outcome(op, "unknown")).status_code == 409
    assert report(client, op, outcome(op, "failed")).status_code == 200
