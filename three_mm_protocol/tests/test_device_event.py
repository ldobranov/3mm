from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from three_mm_protocol import DeviceEventV1


def event_payload():
    return {
        "event_id": "evt_" + "a" * 32,
        "device_id": "dev_" + "b" * 32,
        "event_type": "reference.state.changed",
        "payload": {"channel": "output.1", "value": True},
        "occurred_at": datetime.now(UTC).isoformat(),
    }


def test_generic_event_round_trip_has_no_linux_or_provider_fields():
    event = DeviceEventV1.model_validate(event_payload())
    assert DeviceEventV1.model_validate_json(event.model_dump_json()) == event
    assert set(event.model_dump()) == {
        "event_id",
        "device_id",
        "event_type",
        "payload",
        "occurred_at",
    }
    with pytest.raises(ValidationError):
        event.event_type = "changed"


@pytest.mark.parametrize(
    "changes",
    [
        {"event_id": "invalid"},
        {"device_id": "invalid"},
        {"event_type": ""},
        {"event_type": "x" * 121},
        {"payload": []},
        {"module_id": "unnecessary"},
        {"protocol_version": "1.0"},
    ],
)
def test_invalid_envelope_and_unversioned_extra_fields_are_rejected(changes):
    with pytest.raises(ValidationError):
        DeviceEventV1.model_validate(event_payload() | changes)


def test_default_payload_and_legacy_timestamp_shape_remain_compatible():
    values = event_payload()
    values.pop("payload")
    values["occurred_at"] = "2026-10-03T12:00:00"
    restored = DeviceEventV1.model_validate(values)
    assert restored.payload == {} and restored.occurred_at.tzinfo is None
