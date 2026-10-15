"""Fixed restore consent cannot pass as readonly, migration or SQL authority."""

import pytest
from pydantic import ValidationError

from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeRestoreTicket,
    _RelationalUpgradeRollbackTicket,
    _RelationalUpgradeTicket,
    _rollback_ticket,
)
from three_mm_application_sdk.relational_wire import sign_metadata, verify_metadata
from three_mm_application_sdk.tests.test_relational_upgrade_rollback import (
    SECRET,
    ticket,
)


@pytest.mark.parametrize(
    "changes",
    [
        {"version": True},
        {"deadline_ms": True},
        {"deadline_ms": 300002},
        {"source_upgrade_id": "9" * 32},
        {"database_path": "/foreign"},
        {"action": "confirm_restored_upgrade"},
        {"restored_lifecycle_sha256": "invalid"},
    ],
)
def test_fixed_restore_has_closed_strict_contract(changes):
    value = sign_metadata(
        SECRET,
        "database_upgrade_restore",
        {
            **ticket(),
            "action": "finish_interrupted_upgrade_restore",
            **changes,
        },
    )
    with pytest.raises(ValidationError):
        _RelationalUpgradeRestoreTicket.model_validate(value)


def test_restore_ticket_has_distinct_hmac_and_cannot_run_a_migration():
    value = sign_metadata(
        SECRET,
        "database_upgrade_restore",
        {
            **ticket(),
            "action": "finish_interrupted_upgrade_restore",
        },
    )
    decoded, purpose = _rollback_ticket(value)
    assert decoded == value and purpose == "database_upgrade_restore"
    verify_metadata(SECRET, purpose, decoded)
    for model in (_RelationalUpgradeRollbackTicket, _RelationalUpgradeTicket):
        with pytest.raises(ValidationError):
            model.model_validate(value)
    for other in (
        "database_upgrade_rollback",
        "database_upgrade",
        "admission",
        "database_upgrade_confirmation",
    ):
        with pytest.raises(ValueError, match="signature"):
            verify_metadata(SECRET, other, value)
