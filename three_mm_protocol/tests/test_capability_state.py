from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from three_mm_protocol import CapabilityStateReportV1


def test_capability_state_report_is_strict_and_serializable():
    report = CapabilityStateReportV1(
        device_id="dev_0123456789abcdef0123456789abcdef",
        capability_id="gpio.digital.input",
        values={"gpio.input.1": True},
        observed_at=datetime.now(UTC),
    )
    assert CapabilityStateReportV1.model_validate_json(report.model_dump_json()) == report


def test_capability_state_report_rejects_empty_values():
    with pytest.raises(ValidationError):
        CapabilityStateReportV1(
            device_id="dev_0123456789abcdef0123456789abcdef",
            capability_id="gpio.digital.input",
            values={},
            observed_at=datetime.now(UTC),
        )
