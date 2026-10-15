"""Private LOCAL rollback confirmation and separate partial-restore consent.

The original upgrade remains execution_unconfirmed. Only a separate confirmed
rollback allows a NEW reviewed forward attempt to reserve the restored source.
No automatic package switch, start, permission restoration or SQL outcome repair.
"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.services import application_authority_management as authority
from backend.services import application_relational_lifecycle as preparation
from backend.services import application_relational_upgrade_confirmation as published
from backend.services.application_commands import invalidate_commands
from backend.services.application_policy_reviews import _actor
from backend.services.authority_metadata import authority_transaction
from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeRestoreTicket,
    _RelationalUpgradeRollbackResult,
    _RelationalUpgradeRollbackTicket,
    _rollback_ticket,
)
from three_mm_application_sdk.relational_wire import (
    canonical,
    sign_metadata,
    verify_metadata,
)

OPERATION = "relational_upgrade_rollback_confirmation"
POINTER = "rollback_confirmation_id"


def _digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _confirmation(db, key, source, old, secret):
    identifier = source["data"][POINTER]
    row = db.get(Action, identifier, populate_existing=True)
    value = authority._load(db, key, "action", row, identifier)
    ticket, purpose = _rollback_ticket(value["data"]["result"]["ticket"])
    verify_metadata(secret, purpose, ticket)
    if (
        value["installation_id"] != source["installation_id"]
        or value["data"].get("operation") != OPERATION
        or value["state"] not in {"recorded", "execution_unconfirmed", "confirmed"}
        or value["data"].get("superseded_by") is not None
        or ticket["preparation_id"] != identifier
        or ticket["source_upgrade_id"] != old["preparation_id"]
        or ticket["source_ticket_sha256"] != _digest(old)
        or ticket["restored_lifecycle_sha256"] != old["source_lifecycle_sha256"]
        or ticket["database_lineage"] != old["source_database_lineage"]
        or any(
            ticket[name] != old[name]
            for name in published.STABLE_FIELDS
            if name != "database_lineage"
        )
    ):
        raise authority.AuthorityManagementError("rollback_confirmation_changed")
    return row, value, ticket


def require_confirmed_rollback(db, key, previous, old, secret):
    """Only permits issuing a NEW upgrade; never start or historical ACK replay."""
    _, failed, ticket, _ = published._source(
        db,
        key,
        previous["installation_id"],
        previous["data"]["upgrade_id"],
        secret,
        rollback=True,
    )
    if (
        _digest(old) != ticket["source_ticket_sha256"]
        or failed["data"].get(POINTER) is None
    ):
        raise authority.AuthorityManagementError("rollback_confirmation_pending")
    _, value, confirmation = _confirmation(db, key, failed, ticket, secret)
    if value["state"] != "confirmed":
        raise authority.AuthorityManagementError("rollback_confirmation_pending")
    receipt = _RelationalUpgradeRollbackResult.model_validate(
        value["data"]["receipt"]
    ).model_dump(mode="json")
    verify_metadata(secret, "database_upgrade_rollback_result", receipt)
    if (
        receipt["preparation_id"] != confirmation["preparation_id"]
        or receipt["source_upgrade_id"] != ticket["preparation_id"]
        or receipt["lifecycle_sha256"] != ticket["source_lifecycle_sha256"]
    ):
        raise authority.AuthorityManagementError("rollback_confirmation_changed")


def issue_restored_upgrade_confirmation(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    source_upgrade_id,
    expected_source_revision,
    expected_grant_record_revision,
    confirm_restored_state_reviewed,
    transport_secret,
    confirm_finish_interrupted_restore=False,
):
    if (
        type(confirm_finish_interrupted_restore) is not bool
        or confirm_restored_state_reviewed is not True
    ):
        raise authority.AuthorityManagementError("rollback_confirmation_required")
    source_id = authority._identifier(source_upgrade_id)
    expected_source = authority._identifier(expected_source_revision)
    expected_grant = authority._identifier(expected_grant_record_revision)
    prepared = manager._prepare(installation_id)
    with manager._write(
        installation_id,
        actor_token,
        request_id,
        OPERATION,
        {
            "source_upgrade_id": source_id,
            "source_revision": expected_source,
            "grant_record_revision": expected_grant,
            "finish_interrupted_restore": confirm_finish_interrupted_restore,
        },
    ) as (db, key, mutation, actor, result):
        if result:
            raise authority.AuthorityManagementError(
                "rollback_confirmation_ticket_consumed"
            )
        row, source, old, _ = published._source(
            db, key, installation_id, source_id, transport_secret, rollback=True
        )
        prior, binding = None, old
        if source["data"].get(POINTER) is not None:
            prior = _confirmation(db, key, source, old, transport_secret)
            binding = prior[2]
        elif source["data"].get(published.POINTER) is not None:
            prior = published._confirmation(db, key, source, old, transport_secret)
            binding = prior[2]
        current, bindings = published._current(
            manager, db, key, mutation, installation_id, prepared, binding, live=False
        )
        if (
            source["revision"] != expected_source
            or bindings["grant_record_revision"] != expected_grant
            or db.scalar(
                select(func.count())
                .select_from(Action)
                .where(Action.installation_id == installation_id)
            )
            >= preparation.MAX_PREPARATION_ACTIONS
        ):
            raise authority.AuthorityManagementError(
                "rollback_confirmation_unavailable"
            )
        invalidate_commands(db, installation_id)
        bindings["authority_epoch"] = mutation.set_application_mode(
            current, "review_required"
        ).epoch
        boot, now = authority._clock()
        model, purpose, operation = (
            (
                _RelationalUpgradeRestoreTicket,
                "database_upgrade_restore",
                "finish_interrupted_upgrade_restore",
            )
            if confirm_finish_interrupted_restore
            else (
                _RelationalUpgradeRollbackTicket,
                "database_upgrade_rollback",
                "confirm_restored_upgrade",
            )
        )
        result["ticket"] = model.model_validate(
            sign_metadata(
                transport_secret,
                purpose,
                {
                    "version": 1,
                    "action": operation,
                    "preparation_id": request_id,
                    "source_upgrade_id": source_id,
                    "source_ticket_sha256": _digest(old),
                    "restored_lifecycle_sha256": old["source_lifecycle_sha256"],
                    "database_lineage": old["source_database_lineage"],
                    "transport_key_sha256": old["transport_key_sha256"],
                    **bindings,
                    "boot_id": boot,
                    "issued_at_ms": now,
                    "deadline_ms": now + 300000,
                },
            )
        ).model_dump(mode="json")
        if prior is not None:
            prior_row, value, _ = prior
            value["data"]["superseded_by"] = request_id
            value["revision"] = authority.new_authority_generation()
            authority._save(db, key, "action", prior_row, value)
        source["data"][POINTER] = request_id
        source["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, source)
    return result["ticket"]


def rollback_confirmation_checkpoint(
    manager,
    installation_id,
    ticket,
    phase,
    *,
    actor_token,
    transport_secret,
    receipt=None,
):
    ticket, purpose = _rollback_ticket(ticket)
    verify_metadata(transport_secret, purpose, ticket)
    if (
        phase not in {"authorize", "begin", "check", "finish"}
        or phase != "finish"
        and receipt is not None
        or ticket["transport_key_sha256"]
        != hashlib.sha256(transport_secret).hexdigest()
    ):
        raise authority.AuthorityManagementError("invalid_rollback_confirmation_phase")
    prepared = manager._prepare(installation_id)
    with (
        manager.keys.locked() as key,
        Session(manager.engine) as db,
        authority_transaction(db) as mutation,
    ):
        actor = list(_actor(db, actor_token))
        _, source, old, _ = published._source(
            db,
            key,
            installation_id,
            ticket["source_upgrade_id"],
            transport_secret,
            rollback=True,
        )
        row, value, issued = _confirmation(db, key, source, old, transport_secret)
        if issued != ticket or value["data"]["actor"] != actor:
            raise authority.AuthorityManagementError(
                "rollback_confirmation_unavailable"
            )
        current, _ = published._current(
            manager, db, key, mutation, installation_id, prepared, ticket
        )
        mutation.lock_application(current)
        if phase in {"authorize", "begin"}:
            if value["state"] != "recorded":
                raise authority.AuthorityManagementError(
                    "rollback_confirmation_ticket_consumed"
                )
            if phase == "authorize":
                return {"state": "authorized_not_started"}
            value["state"] = "execution_unconfirmed"
        else:
            if value["state"] not in {"execution_unconfirmed", "confirmed"}:
                raise authority.AuthorityManagementError(
                    "rollback_confirmation_not_started"
                )
            if phase == "check":
                if value["state"] == "confirmed":
                    raise authority.AuthorityManagementError(
                        "rollback_confirmation_ticket_consumed"
                    )
                return {"state": "execution_unconfirmed"}
            receipt = _RelationalUpgradeRollbackResult.model_validate(
                receipt
            ).model_dump(mode="json")
            verify_metadata(
                transport_secret, "database_upgrade_rollback_result", receipt
            )
            if (
                receipt["preparation_id"] != ticket["preparation_id"]
                or receipt["source_upgrade_id"] != ticket["source_upgrade_id"]
                or receipt["lifecycle_sha256"] != ticket["restored_lifecycle_sha256"]
            ):
                raise authority.AuthorityManagementError(
                    "rollback_confirmation_receipt_changed"
                )
            if value["state"] == "confirmed":
                if value["data"]["receipt"] != receipt:
                    raise authority.AuthorityManagementError(
                        "rollback_confirmation_receipt_changed"
                    )
                return {"state": "restored_not_started", "historical": True}
            value["state"] = "confirmed"
            value["data"]["receipt"] = receipt
        value["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, value)
        db.add(
            AuditLog(
                user_id=actor[0],
                action="APPLICATION_RELATIONAL_ROLLBACK_CONFIRMATION_" + phase.upper(),
                entity_type="application_extension",
                entity_name=current.module_id,
                changes={
                    "confirmation_id": ticket["preparation_id"],
                    "source_upgrade_id": ticket["source_upgrade_id"],
                    "consent_action": ticket["action"],
                    "state": value["state"],
                },
            )
        )
        mutation.advance_guard_revision()
    return {
        "state": (
            "restored_not_started" if phase == "finish" else "execution_unconfirmed"
        )
    }
