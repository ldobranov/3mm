"""Private relational metadata wire format; not a public SDK/runtime feature.

HMAC authenticates the reviewed-native instance transport, not hostile Python
isolation or independent evidence that application SQL was executed.
"""

import hashlib
import hmac
import json
import math
import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identity = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{32}$")]
Digest = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
Millis = Annotated[int, Field(strict=True, ge=0, le=9007199254740990)]


class RelationalPermit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    transaction_id: Identity
    mode: Literal["read", "write"]
    instance_id: Annotated[str, Field(pattern=r"^[0-9a-f]{24}$")]
    runtime_nonce: Identity
    database_lineage: Identity
    profile_sha256: Digest
    binding_sha256: Digest
    authority_epoch: Identity
    recovery_generation: Identity
    grant_revision: Annotated[int, Field(strict=True, ge=1, le=9007199254740990)]
    boot_id: Annotated[
        str,
        Field(
            pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        ),
    ]
    issued_at_ms: Millis
    deadline_ms: Millis
    signature: Digest

    @model_validator(mode="after")
    def budget(self):
        if not 0 < self.deadline_ms - self.issued_at_ms <= 30000:
            raise ValueError("Invalid relational budget")
        return self


class RelationalCommitReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    transaction_id: Identity
    permit_sha256: Digest
    database_lineage: Identity
    schema_revision: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")]
    outcome: Literal["committed"]
    signature: Digest


class _RelationalPreparationTicket(BaseModel):
    """Private, one-use LOCAL admin preparation; never a runtime SQL permit."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    action: Literal["prepare_existing_schema"]
    preparation_id: Identity
    instance_id: Annotated[str, Field(pattern=r"^[0-9a-f]{24}$")]
    database_lineage: Identity
    owner_sha256: Digest
    package_sha256: Digest
    service_sha256: Digest
    configuration_sha256: Digest
    profile_sha256: Digest
    schema_revision: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")]
    grant_record_revision: Identity
    binding_sha256: Digest
    authority_epoch: Identity
    recovery_generation: Identity
    boot_id: Annotated[
        str,
        Field(
            pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        ),
    ]
    issued_at_ms: Millis
    deadline_ms: Millis
    signature: Digest

    @model_validator(mode="after")
    def budget(self):
        if not 0 < self.deadline_ms - self.issued_at_ms <= 300000:
            raise ValueError("Invalid preparation budget")
        return self


class _RelationalPreparationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    preparation_id: Identity
    lifecycle_sha256: Digest
    outcome: Literal["prepared_not_started"]
    signature: Digest


class _RelationalMigrationPreparationTicket(_RelationalPreparationTicket):
    """Separate human permission to import/run the EXACT candidate migrations."""

    action: Literal["prepare_migrated_schema"]
    worker_profile_sha256: Digest


class _RelationalNamespacePreparationTicket(_RelationalPreparationTicket):
    """Local helper dependencies, not package-selected paths or SQL authority."""

    action: Literal["create_owned_namespace"]
    service_uid: Annotated[int, Field(strict=True, ge=1, le=2147483647)]
    service_gid: Annotated[int, Field(strict=True, ge=1, le=2147483647)]
    coordinator_uid: Annotated[int, Field(strict=True, ge=1, le=2147483647)]
    transport_key_sha256: Digest

    @model_validator(mode="after")
    def separate_principals(self):
        if self.coordinator_uid == self.service_uid:
            raise ValueError("Core and application principals must be distinct")
        return self


class _RelationalNamespacePreparationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    preparation_id: Identity
    ticket_sha256: Digest
    outcome: Literal["namespace_created_not_started"]
    signature: Digest


class _RelationalActivationTicket(_RelationalNamespacePreparationTicket):
    """One LOCAL start of an already prepared database, never a SQL permit.

    The inherited preparation_id identifies this activation, not a new database
    preparation. Source lineage and lifecycle bytes must remain unchanged.
    """

    action: Literal["activate_prepared_service"]
    source_preparation_id: Identity
    prepared_lifecycle_sha256: Digest


class _RelationalActivationResult(_RelationalPreparationResult):
    outcome: Literal["active_review_required"]


class _RelationalActivationRecoveryTicket(_RelationalActivationTicket):
    """Fresh LOCAL stop/reconciliation only; inherited grant fields are history.

    This never renews the source start ticket or authorizes SQL, permissions,
    migrations, namespace replacement, key rotation or another start.
    """

    action: Literal["reconcile_prepared_start"]
    source_activation_id: Identity
    source_activation_revision: Identity
    source_ticket_sha256: Digest
    source_state: Literal[
        "recorded", "execution_unconfirmed", "activation_unconfirmed", "activated"
    ]


class _RelationalActivationRecoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    preparation_id: Identity
    ticket_sha256: Digest
    source_activation_id: Identity
    lifecycle_sha256: Digest
    witness_sha256: Digest
    outcome: Literal["stopped_review_required"]
    signature: Digest


class _RelationalReactivationRecoveryTicket(_RelationalActivationRecoveryTicket):
    """Same stop-only contract, distinct source witness for a repeated start."""

    action: Literal["reconcile_reactivated_start"]


class _RelationalReactivationTicket(_RelationalActivationTicket):
    """Fresh one-use start after an exact confirmed stop, not ticket renewal.

    Historical stop evidence is bounded and embedded for Root verification;
    only the outer ticket's fresh grant/epoch/clock authorizes the new start.
    """

    action: Literal["reactivate_prepared_service"]
    origin_activation_id: Identity
    source_recovery_id: Identity
    source_recovery_revision: Identity
    source_activation_revision: Identity
    source_recovery_ticket: (
        _RelationalActivationRecoveryTicket | _RelationalReactivationRecoveryTicket
    )
    source_recovery_receipt: _RelationalActivationRecoveryResult


class _RelationalBootEnableTicket(_RelationalActivationTicket):
    """Fresh LOCAL consent to enable an already running exact prepared unit.

    Not start/restart, a migration ticket, SQL authority or a durable grant.
    Historical start digests bind the protected successful Root witness; only
    the outer fresh clock/current grant/epoch permits the one enable action.
    """

    action: Literal["enable_prepared_boot"]
    source_activation_id: Identity
    source_activation_revision: Identity
    source_activation_action: Literal[
        "activate_prepared_service", "reactivate_prepared_service"
    ]
    source_ticket_sha256: Digest
    source_receipt_sha256: Digest


class _RelationalBootEnableResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    preparation_id: Identity
    ticket_sha256: Digest
    source_activation_id: Identity
    lifecycle_sha256: Digest
    witness_sha256: Digest
    outcome: Literal["boot_enabled_not_started"]
    signature: Digest


class _RelationalBootStartupPermit(BaseModel):
    """Short fresh pre-import handoff, never an enable ticket or SQL grant."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    action: Literal["boot_startup"]
    instance_id: Annotated[str, Field(pattern=r"^[0-9a-f]{24}$")]
    runtime_nonce: Identity
    boot_enable_id: Identity
    policy_sha256: Digest
    lifecycle_sha256: Digest
    authority_epoch: Identity
    recovery_generation: Identity
    grant_record_revision: Identity
    process_pid: Annotated[int, Field(strict=True, ge=1, le=2147483647)]
    process_start_ticks: Annotated[int, Field(strict=True, ge=1, le=9007199254740990)]
    service_uid: Annotated[int, Field(strict=True, ge=1, le=2147483647)]
    service_gid: Annotated[int, Field(strict=True, ge=1, le=2147483647)]
    boot_id: Annotated[
        str,
        Field(
            pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        ),
    ]
    issued_at_ms: Millis
    deadline_ms: Millis
    signature: Digest

    @model_validator(mode="after")
    def budget(self):
        if not 0 < self.deadline_ms - self.issued_at_ms <= 5000:
            raise ValueError("Invalid boot startup budget")
        return self


def _activation_ticket(value):
    model, purpose = (
        (_RelationalReactivationTicket, "reactivation")
        if type(value) is dict and value.get("action") == "reactivate_prepared_service"
        else (_RelationalActivationTicket, "activation")
    )
    return model.model_validate(value).model_dump(mode="json"), purpose


def _activation_recovery_ticket(value):
    model, purpose = (
        (_RelationalReactivationRecoveryTicket, "reactivation_recovery")
        if type(value) is dict and value.get("action") == "reconcile_reactivated_start"
        else (_RelationalActivationRecoveryTicket, "activation_recovery")
    )
    return model.model_validate(value).model_dump(mode="json"), purpose


class _RelationalNamespaceRecoveryTicket(_RelationalNamespacePreparationTicket):
    """Fresh human choice for EMPTY bootstrap state, never database recovery."""

    action: Literal["confirm_owned_namespace", "quarantine_owned_namespace"]
    source_preparation_id: Identity
    source_ticket_sha256: Digest


class _RelationalNamespaceRecoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    preparation_id: Identity
    ticket_sha256: Digest
    outcome: Literal[
        "namespace_confirmed_not_started", "namespace_quarantined_not_started"
    ]
    signature: Digest


class _RelationalRecoveryTicket(_RelationalPreparationTicket):
    """Explicit acceptance of an exact published candidate, never SQL replay."""

    action: Literal["accept_prepared_candidate"]
    source_preparation_id: Identity
    source_lifecycle_sha256: Digest


class _RelationalRecoveryConfirmationTicket(_RelationalPreparationTicket):
    """Fresh human metadata reconciliation; never renews SQL recovery authority."""

    action: Literal["confirm_published_recovery"]
    source_recovery_id: Identity
    source_ticket_sha256: Digest
    published_lifecycle_sha256: Digest


def migration_worker_profile_digest():
    """Fixed private executor policy; old tickets cannot select a changed worker."""
    return hashlib.sha256(
        canonical(
            {
                "profile": "nonroot_quiescent_owned_sqlite_v1",
                "sql_facade": "bounded_business_ddl_v1",
                "max_migrations": 128,
                "max_process_ms": 30000,
                "max_memory_bytes": 512 * 1024 * 1024,
                "file_ceiling": "max_database_bytes_plus_auxiliary_pause_bytes",
                "platform_transport": False,
            }
        )
    ).hexdigest()


def _preparation_ticket(value):
    model, purpose = (
        (_RelationalNamespacePreparationTicket, "namespace_preparation")
        if type(value) is dict and value.get("action") == "create_owned_namespace"
        else (
            (_RelationalMigrationPreparationTicket, "migration_preparation")
            if type(value) is dict and value.get("action") == "prepare_migrated_schema"
            else (_RelationalPreparationTicket, "preparation")
        )
    )
    return model.model_validate(value).model_dump(mode="json"), purpose


def prepared_lifecycle(ticket, secret):
    ticket, purpose = _preparation_ticket(ticket)
    verify_metadata(secret, purpose, ticket)
    if purpose == "namespace_preparation":
        raise ValueError("Namespace preparation is not database lifecycle authority")
    return _lifecycle(ticket, secret)


def recovered_lifecycle(ticket, secret):
    ticket = _RelationalRecoveryTicket.model_validate(ticket).model_dump(mode="json")
    verify_metadata(secret, "recovery", ticket)
    return _lifecycle(ticket, secret)


def _lifecycle(ticket, secret):
    fields = (
        "instance_id",
        "database_lineage",
        "owner_sha256",
        "package_sha256",
        "service_sha256",
        "configuration_sha256",
        "profile_sha256",
        "schema_revision",
        "recovery_generation",
    )
    return sign_metadata(
        secret,
        "lifecycle",
        {
            "version": 1,
            "lifecycle_id": ticket["preparation_id"],
            **{field: ticket[field] for field in fields},
        },
    )


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sign_metadata(secret, purpose, value):
    if (
        type(secret) is not bytes
        or len(secret) != 32
        or purpose
        not in {
            "admission",
            "receipt",
            "lineage",
            "lifecycle",
            "invocation",
            "preparation",
            "preparation_result",
            "migration_preparation",
            "database_upgrade",
            "database_upgrade_result",
            "database_upgrade_confirmation",
            "database_upgrade_confirmation_result",
            "database_upgrade_rollback",
            "database_upgrade_rollback_result",
            "database_upgrade_rollback_proof",
            "database_upgrade_restore",
            "namespace_preparation",
            "namespace_preparation_result",
            "activation",
            "activation_result",
            "activation_recovery",
            "activation_recovery_result",
            "reactivation",
            "reactivation_result",
            "reactivation_recovery",
            "boot_enable",
            "boot_enable_result",
            "boot_startup",
            "namespace_recovery",
            "namespace_recovery_result",
            "empty_preparation_recovery",
            "empty_preparation_recovery_result",
            "recovery",
            "recovery_result",
            "recovery_confirmation",
            "recovery_confirmation_result",
        }
    ):
        raise ValueError("Invalid relational signing dependency")
    body = {key: item for key, item in value.items() if key != "signature"}
    return {
        **body,
        "signature": hmac.new(
            secret,
            b"3mm:m20:relational:"
            + purpose.encode("ascii")
            + b":v1\x00"
            + canonical(body),
            hashlib.sha256,
        ).hexdigest(),
    }


def verify_metadata(secret, purpose, value):
    expected = sign_metadata(secret, purpose, value)
    if type(value.get("signature")) is not str or not hmac.compare_digest(
        value["signature"], expected["signature"]
    ):
        raise ValueError("Invalid relational metadata signature")


def permit_digest(permit):
    return hashlib.sha256(canonical(permit)).hexdigest()


def profile_digest(declaration, schema_revision):
    return hashlib.sha256(
        canonical(
            {
                "declaration": declaration.model_dump(mode="json"),
                "schema_revision": schema_revision,
            }
        )
    ).hexdigest()


def accept_permit(value, *, secret, expected, local_deadline):
    """Host-only handoff after signed transport; no permission/retry fallback.

    Expectations come from protected host lifecycle/session state, never the
    manifest or service payload. CLOCK_BOOTTIME is shared with the local Core.
    """
    from three_mm_application_sdk.scoped_relational import _TransactionAdmission

    if (
        type(value) is not dict
        or type(local_deadline) not in {int, float}
        or not math.isfinite(local_deadline)
        or time.monotonic() >= local_deadline
    ):
        raise ValueError("Invalid relational permit handoff")
    permit = RelationalPermit.model_validate(value).model_dump(mode="json")
    verify_metadata(secret, "admission", permit)
    required = {
        "transaction_id",
        "mode",
        "profile_sha256",
        "instance_id",
        "runtime_nonce",
        "database_lineage",
        "boot_id",
        "authority_epoch",
        "recovery_generation",
        "binding_sha256",
    }
    if (
        type(expected) is not dict
        or set(expected) != required
        or any(permit[key] != item for key, item in expected.items())
    ):
        raise ValueError("Relational permit binding changed")
    if not hasattr(time, "CLOCK_BOOTTIME"):
        raise ValueError("Relational host clock is unavailable")
    local_now = time.monotonic()
    now = time.clock_gettime_ns(time.CLOCK_BOOTTIME) // 1_000_000
    if not permit["issued_at_ms"] <= now < permit["deadline_ms"]:
        raise ValueError("Relational permit expired")
    return _TransactionAdmission(
        permit["transaction_id"],
        permit["mode"],
        permit["profile_sha256"],
        min(local_deadline, local_now + (permit["deadline_ms"] - now) / 1000),
        permit_digest(permit),
        permit["deadline_ms"],
    )
