"""Internal current-authority admission journal, not an exposed SQL endpoint.

The internal resolver checks a prepared host over bounded signed Unix metadata
transport. Production dispatch/SDK wiring and protected lifecycle publication/
recovery are still missing; no HTTP/platform routes activate this runtime.
The context argument is a trusted Core dependency, NEVER a service payload.
No SQL, parameters, business values, paths or application disk I/O enter Core.
"""

import hashlib
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services.application_authority_context import _canonical_bytes
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_authority_sources import _configuration
from backend.services.application_files import _clean_session, _principal, _runtime
from backend.services.authority_metadata import (
    authority_transaction,
    read_application_authority,
)
from three_mm_application_sdk.relational_wire import (
    RelationalCommitReceipt,
    RelationalPermit,
    canonical,
    permit_digest,
    profile_digest,
    sign_metadata,
    verify_metadata,
)
from three_mm_runtime.application_relational_session import (
    _call_host_metadata,
    _Invocation,
)

MAX_RELATIONAL_ACTIONS = 4096


class RelationalAuthorityError(ValueError):
    def __init__(self):
        super().__init__("Relational authority or transaction metadata unavailable")


@dataclass(frozen=True, slots=True)
class _HostTransactionContext:
    """Core-owned dependency from the verified host resolver below.

    A typed object alone is not authentication/lifecycle proof. Do not deserialize
    this from an extension request or add a transport route before that adapter.
    """

    instance_id: str
    runtime_nonce: str
    database_lineage: str
    boot_id: str
    authority_epoch: str
    recovery_generation: str
    started_at_ms: int
    operation_deadline_ms: int


def _host_snapshot(db, installation_id, transport_secret):
    """No IPC under authority leases; principal/path/key are Core dependencies."""
    if type(transport_secret) is not bytes or len(transport_secret) != 32:
        raise RelationalAuthorityError()
    _clean_session(db)
    runtime = _runtime(db, installation_id)
    db.rollback()  # Close the routing read snapshot before host IPC.
    hello = _call_host_metadata(
        runtime[1].with_name("relational.sock"), transport_secret
    )
    return runtime, hello


def _require_prepared_host(db, installation_id, prepared, runtime, hello, generation):
    boot, now = authority._clock()
    definition = prepared[1].application_extension
    record = hello["lifecycle"]
    if (
        _runtime(db, installation_id) != runtime
        or hello["boot_id"] != boot
        or not 0 <= now - hello["clock_ms"] <= 2000
        or record["instance_id"] != runtime[0]
        or record["package_sha256"] != prepared[0].sha256
        or record["service_sha256"] != definition.service.artifact_sha256
        or record["schema_revision"] != definition.storage.schema_revision
        or record["profile_sha256"]
        != profile_digest(
            definition.storage.relational, definition.storage.schema_revision
        )
        or record["owner_sha256"]
        != hashlib.sha256(_canonical_bytes(_principal(db, installation_id))).hexdigest()
        or record["configuration_sha256"]
        != hashlib.sha256(
            canonical(_configuration(db, installation_id, prepared[1]))
        ).hexdigest()
        or record["recovery_generation"] != generation
    ):
        raise RelationalAuthorityError()
    return boot, now


def prepare_host_invocation(
    db, installation_id, operation_id, *, required_audience, transport_secret
):
    """Private handoff AFTER existing Core route/actor/payload authorization.

    Not an invocation endpoint or a permission bypass. Only Core selects the
    operation budget from its installed descriptor, never from service JSON.
    A ticket permits no SQL without separate fresh durable transaction admission.
    """
    try:
        runtime, hello = _host_snapshot(db, installation_id, transport_secret)
        manager = authority.configured_manager(db.get_bind().engine)
        prepared = manager._prepare(installation_id)
        operation = next(
            (
                item
                for item in prepared[1].application_extension.operations
                if item.operation_id == operation_id
            ),
            None,
        )
        if operation is None or required_audience not in operation.audiences:
            raise RelationalAuthorityError()
        with manager.keys.locked() as key, authority_transaction(db) as mutation:
            grant = manager._require_grant(
                db, key, installation_id, prepared, "storage:relational_read"
            )
            boot, now = _require_prepared_host(
                db, installation_id, prepared, runtime, hello, mutation.guard.generation
            )
            if hello["invocation"] is not None:
                raise RelationalAuthorityError()
            current = read_application_authority(db, installation_id)
            return _Invocation.model_validate(
                sign_metadata(
                    transport_secret,
                    "invocation",
                    {
                        "version": 1,
                        "invocation_id": authority.new_authority_generation(),
                        "operation_id": operation.operation_id,
                        "instance_id": runtime[0],
                        "runtime_nonce": hello["runtime_nonce"],
                        "boot_id": boot,
                        "lifecycle_sha256": hashlib.sha256(
                            canonical(hello["lifecycle"])
                        ).hexdigest(),
                        "binding_sha256": hashlib.sha256(
                            _canonical_bytes(grant["data"]["subject"])
                        ).hexdigest(),
                        "authority_epoch": current.epoch,
                        "recovery_generation": mutation.guard.generation,
                        "started_at_ms": now,
                        "deadline_ms": now + operation.timeout_seconds * 1000,
                    },
                )
            ).model_dump(mode="json")
    except (
        authority.AuthorityManagementError,
        AuthorityReviewKeyError,
        SQLAlchemyError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OSError,
        RuntimeError,
    ):
        db.rollback()
        raise RelationalAuthorityError() from None


def admit_host_transaction(
    db, installation_id, transaction_id, mode, *, transport_secret
):
    """Resolve live host context, then run the existing fresh journal admission.

    A caller cannot supply a nonce/lineage/epoch/deadline. No application DB I/O
    or SQL payload enters Core; a worker handles only readiness/invocation metadata.
    """
    try:
        transaction_started_ms = authority._clock()[1]
        runtime, hello = _host_snapshot(db, installation_id, transport_secret)
        manager = authority.configured_manager(db.get_bind().engine)
        prepared = manager._prepare(installation_id)
        with manager.keys.locked() as key, authority_transaction(db) as mutation:
            grant = manager._require_grant(
                db, key, installation_id, prepared, "storage:relational_" + mode
            )
            boot, now = _require_prepared_host(
                db, installation_id, prepared, runtime, hello, mutation.guard.generation
            )
            ticket = hello["invocation"]
            if (
                ticket is None
                or any(
                    ticket[field] != value
                    for field, value in {
                        "instance_id": runtime[0],
                        "runtime_nonce": hello["runtime_nonce"],
                        "boot_id": boot,
                        "lifecycle_sha256": hashlib.sha256(
                            canonical(hello["lifecycle"])
                        ).hexdigest(),
                        "binding_sha256": hashlib.sha256(
                            _canonical_bytes(grant["data"]["subject"])
                        ).hexdigest(),
                        "authority_epoch": read_application_authority(
                            db, installation_id
                        ).epoch,
                        "recovery_generation": mutation.guard.generation,
                    }.items()
                )
                or not ticket["started_at_ms"] <= now < ticket["deadline_ms"]
            ):
                raise RelationalAuthorityError()
            context = _HostTransactionContext(
                runtime[0],
                hello["runtime_nonce"],
                hello["lifecycle"]["database_lineage"],
                boot,
                ticket["authority_epoch"],
                ticket["recovery_generation"],
                transaction_started_ms,
                ticket["deadline_ms"],
            )
        return admit_transaction(
            db,
            installation_id,
            transaction_id,
            mode,
            host_context=context,
            transport_secret=transport_secret,
        )
    except (
        authority.AuthorityManagementError,
        AuthorityReviewKeyError,
        SQLAlchemyError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OSError,
        RuntimeError,
    ):
        db.rollback()
        raise RelationalAuthorityError() from None


def record_host_commit(db, installation_id, receipt, *, transport_secret):
    """Internal live-host completion after SQL unlock, including after revoke.

    No new grant/admission is requested here. Ending/restarting the invocation
    leaves uncertainty; historical receipt reconciliation is not replay.
    """
    try:
        runtime, hello = _host_snapshot(db, installation_id, transport_secret)
        manager = authority.configured_manager(db.get_bind().engine)
        prepared = manager._prepare(installation_id)
        with manager.keys.locked(), authority_transaction(db) as mutation:
            boot, _ = _require_prepared_host(
                db, installation_id, prepared, runtime, hello, mutation.guard.generation
            )
            ticket = hello["invocation"]
            if (
                ticket is None
                or ticket["instance_id"] != runtime[0]
                or ticket["runtime_nonce"] != hello["runtime_nonce"]
                or ticket["boot_id"] != boot
                or ticket["lifecycle_sha256"]
                != hashlib.sha256(canonical(hello["lifecycle"])).hexdigest()
                or ticket["recovery_generation"] != mutation.guard.generation
            ):
                raise RelationalAuthorityError()
            context = _HostTransactionContext(
                runtime[0],
                hello["runtime_nonce"],
                hello["lifecycle"]["database_lineage"],
                boot,
                ticket["authority_epoch"],
                ticket["recovery_generation"],
                ticket["started_at_ms"],
                ticket["deadline_ms"],
            )
        return record_commit(
            db,
            installation_id,
            receipt,
            host_context=context,
            transport_secret=transport_secret,
        )
    except (
        authority.AuthorityManagementError,
        AuthorityReviewKeyError,
        SQLAlchemyError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OSError,
        RuntimeError,
    ):
        db.rollback()
        raise RelationalAuthorityError() from None


def _record(db, key, installation_id, transaction_id):
    row = db.get(Action, transaction_id, populate_existing=True)
    if row is None:
        return None, None
    value = authority._load(db, key, "action", row, transaction_id)
    data = value["data"]
    if (
        value["installation_id"] != installation_id
        or data.get("operation") != "relational_transaction"
        or data.get("principal") != _principal(db, installation_id)
        or value["state"] not in {"execution_unconfirmed", "committed"}
    ):
        raise RelationalAuthorityError()
    return row, value


def admit_transaction(
    db, installation_id, transaction_id, mode, *, host_context, transport_secret
):
    """Fresh exact admission, durably committed before returning signed permit.

    Repeated ID is a refusal, even with identical contents. Use status for lost
    replies; never reissue a consumed/possibly received permit after a restart.
    """
    try:
        transaction_id = authority._identifier(transaction_id)
        if (
            type(mode) is not str
            or mode not in {"read", "write"}
            or type(host_context) is not _HostTransactionContext
        ):
            raise RelationalAuthorityError()
        if type(transport_secret) is not bytes or len(transport_secret) != 32:
            raise RelationalAuthorityError()
        _clean_session(db)
        manager = authority.configured_manager(db.get_bind().engine)
        prepared = manager._prepare(installation_id)  # ZIP I/O before key/DB fence.
        definition = prepared[1].application_extension
        declaration = definition.storage.relational
        if declaration is None:
            raise RelationalAuthorityError()
        with manager.keys.locked() as key, authority_transaction(db) as mutation:
            if db.get(Action, transaction_id) is not None:
                raise RelationalAuthorityError()
            grant = manager._require_grant(
                db, key, installation_id, prepared, "storage:relational_" + mode
            )
            current = read_application_authority(db, installation_id)
            installation = db.get(Installation, installation_id, populate_existing=True)
            context = host_context
            boot, now = authority._clock()
            if (
                not installation.enabled
                or installation.status != "active"
                or installation.instance_id != context.instance_id
                or current.epoch != context.authority_epoch
                or mutation.guard.generation != context.recovery_generation
                or boot != context.boot_id
                or type(context.started_at_ms) is not int
                or type(context.operation_deadline_ms) is not int
                or not 0 <= context.started_at_ms <= now < context.operation_deadline_ms
            ):
                raise RelationalAuthorityError()
            deadline = min(
                context.operation_deadline_ms,
                context.started_at_ms + declaration.max_transaction_ms,
            )
            value = RelationalPermit.model_validate(
                sign_metadata(
                    transport_secret,
                    "admission",
                    {
                        "version": 1,
                        "transaction_id": transaction_id,
                        "mode": mode,
                        "instance_id": context.instance_id,
                        "runtime_nonce": context.runtime_nonce,
                        "database_lineage": context.database_lineage,
                        "boot_id": boot,
                        "authority_epoch": current.epoch,
                        "recovery_generation": mutation.guard.generation,
                        "grant_revision": grant["data"]["grant_revision"],
                        "binding_sha256": hashlib.sha256(
                            _canonical_bytes(grant["data"]["subject"])
                        ).hexdigest(),
                        "profile_sha256": profile_digest(
                            declaration, definition.storage.schema_revision
                        ),
                        "issued_at_ms": now,
                        "deadline_ms": deadline,
                    },
                )
            ).model_dump(mode="json")
            count = db.scalar(
                select(func.count())
                .select_from(Action)
                .where(Action.installation_id == installation_id)
            )
            if count >= MAX_RELATIONAL_ACTIONS:
                raise RelationalAuthorityError()
            mutation.lock_application(current)
            authority._save(
                db,
                key,
                "action",
                Action(request_id=transaction_id, installation_id=installation_id),
                authority._envelope(
                    "action",
                    transaction_id,
                    installation_id,
                    "execution_unconfirmed",
                    {
                        "operation": "relational_transaction",
                        "actor": ["application", str(installation_id)],
                        "principal": _principal(db, installation_id),
                        "permit": value,
                        "plan_id": grant["data"]["plan_id"],
                        "native_review_id": grant["data"]["native_review_id"],
                        "schema_revision": definition.storage.schema_revision,
                        "outcome": "execution_unconfirmed",
                    },
                ),
            )
            mutation.advance_guard_revision()
        return value
    except (
        authority.AuthorityManagementError,
        AuthorityReviewKeyError,
        SQLAlchemyError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OSError,
    ):
        db.rollback()
        raise RelationalAuthorityError() from None


def transaction_status(db, installation_id, transaction_id):
    """Historical bounded own outcome only, never a new permit or SQL read.

    Missing completion/record does not prove rollback. Recovery/key/incarnation
    changes refuse old evidence; absence never authorizes callback replay.
    """
    try:
        transaction_id = authority._identifier(transaction_id)
        _clean_session(db)
        manager = authority.configured_manager(db.get_bind().engine)
        with manager.keys.locked() as key, authority_transaction(db):
            _, value = _record(db, key, installation_id, transaction_id)
            return {
                "transaction_id": transaction_id,
                "outcome": value["state"] if value else "execution_unconfirmed",
                "historical": True,
            }
    except (
        authority.AuthorityManagementError,
        AuthorityReviewKeyError,
        SQLAlchemyError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OSError,
    ):
        db.rollback()
        raise RelationalAuthorityError() from None


def record_commit(db, installation_id, receipt, *, host_context, transport_secret):
    """Metadata completion after own SQL unlock, allowed after grant revocation.

    Only a matching signed atomic commit receipt may turn unknown into committed.
    No caller-authored rolled_back/not_started assertion clears uncertainty.
    """
    try:
        receipt = RelationalCommitReceipt.model_validate(receipt).model_dump(
            mode="json"
        )
        verify_metadata(transport_secret, "receipt", receipt)
        if type(host_context) is not _HostTransactionContext:
            raise RelationalAuthorityError()
        _clean_session(db)
        manager = authority.configured_manager(db.get_bind().engine)
        with manager.keys.locked() as key, authority_transaction(db) as mutation:
            row, value = _record(db, key, installation_id, receipt["transaction_id"])
            if value is None:
                raise RelationalAuthorityError()
            data, context = value["data"], host_context
            permit = data["permit"]
            verify_metadata(transport_secret, "admission", permit)
            installation = db.get(Installation, installation_id, populate_existing=True)
            if (
                "recovery_fenced_by" in data
                or permit["mode"] != "write"
                or installation.instance_id != context.instance_id
                or any(
                    permit[field] != getattr(context, field)
                    for field in (
                        "instance_id",
                        "runtime_nonce",
                        "database_lineage",
                        "boot_id",
                        "authority_epoch",
                        "recovery_generation",
                    )
                )
                or mutation.guard.generation != context.recovery_generation
                or permit["boot_id"] != authority._clock()[0]
                or receipt["permit_sha256"] != permit_digest(permit)
                or receipt["database_lineage"] != permit["database_lineage"]
                or receipt["schema_revision"] != data["schema_revision"]
            ):
                raise RelationalAuthorityError()
            if value["state"] == "committed":
                if data["receipt"] != receipt:
                    raise RelationalAuthorityError()
            else:
                value.update(
                    state="committed", revision=authority.new_authority_generation()
                )
                data.update(outcome="committed", receipt=receipt)
                authority._save(db, key, "action", row, value)
                mutation.advance_guard_revision()
        return {
            "transaction_id": receipt["transaction_id"],
            "outcome": "committed",
            "historical": True,
        }
    except (
        authority.AuthorityManagementError,
        AuthorityReviewKeyError,
        SQLAlchemyError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OSError,
    ):
        db.rollback()
        raise RelationalAuthorityError() from None
