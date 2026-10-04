"""C6/C7 security boundaries on the common Core, without Fleet or hardware."""

import ast
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select, update

from backend.db.device import (
    Device,
    DeviceCommand,
    DeviceCredential,
    DeviceEvent,
    DeviceState,
)
from backend.services.device_runtime_features import replace_runtime_features
from backend.tests.test_mock_embedded_protocol import (
    ORIGIN,
    MockEmbeddedClient,
    approve,
    core,
)  # noqa: F401
from backend.utils.device_auth import require_device
from backend.utils.device_body_limit import DeviceBodyLimitMiddleware
from three_mm_protocol import DeviceEventV1, DeviceRuntimeFeaturesReportV1
from three_mm_protocol.node_features import MANDATORY_NODE_FEATURES
from three_mm_protocol.node_security import NODE_MESSAGE_BYTES


@pytest.mark.parametrize("headers", [[], [(b"content-length", b"1")]])
def test_chunked_or_false_length_cannot_bypass_body_limit(headers):
    reached_app, sent = [], []
    chunks = iter(
        [
            {
                "type": "http.request",
                "body": b" " * NODE_MESSAGE_BYTES,
                "more_body": True,
            },
            {"type": "http.request", "body": b"x", "more_body": False},
        ]
    )

    async def receive():
        return next(chunks)

    async def send(message):
        sent.append(message)

    async def app(*_):
        reached_app.append(True)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/pairing/enroll",
        "headers": headers,
    }
    asyncio.run(DeviceBodyLimitMiddleware(app)(scope, receive, send))
    assert reached_app == [] and sent[0]["status"] == 413


@pytest.mark.parametrize(
    "path, method",
    [("/api/v1/devices/dev_test/events", "GET"), ("/api/v1/other", "POST")],
)
def test_body_limit_does_not_change_unrelated_contracts(path, method):
    reached_app = []

    async def app(*_):
        reached_app.append(True)

    async def unused(*_):
        pytest.fail("Unrelated body must not be consumed")

    asyncio.run(
        DeviceBodyLimitMiddleware(app)(
            {"type": "http", "method": method, "path": path}, unused, unused
        )
    )
    assert reached_app == [True]


@pytest.mark.parametrize(
    "body, status",
    [
        ('{"value":NaN}', 400),
        ('{"value":Infinity}', 400),
        ("[" * 18 + "0" + "]" * 18, 400),
        (" " * (NODE_MESSAGE_BYTES + 1), 413),
    ],
    ids=["nan", "infinity", "depth", "bytes"],
)
def test_invalid_json_rejected_before_enrollment_persistence(core, body, status):
    client, db, *_ = core
    client.app.add_middleware(DeviceBodyLimitMiddleware)
    response = client.post("/api/v1/pairing/enroll", content=body)
    assert response.status_code == status and db.query(Device).count() == 0


def test_module_blob_exception_and_desired_envelope_are_bounded(core, tmp_path):
    client, db, admin, _, transport = core
    client.app.add_middleware(DeviceBodyLimitMiddleware)
    node = MockEmbeddedClient(ORIGIN, tmp_path, transport=transport)
    try:
        approve(
            core, node
        )  # No feature declaration: retain legacy queue compatibility.
        blob = "a" * (NODE_MESSAGE_BYTES + 1)
        envelope = {
            "command_type": "module.install",
            "idempotency_key": "bounded-archive",
            "payload": {"package_base64": blob},
        }
        response = client.post(node.prefix + "/commands", headers=admin, json=envelope)
        assert response.status_code == 200, response.text
        # Only a module archive has the larger budget; metadata/ordinary work do not.
        ordinary = envelope | {
            "command_type": "capability.invoke",
            "idempotency_key": "not-archive",
        }
        assert (
            client.post(
                node.prefix + "/commands", headers=admin, json=ordinary
            ).status_code
            == 409
        )
        assert (
            client.post(
                node.prefix + "/commands",
                headers=admin,
                json=envelope
                | {
                    "idempotency_key": "metadata",
                    "payload": {"package_base64": blob, "other": blob},
                },
            ).status_code
            == 409
        )
        assert db.query(DeviceCommand).count() == 1
        # Inbound update fits, but the Node response includes extra identity/time.
        body = json.dumps(
            {
                "expected_revision": 0,
                "state": {"text": "x" * (NODE_MESSAGE_BYTES - 100)},
            },
            separators=(",", ":"),
        )
        assert len(body) < NODE_MESSAGE_BYTES
        response = client.put(
            node.prefix + "/desired-state",
            headers=admin | {"Content-Type": "application/json"},
            content=body,
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail, str), [item["msg"] for item in detail]
        assert detail == "Desired state exceeds the Node message contract"
        state = db.query(DeviceState).one()
        assert state.desired_revision == 0 and state.desired_state == {}
    finally:
        node.close()


@pytest.mark.parametrize(
    "event_type", ["runtime.features.updated", "capability.provider.updated"]
)
def test_node_cannot_forge_core_audit_events(core, tmp_path, event_type):
    client, db, _, _, transport = core
    node = MockEmbeddedClient(ORIGIN, tmp_path, transport=transport)
    try:
        approve(core, node)
        assert node.tick() == "approved"
        before = db.query(DeviceEvent).filter_by(event_type=event_type).count()
        report = DeviceEventV1(
            device_id=node.device_id,
            event_id="evt_" + "f" * 32,
            event_type=event_type,
            occurred_at=datetime.now(UTC),
            payload={"forged": True},
        )
        assert (
            node._request(
                "POST", node.prefix + "/events", report.model_dump(mode="json")
            ).status_code
            == 403
        )
        assert (
            db.query(DeviceEvent).filter_by(event_type=event_type).count()
            == before
            == 1
        )
    finally:
        node.close()


@pytest.mark.parametrize("target", [Device, DeviceCredential])
def test_revocation_refreshes_a_cached_orm_identity(core, tmp_path, target):
    _, db, _, _, transport = core
    node = MockEmbeddedClient(ORIGIN, tmp_path, transport=transport)
    try:
        approve(core, node)
        device = db.scalar(select(Device).where(Device.device_id == node.device_id))
        credential = db.scalar(
            select(DeviceCredential).where(DeviceCredential.device_id == device.id)
        )
        cached = device if target is Device else credential
        db.execute(
            update(target)
            .where(target.id == cached.id)
            .values(revoked_at=datetime.now(UTC))
            .execution_options(synchronize_session=False)
        )
        db.flush()
        assert (
            cached.revoked_at is None
        )  # Simulates a session with an old cached object.
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as rejected:
            require_device(
                f"Device {node.identity['credential_id']}:{node.identity['secret']}", db
            )
        assert rejected.value.status_code == 401
    finally:
        node.close()


def test_runtime_feature_service_rejects_another_device_identity(core, tmp_path):
    _, db, _, _, transport = core
    node = MockEmbeddedClient(ORIGIN, tmp_path, transport=transport)
    try:
        approve(core, node)
        device = db.scalar(select(Device).where(Device.device_id == node.device_id))
        report = DeviceRuntimeFeaturesReportV1(
            device_id="dev_" + "a" * 32,
            runtime_name="neutral",
            runtime_version="1",
            features=tuple(sorted(MANDATORY_NODE_FEATURES)),
            command_types=("capability.invoke",),
            expected_revision=0,
        )
        with pytest.raises(ValueError, match="identity"):
            replace_runtime_features(db, device, report)
    finally:
        node.close()


def test_neutral_contracts_have_no_runtime_driver_or_fleet_imports():
    root = Path(__file__).resolve().parents[2]
    files = [
        "three_mm_protocol/device_inventory.py",
        "three_mm_protocol/device_capabilities.py",
        "three_mm_protocol/node_features.py",
        "three_mm_protocol/node_security.py",
        "three_mm_protocol/device_platform.py",
        "three_mm_protocol/device_authority.py",
        "three_mm_protocol/capability_contracts.py",
        "three_mm_protocol/capability_availability.py",
        "backend/services/device_capability_registry.py",
        "backend/services/device_runtime_features.py",
        "backend/services/device_platform.py",
        "examples/mock_embedded/client.py",
    ]
    forbidden = {
        "agent",
        "three_mm_runtime",
        "three_mm_provisioning",
        "gpiozero",
        "lgpio",
        "RPi",
        "fleet",
    }
    for filename in files:
        tree = ast.parse((root / filename).read_text(encoding="utf-8"))
        for item in ast.walk(tree):
            imports = []
            if isinstance(item, ast.Import):
                imports = [alias.name for alias in item.names]
            elif isinstance(item, ast.ImportFrom):
                imports = [item.module or ""]
            assert not any(
                set(module.split(".")) & forbidden for module in imports
            ), filename
    main = ast.parse((root / "backend/main.py").read_text(encoding="utf-8"))
    assert any(
        isinstance(item, ast.Call)
        and isinstance(item.func, ast.Attribute)
        and item.func.attr == "add_middleware"
        and item.args
        and isinstance(item.args[0], ast.Name)
        and item.args[0].id == "DeviceBodyLimitMiddleware"
        for item in ast.walk(main)
    ), "The real Core app must enforce the common Node body contract"
