"""Private LOCAL recovery dialect, not a public SDK feature or SQL permit."""

from typing import Literal

from three_mm_application_sdk.relational_wire import (
    Digest,
    Identity,
    _RelationalNamespacePreparationResult,
    _RelationalNamespacePreparationTicket,
)


class _EmptyPreparationRecoveryTicket(_RelationalNamespacePreparationTicket):
    action: Literal["reconcile_restored_empty_preparation"]
    source_preparation_id: Identity
    source_preparation_revision: Identity
    source_ticket_sha256: Digest
    source_namespace_id: Identity
    source_namespace_sha256: Digest


class _EmptyPreparationRecoveryResult(_RelationalNamespacePreparationResult):
    outcome: Literal["restored_empty_not_started"]
