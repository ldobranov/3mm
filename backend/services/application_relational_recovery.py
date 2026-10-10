"""Private LOCAL-human recovery of a published relational preparation.

Not a generic restore API. Only the exact installed reviewed-native candidate
can be accepted; no migration/external-effect replay or implicit rekey. Existing
sealed Action records provide the one-use journal. Core leases never span SQL,
runtime filesystem or helper calls. Production dispatch remains gated.
"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services.application_commands import invalidate_commands
from backend.services.application_policy_reviews import _actor
from backend.services.application_relational_lifecycle import (
    MAX_PREPARATION_ACTIONS,
    _bindings,
    _current,
)
from backend.services.authority_metadata import (
    authority_transaction,
    read_application_authority,
)
from three_mm_application_sdk.relational_wire import (
    _preparation_ticket,
    _RelationalPreparationResult,
    _RelationalRecoveryTicket,
    canonical,
    prepared_lifecycle,
    recovered_lifecycle,
    sign_metadata,
    verify_metadata,
)


def issue_prepared_candidate_recovery(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    source_preparation_id,
    expected_grant_record_revision,
    confirm_candidate_and_uncertain_outcomes_reviewed,
    transport_secret,
):
    """New authenticated human action, not renewal of the old expired ticket.

    Fences the old epoch immediately, even if delivery/SQL later fails. A fresh
    permission review is required after recovery. Confirmation does NOT resolve
    other uncertain commands/outbox/external effects. No artifact/body/path
    supplied by an application becomes lifecycle authority.
    """
    if confirm_candidate_and_uncertain_outcomes_reviewed is not True:
        raise authority.AuthorityManagementError("recovery_confirmation_required")
    source_id = authority._identifier(source_preparation_id)
    expected = authority._identifier(expected_grant_record_revision)
    prepared = manager._prepare(installation_id)
    with manager._write(
        installation_id,
        actor_token,
        request_id,
        "relational_recovery",
        {"source_preparation_id": source_id, "grant_record_revision": expected},
    ) as (db, key, mutation, actor, result):
        if result:
            raise authority.AuthorityManagementError("recovery_ticket_consumed")
        grant, definition = _current(manager, db, key, installation_id, prepared)
        if (
            grant["revision"] != expected
            or db.scalar(
                select(func.count())
                .select_from(Action)
                .where(Action.installation_id == installation_id)
            )
            >= MAX_PREPARATION_ACTIONS
        ):
            raise authority.AuthorityManagementError("recovery_unavailable")
        row = db.get(Action, source_id, populate_existing=True)
        source = authority._load(db, key, "action", row, source_id)
        if (
            source["installation_id"] != installation_id
            or source["state"] not in {"prepared", "execution_unconfirmed"}
            or "recovery_id" in source["data"]
            or source["data"].get("operation")
            not in {"relational_prepare", "relational_prepare_migrated"}
        ):
            raise authority.AuthorityManagementError("recovery_source_unavailable")
        old, purpose = _preparation_ticket(source["data"]["result"]["ticket"])
        verify_metadata(transport_secret, purpose, old)
        current = _bindings(
            db, installation_id, prepared, grant, definition, mutation.guard.generation
        )
        pinned = (
            "instance_id",
            "owner_sha256",
            "package_sha256",
            "service_sha256",
            "configuration_sha256",
            "profile_sha256",
            "schema_revision",
            "recovery_generation",
        )
        if old["preparation_id"] != source_id or any(
            old[name] != current[name] for name in pinned
        ):
            raise authority.AuthorityManagementError("recovery_source_changed")
        # Preserve the original action, outcome, receipt and actor as evidence.
        # Only a separate recovery reference is appended; no historical grant is
        # rewritten into fresh authority and no command is marked successful.
        # Revoke alone permits completion of already admitted SQL; recovery must
        # additionally prevent an OLD live host/context from acknowledging old
        # lineage evidence. Fence the bounded existing records, not their outcome.
        for transaction_row in db.scalars(
            select(Action)
            .where(Action.installation_id == installation_id)
            .limit(MAX_PREPARATION_ACTIONS)
        ):
            transaction = authority._load(
                db, key, "action", transaction_row, transaction_row.request_id
            )
            if transaction["data"].get("operation") == "relational_transaction":
                permit = transaction["data"]["permit"]
                if (
                    permit["database_lineage"] == old["database_lineage"]
                    and permit["instance_id"] == old["instance_id"]
                ):
                    transaction["data"]["recovery_fenced_by"] = request_id
                    transaction["revision"] = authority.new_authority_generation()
                    authority._save(db, key, "action", transaction_row, transaction)
        invalidate_commands(db, installation_id)
        resulting = mutation.set_application_mode(
            read_application_authority(db, installation_id), "review_required"
        )
        current["authority_epoch"] = resulting.epoch
        boot, now = authority._clock()
        result["ticket"] = _RelationalRecoveryTicket.model_validate(
            sign_metadata(
                transport_secret,
                "recovery",
                {
                    "version": 1,
                    "action": "accept_prepared_candidate",
                    "preparation_id": request_id,
                    "source_preparation_id": source_id,
                    "source_lifecycle_sha256": hashlib.sha256(
                        canonical(prepared_lifecycle(old, transport_secret))
                    ).hexdigest(),
                    "database_lineage": authority.new_authority_generation(),
                    **current,
                    "boot_id": boot,
                    "issued_at_ms": now,
                    "deadline_ms": now + 300000,
                },
            )
        ).model_dump(mode="json")
        result["native_review_id"] = grant["data"]["native_review_id"]
        result["native_revision"] = grant["data"]["native_revision"]
        source["data"]["recovery_id"] = request_id
        source["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, source)
    return result["ticket"]


def _current_recovery(
    manager, db, key, mutation, installation_id, prepared, value, ticket, *, live=True
):
    """Exact disabled review binding; old grants are evidence, not runtime rights."""
    from backend.db.application_authority_grant import (
        ApplicationAuthorityGrant as Grant,
    )

    subject = manager._subject(db, key, installation_id, prepared)
    native, _ = manager._policy(
        db, key, subject, value["data"]["result"]["native_review_id"]
    )
    current = read_application_authority(db, installation_id)
    installation = db.get(Installation, installation_id, populate_existing=True)
    grant = authority._load(
        db,
        key,
        "grant",
        db.get(Grant, installation_id, populate_existing=True),
        installation_id,
    )
    definition = prepared[1].application_extension
    if definition is None or definition.storage.relational is None:
        raise authority.AuthorityManagementError("recovery_changed")
    boot, now = authority._clock()
    expected = _bindings(
        db, installation_id, prepared, grant, definition, mutation.guard.generation
    )
    if (
        installation.enabled
        or installation.status != "disabled"
        or current.mode != "review_required"
        or installation.instance_id != expected["instance_id"]
        or live
        and (
            boot != ticket["boot_id"]
            or not ticket["issued_at_ms"] <= now < ticket["deadline_ms"]
        )
        or native["revision"] != value["data"]["result"]["native_revision"]
        or any(ticket[name] != item for name, item in expected.items())
    ):
        raise authority.AuthorityManagementError("recovery_changed")
    return current, expected


def recovery_checkpoint(
    manager,
    installation_id,
    ticket,
    phase,
    *,
    actor_token,
    transport_secret,
    receipt=None,
):
    ticket = _RelationalRecoveryTicket.model_validate(ticket).model_dump(mode="json")
    verify_metadata(transport_secret, "recovery", ticket)
    if (
        phase not in {"authorize", "begin", "check", "finish"}
        or phase != "finish"
        and receipt is not None
    ):
        raise authority.AuthorityManagementError("invalid_recovery_phase")
    prepared = manager._prepare(installation_id)
    with (
        manager.keys.locked() as key,
        Session(manager.engine) as db,
        authority_transaction(db) as mutation,
    ):
        actor = list(_actor(db, actor_token))
        row = db.get(Action, ticket["preparation_id"], populate_existing=True)
        value = authority._load(db, key, "action", row, ticket["preparation_id"])
        if (
            value["installation_id"] != installation_id
            or value["data"].get("operation") != "relational_recovery"
            or "confirmation_id" in value["data"]
            or value["data"]["actor"] != actor
            or value["data"]["result"]["ticket"] != ticket
        ):
            raise authority.AuthorityManagementError("recovery_unavailable")
        current, _ = _current_recovery(
            manager, db, key, mutation, installation_id, prepared, value, ticket
        )
        mutation.lock_application(current)
        if phase in {"authorize", "begin"}:
            if value["state"] != "recorded":
                raise authority.AuthorityManagementError("recovery_ticket_consumed")
            if phase == "authorize":
                return {"state": "authorized_not_started"}
            value["state"] = "execution_unconfirmed"
        else:
            if value["state"] not in {"execution_unconfirmed", "recovered"}:
                raise authority.AuthorityManagementError("recovery_not_started")
            if phase == "check":
                if value["state"] != "execution_unconfirmed":
                    raise authority.AuthorityManagementError("recovery_ticket_consumed")
                return {"state": "execution_unconfirmed"}
            receipt = _RelationalPreparationResult.model_validate(receipt).model_dump(
                mode="json"
            )
            verify_metadata(transport_secret, "recovery_result", receipt)
            if (
                receipt["preparation_id"] != ticket["preparation_id"]
                or receipt["lifecycle_sha256"]
                != hashlib.sha256(
                    canonical(recovered_lifecycle(ticket, transport_secret))
                ).hexdigest()
            ):
                raise authority.AuthorityManagementError("recovery_receipt_changed")
            if value["state"] == "recovered":
                if value["data"]["receipt"] != receipt:
                    raise authority.AuthorityManagementError("recovery_receipt_changed")
                return {"state": "prepared_not_started", "historical": True}
            value["state"] = "recovered"
            value["data"]["receipt"] = receipt
        value["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, value)
        db.add(
            AuditLog(
                user_id=actor[0],
                action="APPLICATION_RELATIONAL_RECOVERY_" + phase.upper(),
                entity_type="application_extension",
                entity_name=current.module_id,
                changes={
                    "recovery_id": ticket["preparation_id"],
                    "source_preparation_id": ticket["source_preparation_id"],
                    "state": value["state"],
                },
            )
        )
        mutation.advance_guard_revision()
    return {
        "state": (
            "prepared_not_started" if phase == "finish" else "execution_unconfirmed"
        )
    }
