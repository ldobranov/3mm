import base64
import hashlib
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from three_mm_protocol.node_updates import (
    NodeUpdateApplyRequest, NodeUpdateApprovalKey, NodeUpdateAuthorization,
    canonical_node_update_authorization,
)


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


def test_signed_approval_round_trip_and_timezone_canonicalization():
    value = NodeUpdateApplyRequest.model_validate(request())
    key_id = "a" * 64
    authorization = NodeUpdateAuthorization(
        request=value, key_id=key_id, signature=base64.b64encode(b"s" * 64).decode(),
    )
    decoded = NodeUpdateAuthorization.model_validate_json(authorization.model_dump_json())
    offset = timezone(timedelta(hours=3))
    equivalent = NodeUpdateApplyRequest.model_validate({**value.model_dump(),
        "created_at": value.created_at.astimezone(offset),
        "expires_at": value.expires_at.astimezone(offset)})
    assert canonical_node_update_authorization(decoded.request, key_id) == canonical_node_update_authorization(equivalent, key_id)
    assert canonical_node_update_authorization(value, key_id).startswith(b"3mm.node-update.apply.v1\n")


def test_public_key_fingerprint_is_derived_and_signature_encoding_is_strict():
    raw_key = b"k" * 32
    public = {"key_id": hashlib.sha256(raw_key).hexdigest(),
              "public_key": base64.b64encode(raw_key).decode()}
    assert NodeUpdateApprovalKey.model_validate(public).algorithm == "ed25519"
    with pytest.raises(ValidationError):
        NodeUpdateApprovalKey.model_validate({**public, "key_id": "0" * 64})
    with pytest.raises(ValidationError):
        NodeUpdateAuthorization(request=NodeUpdateApplyRequest.model_validate(request()),
            key_id=public["key_id"], signature="!" * 88)
