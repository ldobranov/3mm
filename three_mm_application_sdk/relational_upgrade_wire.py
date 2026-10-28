"""Private prepared-database upgrade contract; not a public SDK feature."""

import hashlib
from typing import Annotated, Literal

from pydantic import Field, model_validator

from three_mm_application_sdk.relational_wire import (
    Digest,
    Identity,
    _lifecycle,
    _RelationalMigrationPreparationTicket,
    _RelationalPreparationResult,
    _RelationalPreparationTicket,
    canonical,
    migration_worker_profile_digest,
    verify_metadata,
)


class _RelationalUpgradeTicket(_RelationalMigrationPreparationTicket):
    action: Literal["upgrade_prepared_schema"]
    source_preparation_id: Identity
    source_preparation_revision: Identity
    source_ticket_sha256: Digest
    source_lifecycle_sha256: Digest
    source_package_sha256: Digest
    source_service_sha256: Digest
    source_configuration_sha256: Digest
    source_profile_sha256: Digest
    source_schema_revision: Annotated[
        str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")
    ]
    source_database_lineage: Identity
    transport_key_sha256: Digest

    @model_validator(mode="after")
    def separate_source(self):
        if (
            self.preparation_id == self.source_preparation_id
            or self.database_lineage == self.source_database_lineage
            or self.schema_revision == self.source_schema_revision
        ):
            raise ValueError("Upgrade requires a separate forward lifecycle")
        return self


class _RelationalUpgradeResult(_RelationalPreparationResult):
    outcome: Literal["upgraded_not_started"]


class _RelationalUpgradeConfirmationTicket(_RelationalPreparationTicket):
    """Fresh readonly reconciliation; never permission to execute migrations."""

    action: Literal["confirm_published_upgrade"]
    source_upgrade_id: Identity
    source_ticket_sha256: Digest
    published_lifecycle_sha256: Digest
    transport_key_sha256: Digest

    @model_validator(mode="after")
    def separate_confirmation(self):
        if self.preparation_id == self.source_upgrade_id:
            raise ValueError("Confirmation requires a separate human action")
        return self


class _RelationalUpgradeRollbackTicket(_RelationalPreparationTicket):
    """Target consent is historical; the restored source is NOT runtime authority."""

    action: Literal["confirm_restored_upgrade"]
    source_upgrade_id: Identity
    source_ticket_sha256: Digest
    restored_lifecycle_sha256: Digest
    transport_key_sha256: Digest

    @model_validator(mode="after")
    def separate_confirmation(self):
        if self.preparation_id == self.source_upgrade_id:
            raise ValueError("Rollback confirmation requires a separate human action")
        return self


class _RelationalUpgradeRollbackProof(_RelationalPreparationResult):
    outcome: Literal["restored_not_started"]
    source_ticket_sha256: Digest
    database_sha256: Digest
    preimage_sha256: Digest
    files_manifest_sha256: Digest
    media_manifest_sha256: Digest


class _RelationalUpgradeRestoreTicket(_RelationalUpgradeRollbackTicket):
    """Explicit fixed preimage restore; NOT readonly rollback confirmation."""

    action: Literal["finish_interrupted_upgrade_restore"]


def _rollback_ticket(value):
    model, purpose = (
        (_RelationalUpgradeRestoreTicket, "database_upgrade_restore")
        if type(value) is dict
        and value.get("action") == "finish_interrupted_upgrade_restore"
        else (_RelationalUpgradeRollbackTicket, "database_upgrade_rollback")
    )
    return model.model_validate(value).model_dump(mode="json"), purpose


class _RelationalUpgradeRollbackResult(_RelationalPreparationResult):
    outcome: Literal["restored_not_started"]
    source_upgrade_id: Identity
    rollback_proof_sha256: Digest


def upgrade_worker_profile_digest():
    return hashlib.sha256(
        canonical(
            {
                "profile": "prepared_owned_sqlite_forward_v1",
                "base_worker_sha256": migration_worker_profile_digest(),
                "receipt_metadata": "pinned_unchanged_during_business_migrations",
                "history": "preserved_original_schema_lineage_and_signatures",
            }
        )
    ).hexdigest()


def upgraded_lifecycle(ticket, secret):
    ticket = _RelationalUpgradeTicket.model_validate(ticket).model_dump(mode="json")
    verify_metadata(secret, "database_upgrade", ticket)
    return _lifecycle(ticket, secret)
