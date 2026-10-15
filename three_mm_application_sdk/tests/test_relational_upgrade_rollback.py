"""Private rollback evidence is neither migration nor runtime permission."""

import pytest
from pydantic import ValidationError

from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeRollbackProof,
    _RelationalUpgradeRollbackResult,
    _RelationalUpgradeRollbackTicket,
    _RelationalUpgradeTicket,
)
from three_mm_application_sdk.relational_wire import sign_metadata, verify_metadata
from three_mm_application_sdk.tests import test_relational_upgrade as upgrade

SECRET = upgrade.SECRET


def ticket(**changes):
    old = upgrade.ticket()
    value = {
        name: old[name]
        for name in _RelationalUpgradeRollbackTicket.model_fields
        if name in old
    }
    value.update(
        action="confirm_restored_upgrade",
        preparation_id="9" * 32,
        source_upgrade_id=old["preparation_id"],
        source_ticket_sha256="a" * 64,
        restored_lifecycle_sha256="b" * 64,
        database_lineage=old["source_database_lineage"],
    )
    return sign_metadata(SECRET, "database_upgrade_rollback", {**value, **changes})


@pytest.mark.parametrize(
    "changes",
    [
        {"version": True},
        {"deadline_ms": True},
        {"deadline_ms": 300002},
        {"source_upgrade_id": "9" * 32},
        {"action": "upgrade_prepared_schema"},
        {"database_path": "/foreign"},
        {"restored_lifecycle_sha256": "invalid"},
    ],
)
def test_rollback_consent_is_closed_and_distinct(changes):
    with pytest.raises(ValidationError):
        _RelationalUpgradeRollbackTicket.model_validate(ticket(**changes))


def test_rollback_ticket_is_not_worker_or_published_confirmation_permission():
    value = _RelationalUpgradeRollbackTicket.model_validate(ticket()).model_dump(
        mode="json"
    )
    verify_metadata(SECRET, "database_upgrade_rollback", value)
    with pytest.raises(ValidationError):
        _RelationalUpgradeTicket.model_validate(value)
    for purpose in (
        "database_upgrade",
        "database_upgrade_confirmation",
        "database_upgrade_rollback_proof",
    ):
        with pytest.raises(ValueError, match="signature"):
            verify_metadata(SECRET, purpose, value)


def test_root_proof_and_core_result_have_separate_closed_shapes_and_purposes():
    body = {
        "version": 1,
        "preparation_id": "1" * 32,
        "lifecycle_sha256": "a" * 64,
        "outcome": "restored_not_started",
    }
    proof = _RelationalUpgradeRollbackProof.model_validate(
        sign_metadata(
            SECRET,
            "database_upgrade_rollback_proof",
            {
                **body,
                "source_ticket_sha256": "b" * 64,
                "database_sha256": "c" * 64,
                "preimage_sha256": "d" * 64,
                "files_manifest_sha256": "e" * 64,
            },
        )
    ).model_dump(mode="json")
    result = _RelationalUpgradeRollbackResult.model_validate(
        sign_metadata(
            SECRET,
            "database_upgrade_rollback_result",
            {
                **body,
                "source_upgrade_id": "2" * 32,
                "rollback_proof_sha256": "f" * 64,
            },
        )
    ).model_dump(mode="json")
    with pytest.raises(ValidationError):
        _RelationalUpgradeRollbackResult.model_validate(proof)
    with pytest.raises(ValidationError):
        _RelationalUpgradeRollbackProof.model_validate(result)
    with pytest.raises(ValueError, match="signature"):
        verify_metadata(SECRET, "database_upgrade_rollback_result", proof)
