from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from three_mm_protocol import IdentifierScanEventV1


def scan_event(**payload_changes):
    payload = {
        "schema_version": 1,
        "capability_id": "identifier.scan.v1",
        "opaque_identifier": "04A1B2C3D4",
        "reader_id": "reader.mock.1",
        "adapter_kind": "mock",
        "sequence": 1,
        "device_health": "ok",
        "scan_metadata": {"signal_dbm": -41},
    }
    payload.update(payload_changes)
    return {
        "event_id": "evt_0123456789abcdef0123456789abcdef",
        "device_id": "dev_0123456789abcdef0123456789abcdef",
        "event_type": "identifier.scan.v1",
        "payload": payload,
        "occurred_at": datetime.now(UTC),
    }


def test_identifier_scan_is_opaque_and_strict():
    event = IdentifierScanEventV1.model_validate(scan_event())

    assert event.payload.opaque_identifier == "04A1B2C3D4"
    assert event.payload.capability_id == event.event_type


@pytest.mark.parametrize(
    "changes",
    [
        {"opaque_identifier": " tag-with-space "},
        {"sequence": 0},
        {"person_name": "Not allowed"},
    ],
)
def test_identifier_scan_rejects_invalid_or_personal_fields(changes):
    with pytest.raises(ValidationError):
        IdentifierScanEventV1.model_validate(scan_event(**changes))


def test_identifier_scan_requires_timezone():
    value = scan_event()
    value["occurred_at"] = datetime.now()

    with pytest.raises(ValidationError, match="timezone"):
        IdentifierScanEventV1.model_validate(value)
