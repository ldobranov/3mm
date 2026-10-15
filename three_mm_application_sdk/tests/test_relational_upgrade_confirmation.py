"""Closed private confirmation wire; it is never a worker execution ticket."""

import hashlib

import pytest
from pydantic import ValidationError

from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeConfirmationTicket,
    _RelationalUpgradeTicket,
    upgraded_lifecycle,
)
from three_mm_application_sdk.relational_wire import (
    canonical,
    sign_metadata,
    verify_metadata,
)
from three_mm_application_sdk.tests import test_relational_upgrade as upgrade

SECRET = upgrade.SECRET


def ticket(**changes):
    old = upgrade.ticket()
    value = {
        name: old[name]
        for name in _RelationalUpgradeConfirmationTicket.model_fields
        if name in old
    }
    value.update(
        action="confirm_published_upgrade",
        preparation_id="9" * 32,
        source_upgrade_id=old["preparation_id"],
        source_ticket_sha256=hashlib.sha256(canonical(old)).hexdigest(),
        published_lifecycle_sha256=hashlib.sha256(
            canonical(upgraded_lifecycle(old, SECRET))
        ).hexdigest(),
    )
    return sign_metadata(SECRET, "database_upgrade_confirmation", {**value, **changes})


@pytest.mark.parametrize(
    "changes",
    [
        {"version": True},
        {"deadline_ms": True},
        {"deadline_ms": 300002},
        {"action": "upgrade_prepared_schema"},
        {"database_path": "/foreign"},
        {"source_upgrade_id": "9" * 32},
        {"transport_key_sha256": "invalid"},
        {"published_lifecycle_sha256": "invalid"},
    ],
)
def test_confirmation_contract_refuses_extra_or_ambiguous_authority(changes):
    with pytest.raises(ValidationError):
        _RelationalUpgradeConfirmationTicket.model_validate(ticket(**changes))


def test_confirmation_signature_is_separate_from_worker_and_finish():
    value = _RelationalUpgradeConfirmationTicket.model_validate(ticket()).model_dump(
        mode="json"
    )
    verify_metadata(SECRET, "database_upgrade_confirmation", value)
    with pytest.raises(ValidationError):
        _RelationalUpgradeTicket.model_validate(value)
    for purpose in (
        "database_upgrade",
        "database_upgrade_result",
        "recovery_confirmation",
        "database_upgrade_confirmation_result",
    ):
        with pytest.raises(ValueError, match="signature"):
            verify_metadata(SECRET, purpose, value)
