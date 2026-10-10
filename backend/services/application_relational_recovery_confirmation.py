"""Private human reconciliation of an already published recovery, never SQL replay.

Fresh bounded authority only confirms exact readonly helper evidence and archives
blocking markers. Previous actions/receipts survive; no automatic ticket renewal,
grant restoration, rekey, migration, service enable or external-outcome resolution.
"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.services import application_authority_management as authority
from backend.services.application_policy_reviews import _actor
from backend.services.application_relational_lifecycle import MAX_PREPARATION_ACTIONS
from backend.services.application_relational_recovery import _current_recovery
from backend.services.authority_metadata import authority_transaction
from three_mm_application_sdk.relational_wire import (
    _RelationalPreparationResult,
    _RelationalRecoveryConfirmationTicket,
    _RelationalRecoveryTicket,
    canonical,
    recovered_lifecycle,
    sign_metadata,
    verify_metadata,
)


def _source(db, key, installation_id, source_id, secret):
    row = db.get(Action, source_id, populate_existing=True)
    value = authority._load(db, key, "action", row, source_id)
    if (
        value["installation_id"] != installation_id
        or value["data"].get("operation") != "relational_recovery"
        or value["state"] not in {"execution_unconfirmed", "recovered"}
    ):
        raise authority.AuthorityManagementError("confirmation_source_unavailable")
    ticket = _RelationalRecoveryTicket.model_validate(
        value["data"]["result"]["ticket"]
    ).model_dump(mode="json")
    verify_metadata(secret, "recovery", ticket)
    if ticket["preparation_id"] != source_id:
        raise authority.AuthorityManagementError("confirmation_source_changed")
    receipt = sign_metadata(
        secret,
        "recovery_result",
        {
            "version": 1,
            "preparation_id": source_id,
            "lifecycle_sha256": hashlib.sha256(
                canonical(recovered_lifecycle(ticket, secret))
            ).hexdigest(),
            "outcome": "prepared_not_started",
        },
    )
    if value["state"] == "recovered" and value["data"]["receipt"] != receipt:
        raise authority.AuthorityManagementError("confirmation_source_changed")
    return row, value, ticket, receipt


def issue_published_recovery_confirmation(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    source_recovery_id,
    expected_grant_record_revision,
    confirm_published_recovery_reviewed,
    transport_secret,
):
    if confirm_published_recovery_reviewed is not True:
        raise authority.AuthorityManagementError("confirmation_required")
    source_id = authority._identifier(source_recovery_id)
    expected = authority._identifier(expected_grant_record_revision)
    prepared = manager._prepare(installation_id)
    with manager._write(
        installation_id,
        actor_token,
        request_id,
        "relational_recovery_confirmation",
        {"source_recovery_id": source_id, "grant_record_revision": expected},
    ) as (db, key, mutation, actor, result):
        if result:
            raise authority.AuthorityManagementError("confirmation_ticket_consumed")
        row, source, old, receipt = _source(
            db, key, installation_id, source_id, transport_secret
        )
        base, binding = source, old
        # Each retry is a NEW explicit human action, not re-delivery of a consumed
        # ticket. Preserve uncertain previous confirmation, fence it by pointer
        # and epoch, and require its exact current binding (not its old deadline).
        previous_id = source["data"].get("confirmation_id")
        if previous_id is not None:
            previous_row = db.get(Action, previous_id, populate_existing=True)
            base = authority._load(db, key, "action", previous_row, previous_id)
            binding = _RelationalRecoveryConfirmationTicket.model_validate(
                base["data"]["result"]["ticket"]
            ).model_dump(mode="json")
            verify_metadata(transport_secret, "recovery_confirmation", binding)
            if (
                base["installation_id"] != installation_id
                or base["data"].get("operation") != "relational_recovery_confirmation"
                or binding["preparation_id"] != previous_id
                or binding["source_recovery_id"] != source_id
                or binding["source_ticket_sha256"]
                != hashlib.sha256(canonical(old)).hexdigest()
            ):
                raise authority.AuthorityManagementError("confirmation_source_changed")
        current, bindings = _current_recovery(
            manager,
            db,
            key,
            mutation,
            installation_id,
            prepared,
            base,
            binding,
            live=False,
        )
        if (
            bindings["grant_record_revision"] != expected
            or db.scalar(
                select(func.count())
                .select_from(Action)
                .where(Action.installation_id == installation_id)
            )
            >= MAX_PREPARATION_ACTIONS
        ):
            raise authority.AuthorityManagementError("confirmation_unavailable")
        bindings["authority_epoch"] = mutation.set_application_mode(
            current, "review_required"
        ).epoch
        boot, now = authority._clock()
        result["ticket"] = _RelationalRecoveryConfirmationTicket.model_validate(
            sign_metadata(
                transport_secret,
                "recovery_confirmation",
                {
                    "version": 1,
                    "action": "confirm_published_recovery",
                    "preparation_id": request_id,
                    "source_recovery_id": source_id,
                    "source_ticket_sha256": hashlib.sha256(canonical(old)).hexdigest(),
                    "published_lifecycle_sha256": receipt["lifecycle_sha256"],
                    "database_lineage": old["database_lineage"],
                    **bindings,
                    "boot_id": boot,
                    "issued_at_ms": now,
                    "deadline_ms": now + 300000,
                },
            )
        ).model_dump(mode="json")
        result["native_review_id"] = source["data"]["result"]["native_review_id"]
        result["native_revision"] = source["data"]["result"]["native_revision"]
        if previous_id is not None:
            base["data"]["superseded_by"] = request_id
            base["revision"] = authority.new_authority_generation()
            authority._save(db, key, "action", previous_row, base)
        source["data"]["confirmation_id"] = request_id
        source["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, source)
    return result["ticket"]


def confirmation_checkpoint(
    manager,
    installation_id,
    ticket,
    phase,
    *,
    actor_token,
    transport_secret,
    receipt=None,
):
    ticket = _RelationalRecoveryConfirmationTicket.model_validate(ticket).model_dump(
        mode="json"
    )
    verify_metadata(transport_secret, "recovery_confirmation", ticket)
    if phase not in {"authorize", "begin", "check", "finish"} or (
        phase != "finish" and receipt is not None
    ):
        raise authority.AuthorityManagementError("invalid_confirmation_phase")
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
            or value["data"].get("operation") != "relational_recovery_confirmation"
            or value["data"]["actor"] != actor
            or value["data"]["result"]["ticket"] != ticket
        ):
            raise authority.AuthorityManagementError("confirmation_unavailable")
        source_row, source, old, old_receipt = _source(
            db, key, installation_id, ticket["source_recovery_id"], transport_secret
        )
        if (
            source["data"].get("confirmation_id") != ticket["preparation_id"]
            or ticket["source_ticket_sha256"]
            != hashlib.sha256(canonical(old)).hexdigest()
            or ticket["published_lifecycle_sha256"] != old_receipt["lifecycle_sha256"]
            or ticket["database_lineage"] != old["database_lineage"]
        ):
            raise authority.AuthorityManagementError("confirmation_source_changed")
        current, _ = _current_recovery(
            manager, db, key, mutation, installation_id, prepared, value, ticket
        )
        mutation.lock_application(current)
        if phase in {"authorize", "begin"}:
            if value["state"] != "recorded":
                raise authority.AuthorityManagementError("confirmation_ticket_consumed")
            if phase == "authorize":
                return {"state": "authorized_not_started"}
            value["state"] = "execution_unconfirmed"
        else:
            if value["state"] not in {"execution_unconfirmed", "confirmed"}:
                raise authority.AuthorityManagementError("confirmation_not_started")
            if phase == "check":
                if value["state"] == "confirmed":
                    raise authority.AuthorityManagementError(
                        "confirmation_ticket_consumed"
                    )
                return {"state": "execution_unconfirmed"}
            receipt = _RelationalPreparationResult.model_validate(receipt).model_dump(
                mode="json"
            )
            verify_metadata(transport_secret, "recovery_confirmation_result", receipt)
            if (
                receipt["preparation_id"] != ticket["preparation_id"]
                or receipt["lifecycle_sha256"] != ticket["published_lifecycle_sha256"]
            ):
                raise authority.AuthorityManagementError("confirmation_receipt_changed")
            if value["state"] == "confirmed":
                if value["data"]["receipt"] != receipt:
                    raise authority.AuthorityManagementError(
                        "confirmation_receipt_changed"
                    )
                return {"state": "prepared_not_started", "historical": True}
            # The original receipt keeps its original ID/purpose/lineage. Preserve
            # its prior unknown state as evidence of this separate resolution.
            if source["state"] != "recovered":
                source["data"]["confirmation_previous_state"] = source["state"]
                source["state"] = "recovered"
                source["data"]["receipt"] = old_receipt
                source["revision"] = authority.new_authority_generation()
                authority._save(db, key, "action", source_row, source)
            value["state"] = "confirmed"
            value["data"]["receipt"] = receipt
        value["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, value)
        db.add(
            AuditLog(
                user_id=actor[0],
                action="APPLICATION_RELATIONAL_CONFIRMATION_" + phase.upper(),
                entity_type="application_extension",
                entity_name=current.module_id,
                changes={
                    "confirmation_id": ticket["preparation_id"],
                    "source_recovery_id": ticket["source_recovery_id"],
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
