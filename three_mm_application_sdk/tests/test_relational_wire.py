"""Closed signed metadata; no production host session/transport substitute."""

import time

import pytest

from three_mm_application_sdk.relational_wire import (
    RelationalPermit,
    accept_permit,
    permit_digest,
    sign_metadata,
    verify_metadata,
)

SECRET = b"s" * 32
BINDINGS = {
    "transaction_id": "1" * 32,
    "mode": "write",
    "profile_sha256": "2" * 64,
    "instance_id": "3" * 24,
    "runtime_nonce": "4" * 32,
    "database_lineage": "5" * 32,
    "boot_id": "00000000-0000-0000-0000-000000000006",
    "authority_epoch": "7" * 32,
    "recovery_generation": "8" * 32,
    "binding_sha256": "9" * 64,
}


def permit(**changes):
    now = (
        time.clock_gettime_ns(time.CLOCK_BOOTTIME) // 1_000_000
        if hasattr(time, "CLOCK_BOOTTIME")
        else 1000
    )
    return sign_metadata(
        SECRET,
        "admission",
        {
            "version": 1,
            **BINDINGS,
            "grant_revision": 1,
            "issued_at_ms": now,
            "deadline_ms": now + 2000,
            **changes,
        },
    )


@pytest.mark.parametrize("version", [True, False, 1.0, "1", 0, 2, None])
def test_wire_version_is_exact_integer(version):
    with pytest.raises(ValueError):
        RelationalPermit.model_validate(permit(version=version))


@pytest.mark.parametrize(
    "changes",
    [
        {"extra": "SQL"},
        {"grant_revision": True},
        {"grant_revision": 0},
        {"deadline_ms": True},
        {"issued_at_ms": True},
        {"issued_at_ms": 1, "deadline_ms": 1},
        {"issued_at_ms": 1, "deadline_ms": 30002},
        {"mode": "migrate"},
        {"runtime_nonce": "bad"},
    ],
)
def test_closed_metadata_refuses_invalid_bounds_or_extra_payload(changes):
    with pytest.raises(ValueError):
        RelationalPermit.model_validate(permit(**changes))


def test_signatures_are_purpose_separated_and_detect_changes():
    value = permit()
    verify_metadata(SECRET, "admission", value)
    for changed in ({**value, "mode": "read"}, {**value, "signature": "0" * 64}):
        with pytest.raises(ValueError):
            verify_metadata(SECRET, "admission", changed)
    with pytest.raises(ValueError):
        verify_metadata(SECRET, "receipt", value)


@pytest.mark.parametrize("deadline", [True, "100", None, float("nan"), float("inf"), 0])
def test_local_handoff_budget_must_be_finite_current_monotonic_deadline(deadline):
    with pytest.raises(ValueError, match="handoff"):
        accept_permit(
            permit(), secret=SECRET, expected=BINDINGS, local_deadline=deadline
        )


@pytest.mark.skipif(
    not hasattr(time, "CLOCK_BOOTTIME"), reason="Shared Core/host boot clock"
)
def test_handoff_caps_local_budget_and_binds_session_exactly():
    value = permit()
    deadline = time.monotonic() + 0.5
    result = accept_permit(
        value, secret=SECRET, expected=BINDINGS, local_deadline=deadline
    )
    assert result.deadline <= deadline and result.permit_sha256 == permit_digest(value)
    for field in BINDINGS:
        wrong = {**BINDINGS, field: "different"}
        with pytest.raises(ValueError, match="binding changed"):
            accept_permit(value, secret=SECRET, expected=wrong, local_deadline=deadline)
    with pytest.raises(ValueError):
        accept_permit(
            value, secret=SECRET, expected={"mode": "write"}, local_deadline=deadline
        )
    value = permit(issued_at_ms=0, deadline_ms=1)
    with pytest.raises(ValueError, match="expired"):
        accept_permit(value, secret=SECRET, expected=BINDINGS, local_deadline=deadline)
