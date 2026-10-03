from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from three_mm_protocol import (
    AgentCommand,
    AgentCommandResult,
    AgentReportedState,
    CapabilityStateReportV1,
    DeviceEventV1,
)
from three_mm_protocol.node_security import (
    NODE_MESSAGE_BYTES,
    MODULE_ARCHIVE_BYTES,
    validate_node_json,
    validate_command_payload,
)


@pytest.mark.parametrize(
    "value",
    [
        {"value": float("nan")},
        {"value": float("inf")},
        {1: "wrong key"},
        {"value": "ж" * NODE_MESSAGE_BYTES},
        {"values": list(range(8193))},
    ],
)
def test_bounded_json_rejects_nonfinite_and_excessive_messages(value):
    with pytest.raises(ValueError):
        validate_node_json(value)


def test_depth_limit_and_unicode_exact_byte_boundary():
    value = "ok"
    for _ in range(17):
        value = [value]
    with pytest.raises(ValueError, match="structure"):
        validate_node_json(value)
    validate_node_json("ж", max_bytes=4)  # UTF-8 + two JSON quotes.
    with pytest.raises(ValueError, match="byte"):
        validate_node_json("ж", max_bytes=3)


def test_module_blob_exception_is_bounded_and_not_an_arbitrary_large_payload():
    from backend.services.module_packages import MAX_PACKAGE_BYTES

    assert MODULE_ARCHIVE_BYTES == MAX_PACKAGE_BYTES
    package = "a" * (NODE_MESSAGE_BYTES + 1)
    validate_command_payload(
        "module.install", {"package_base64": package, "sha256": "a" * 64}
    )
    for kind, payload in [
        ("capability.invoke", {"package_base64": package}),
        ("module.install", {"package_base64": package, "other": package}),
        ("module.install", {"package_base64": "a" * (14 * 1024 * 1024)}),
    ]:
        with pytest.raises(ValueError):
            validate_command_payload(kind, payload)


@pytest.mark.parametrize("times", ["naive", "inverted", "too_long"])
def test_command_deadline_must_be_aware_positive_and_bounded(times):
    now = datetime.now(UTC)
    start, end = now, now + timedelta(seconds=30)
    if times == "naive":
        start = start.replace(tzinfo=None)
    if times == "inverted":
        end = now
    if times == "too_long":
        end = now + timedelta(days=2)
    with pytest.raises(ValidationError):
        AgentCommand(
            device_id="dev_" + "1" * 32,
            command_id="cmd_" + "2" * 32,
            command_type="capability.invoke",
            idempotency_key="one",
            created_at=start,
            expires_at=end,
        )


@pytest.mark.parametrize("kind", ["event", "result", "reported", "capability"])
def test_payload_limits_apply_to_all_common_report_envelopes(kind):
    values = {"value": "x" * NODE_MESSAGE_BYTES}
    now = datetime.now(UTC)
    common = {"device_id": "dev_" + "1" * 32}
    with pytest.raises(ValidationError):
        if kind == "event":
            DeviceEventV1(
                **common,
                event_id="evt_" + "2" * 32,
                event_type="test.changed",
                payload=values,
                occurred_at=now,
            )
        if kind == "result":
            AgentCommandResult(
                **common,
                command_id="cmd_" + "2" * 32,
                status="succeeded",
                completed_at=now,
                output=values,
            )
        if kind == "reported":
            AgentReportedState(
                **common,
                desired_revision=0,
                applied_revision=0,
                state=values,
                reported_at=now,
            )
        if kind == "capability":
            CapabilityStateReportV1(
                **common,
                capability_id="gpio.digital.control",
                observed_at=now,
                values=values,
            )
