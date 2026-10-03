"""C4 required Core boundaries, without optional Fleet/module/update runtimes."""

from datetime import UTC, datetime

from pydantic import ValidationError
import pytest

from backend.db.device import DeviceCredential, DeviceEvent
from backend.db.module import ModuleInstallation, ModulePackage
from backend.routes.device_events import DeviceEventPayload
from backend.tests.test_mock_embedded_protocol import (
    CAPABILITY,
    CHANNEL,
    ORIGIN,
    MockEmbeddedClient,
    approve,
    core,
)  # noqa: F401 - common Core-only fixture
from three_mm_protocol import (
    AgentCommandResult,
    AgentHeartbeat,
    AgentReportedState,
    CapabilityProviderReportV1,
    CapabilityStateReportV1,
    DeviceEventV1,
    DeviceRuntimeFeaturesReportV1,
)
from three_mm_protocol.node_features import MANDATORY_NODE_FEATURES


def test_required_device_boundaries_share_auth_identity_and_revocation(core, tmp_path):
    client, db, admin, _, transport = core
    node = MockEmbeddedClient(ORIGIN, tmp_path / "node", transport=transport)
    other = MockEmbeddedClient(ORIGIN, tmp_path / "other", transport=transport)
    try:
        for device in (node, other):
            approve(core, device)
            assert device.tick() == "approved"
        now = datetime.now(UTC)
        provider_path = "/capability-providers/native/reference.runtime"
        boundaries = [
            ("GET", "/protocol", None),
            (
                "PUT",
                "/runtime-features",
                DeviceRuntimeFeaturesReportV1(
                    device_id=node.device_id,
                    runtime_name="reference",
                    runtime_version="1",
                    features=tuple(sorted(MANDATORY_NODE_FEATURES)),
                    command_types=("capability.invoke",),
                    expected_revision=1,
                ).model_dump(mode="json"),
            ),
            (
                "POST",
                "/heartbeat",
                AgentHeartbeat(
                    device_id=node.device_id, sent_at=now, uptime_seconds=1
                ).model_dump(mode="json"),
            ),
            (
                "POST",
                "/inventory",
                client.get(node.prefix, headers=admin).json()["latest_inventory"],
            ),
            ("GET", "/commands/next", None),
            (
                "POST",
                "/commands/" + "cmd_" + "c" * 32 + "/result",
                AgentCommandResult(
                    device_id=node.device_id,
                    command_id="cmd_" + "c" * 32,
                    status="failed",
                    completed_at=now,
                    error="Unknown command",
                ).model_dump(mode="json"),
            ),
            (
                "POST",
                "/events",
                DeviceEventV1(
                    device_id=node.device_id,
                    event_id="evt_" + "d" * 32,
                    event_type="reference.state.changed",
                    payload={"value": True},
                    occurred_at=now,
                ).model_dump(mode="json"),
            ),
            ("GET", "/desired-state", None),
            (
                "POST",
                "/reported-state",
                AgentReportedState(
                    device_id=node.device_id,
                    desired_revision=0,
                    applied_revision=0,
                    state={},
                    reported_at=now,
                ).model_dump(mode="json"),
            ),
            ("GET", provider_path, None),
            (
                "PUT",
                provider_path,
                CapabilityProviderReportV1(
                    schema_version=1,
                    device_id=node.device_id,
                    provider_type="native",
                    provider_id="reference.runtime",
                    provider_version="1.0",
                    expected_revision=0,
                    capabilities=(),
                ).model_dump(mode="json"),
            ),
            (
                "POST",
                f"/capabilities/{CAPABILITY}/state",
                CapabilityStateReportV1(
                    device_id=node.device_id,
                    capability_id=CAPABILITY,
                    values={CHANNEL: False},
                    observed_at=now,
                ).model_dump(mode="json"),
            ),
        ]
        headers = {
            "Authorization": f"Device {node.identity['credential_id']}:{node.identity['secret']}"
        }
        for method, suffix, payload in boundaries:
            for incorrect_auth in ({}, admin):
                assert (
                    client.request(
                        method,
                        node.prefix + suffix,
                        json=payload,
                        headers=incorrect_auth,
                    ).status_code
                    == 401
                )
            assert (
                client.request(
                    method, other.prefix + suffix, json=payload, headers=headers
                ).status_code
                == 403
            )
        assert (
            client.post(
                node.prefix + f"/credentials/{node.identity['credential_id']}/revoke",
                headers=admin,
            ).status_code
            == 200
        )
        for method, suffix, payload in boundaries:
            assert (
                client.request(
                    method, node.prefix + suffix, json=payload, headers=headers
                ).status_code
                == 401
            )
        assert db.query(DeviceCredential).count() == 2
        assert (
            db.query(ModuleInstallation).count() == db.query(ModulePackage).count() == 0
        )
    finally:
        node.close()
        other.close()


def test_optional_linux_operations_fail_without_breaking_required_node_flow(
    core, tmp_path
):
    client, db, admin, _, transport = core
    node = MockEmbeddedClient(ORIGIN, tmp_path, transport=transport)
    try:
        approve(core, node)
        assert node.tick() == "approved"
        for kind in (
            "module.install",
            "module.disable",
            "agent.update.prepare",
            "agent.update.apply",
            "automation.apply",
            "agent.gpio.configure",
        ):
            queued = client.post(
                node.prefix + "/commands",
                headers=admin,
                json={
                    "command_type": kind,
                    "idempotency_key": kind,
                    "payload": {},
                },
            )
            assert queued.status_code == 409
            assert node.poll() is None
        assert (
            client.get(node.prefix + "/commands", headers=admin).json()["items"] == []
        )
        assert node.tick() == "approved" and node.executions == 0
        assert (
            db.query(ModuleInstallation).count() == db.query(ModulePackage).count() == 0
        )
    finally:
        node.close()


def test_shared_event_envelope_preserves_core_validation_and_duplicate_contract(
    core, tmp_path
):
    client, db, admin, _, transport = core
    node = MockEmbeddedClient(ORIGIN, tmp_path, transport=transport)
    try:
        approve(core, node)
        report = DeviceEventV1(
            device_id=node.device_id,
            event_id="evt_" + "e" * 32,
            event_type="reference.changed",
            payload={"value": True},
            occurred_at=datetime.now(UTC),
        )
        payload = report.model_dump(mode="json")
        assert (
            DeviceEventPayload.model_validate(payload).model_dump(mode="json")
            == payload
        )
        assert (
            DeviceEventPayload.model_json_schema()["properties"]
            == DeviceEventV1.model_json_schema()["properties"]
        )
        first = node._request("POST", node.prefix + "/events", payload)
        assert first.status_code == 202 and first.json()["duplicate"] is False
        second = node._request("POST", node.prefix + "/events", payload)
        assert second.status_code == 202 and second.json()["duplicate"] is True
        assert (
            node._request(
                "POST", node.prefix + "/events", payload | {"payload": {"value": False}}
            ).status_code
            == 409
        )
        assert db.query(DeviceEvent).filter_by(event_id=report.event_id).count() == 1
        # Specific event contracts are still validated by Core, not just the envelope.
        with pytest.raises(ValidationError):
            DeviceEventPayload.model_validate(
                payload | {"event_type": "identifier.scan.v1"}
            )
        assert client.get(node.prefix + "/events", headers=admin).status_code == 200
    finally:
        node.close()
