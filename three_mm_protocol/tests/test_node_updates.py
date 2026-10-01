from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from three_mm_protocol.node_updates import NodeUpdateApplyRequest


def request(**changes):
    now = datetime.now(UTC)
    return dict(operation_id="nodeupd_" + "a" * 32, device_id="dev_" + "b" * 32,
                release_id="v0.3.0-beta.25", archive_sha256="c" * 64,
                confirmed_install=True, created_at=now, expires_at=now + timedelta(seconds=30), **changes)


def test_node_update_request_is_round_trip_and_has_no_path_or_url():
    value = NodeUpdateApplyRequest.model_validate(request())
    assert NodeUpdateApplyRequest.model_validate_json(value.model_dump_json()) == value
    for field in ("path", "url", "command", "profile"):
        with pytest.raises(ValidationError):
            NodeUpdateApplyRequest.model_validate({**request(), field: "untrusted"})


@pytest.mark.parametrize("changes", [
    {"confirmed_install": False}, {"confirmed_install": "true"},
    {"confirmed_install": 1}, {"release_id": "../../outside"},
    {"operation_id": "nodeupd_../outside"}, {"archive_sha256": "0" * 63},
    {"device_id": "other"}, {"created_at": datetime(2026, 9, 30)},
])
def test_node_update_rejects_unsafe_payload(changes):
    with pytest.raises(ValidationError):
        NodeUpdateApplyRequest.model_validate({**request(), **changes})


@pytest.mark.parametrize("seconds", [0, -1, 121])
def test_node_update_handoff_is_bounded(seconds):
    payload = request()
    payload["expires_at"] = payload["created_at"] + timedelta(seconds=seconds)
    with pytest.raises(ValidationError):
        NodeUpdateApplyRequest.model_validate(payload)
