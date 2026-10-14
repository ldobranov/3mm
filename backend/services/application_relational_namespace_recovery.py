"""Private LOCAL-human reconciliation of empty bootstrap state, not DB recovery.

Requires fresh exact grants/native/session and preserves the original unknown
outcome. Superseded helpers cannot finish. No implicit approval, SQL or enable.
"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.services import application_authority_management as authority
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
    _RelationalNamespacePreparationTicket,
    _RelationalNamespaceRecoveryResult,
    _RelationalNamespaceRecoveryTicket,
    canonical,
    sign_metadata,
    verify_metadata,
)

STABLE = (
    "instance_id",
    "owner_sha256",
    "package_sha256",
    "service_sha256",
    "configuration_sha256",
    "profile_sha256",
    "schema_revision",
    "recovery_generation",
)


def _source(db, key, installation_id, source_id, secret):
    row = db.get(Action, source_id, populate_existing=True)
    value = authority._load(db, key, "action", row, source_id)
    if (
        value["installation_id"] != installation_id
        or value["data"].get("operation") != "relational_prepare_namespace"
        or value["state"] not in {"execution_unconfirmed", "prepared"}
    ):
        raise authority.AuthorityManagementError("namespace_source_unavailable")
    source = _RelationalNamespacePreparationTicket.model_validate(
        value["data"]["result"]["ticket"]
    ).model_dump(mode="json")
    verify_metadata(secret, "namespace_preparation", source)
    if (
        source["preparation_id"] != source_id
        or source["transport_key_sha256"] != hashlib.sha256(secret).hexdigest()
    ):
        raise authority.AuthorityManagementError("namespace_source_changed")
    return row, value, source


def issue_namespace_recovery(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    source_preparation_id,
    expected_grant_record_revision,
    choice,
    confirm_empty_bootstrap_reviewed,
    transport_secret,
):
    """Explicit confirm OR recoverable quarantine; existing history is not a grant.

    Current permission approval is still required. A new choice supersedes the
    original creation/older recovery through a sealed pointer, without inventing
    their outcomes or allowing a package/SQL migration. No path/helper I/O here.
    """
    if confirm_empty_bootstrap_reviewed is not True or choice not in {
        "confirm",
        "quarantine",
    }:
        raise authority.AuthorityManagementError(
            "namespace_recovery_confirmation_required"
        )
    source_id = authority._identifier(source_preparation_id)
    expected = authority._identifier(expected_grant_record_revision)
    prepared = manager._prepare(installation_id)
    with manager._write(
        installation_id,
        actor_token,
        request_id,
        "relational_namespace_recovery",
        {
            "source_preparation_id": source_id,
            "grant_record_revision": expected,
            "choice": choice,
        },
    ) as (db, key, mutation, actor, result):
        if result:
            raise authority.AuthorityManagementError(
                "namespace_recovery_ticket_consumed"
            )
        row, value, source = _source(
            db, key, installation_id, source_id, transport_secret
        )
        grant, definition = _current(manager, db, key, installation_id, prepared)
        bindings = _bindings(
            db, installation_id, prepared, grant, definition, mutation.guard.generation
        )
        if (
            grant["revision"] != expected
            or any(bindings[name] != source[name] for name in STABLE)
            or db.scalar(
                select(func.count())
                .select_from(Action)
                .where(Action.installation_id == installation_id)
            )
            >= MAX_PREPARATION_ACTIONS
        ):
            raise authority.AuthorityManagementError("namespace_recovery_changed")
        boot, now = authority._clock()
        result["ticket"] = _RelationalNamespaceRecoveryTicket.model_validate(
            sign_metadata(
                transport_secret,
                "namespace_recovery",
                {
                    "version": 1,
                    "action": (
                        "confirm_owned_namespace"
                        if choice == "confirm"
                        else "quarantine_owned_namespace"
                    ),
                    "preparation_id": request_id,
                    "source_preparation_id": source_id,
                    "source_ticket_sha256": hashlib.sha256(
                        canonical(source)
                    ).hexdigest(),
                    "database_lineage": source["database_lineage"],
                    **bindings,
                    **{
                        name: source[name]
                        for name in (
                            "service_uid",
                            "service_gid",
                            "coordinator_uid",
                            "transport_key_sha256",
                        )
                    },
                    "boot_id": boot,
                    "issued_at_ms": now,
                    "deadline_ms": now + 300000,
                },
            )
        ).model_dump(mode="json")
        value["data"]["namespace_recovery_id"] = request_id
        value["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, value)
    return result["ticket"]


def namespace_recovery_checkpoint(
    manager,
    installation_id,
    ticket,
    phase,
    *,
    actor_token,
    transport_secret,
    receipt=None,
):
    ticket = _RelationalNamespaceRecoveryTicket.model_validate(ticket).model_dump(
        mode="json"
    )
    verify_metadata(transport_secret, "namespace_recovery", ticket)
    if phase not in {"authorize", "begin", "check", "finish"} or (
        phase != "finish" and receipt is not None
    ):
        raise authority.AuthorityManagementError("invalid_namespace_recovery_phase")
    prepared = manager._prepare(installation_id)
    with (
        manager.keys.locked() as key,
        Session(manager.engine) as db,
        authority_transaction(db) as mutation,
    ):
        actor = list(_actor(db, actor_token))
        row = db.get(Action, ticket["preparation_id"], populate_existing=True)
        value = authority._load(db, key, "action", row, ticket["preparation_id"])
        _, source_value, source = _source(
            db, key, installation_id, ticket["source_preparation_id"], transport_secret
        )
        if (
            value["installation_id"] != installation_id
            or value["data"].get("operation") != "relational_namespace_recovery"
            or value["data"]["actor"] != actor
            or value["data"]["result"]["ticket"] != ticket
            or source_value["data"].get("namespace_recovery_id")
            != ticket["preparation_id"]
            or ticket["source_ticket_sha256"]
            != hashlib.sha256(canonical(source)).hexdigest()
            or any(
                ticket[name] != source[name]
                for name in (
                    *STABLE,
                    "database_lineage",
                    "service_uid",
                    "service_gid",
                    "coordinator_uid",
                    "transport_key_sha256",
                )
            )
        ):
            raise authority.AuthorityManagementError(
                "namespace_recovery_superseded_or_changed"
            )
        grant, definition = _current(manager, db, key, installation_id, prepared)
        boot, now = authority._clock()
        bindings = _bindings(
            db, installation_id, prepared, grant, definition, mutation.guard.generation
        )
        if (
            boot != ticket["boot_id"]
            or not ticket["issued_at_ms"] <= now < ticket["deadline_ms"]
            or any(ticket[name] != expected for name, expected in bindings.items())
        ):
            raise authority.AuthorityManagementError("namespace_recovery_changed")
        current = read_application_authority(db, installation_id)
        mutation.lock_application(current)
        if phase in {"authorize", "begin"}:
            if value["state"] != "recorded":
                raise authority.AuthorityManagementError(
                    "namespace_recovery_ticket_consumed"
                )
            if phase == "authorize":
                return {"state": "authorized_not_started"}
            value["state"] = "execution_unconfirmed"
        else:
            if value["state"] not in {"execution_unconfirmed", "confirmed"}:
                raise authority.AuthorityManagementError(
                    "namespace_recovery_not_started"
                )
            if phase == "check":
                if value["state"] == "confirmed":
                    raise authority.AuthorityManagementError(
                        "namespace_recovery_ticket_consumed"
                    )
                return {"state": "execution_unconfirmed"}
            receipt = _RelationalNamespaceRecoveryResult.model_validate(
                receipt
            ).model_dump(mode="json")
            verify_metadata(transport_secret, "namespace_recovery_result", receipt)
            expected_outcome = (
                "namespace_confirmed_not_started"
                if ticket["action"] == "confirm_owned_namespace"
                else "namespace_quarantined_not_started"
            )
            if (
                receipt["preparation_id"] != ticket["preparation_id"]
                or receipt["ticket_sha256"]
                != hashlib.sha256(canonical(ticket)).hexdigest()
                or receipt["outcome"] != expected_outcome
            ):
                raise authority.AuthorityManagementError(
                    "namespace_recovery_receipt_changed"
                )
            if value["state"] == "confirmed":
                if value["data"]["receipt"] != receipt:
                    raise authority.AuthorityManagementError(
                        "namespace_recovery_receipt_changed"
                    )
                return {"state": expected_outcome, "historical": True}
            value["state"] = "confirmed"
            value["data"]["receipt"] = receipt
        value["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, value)
        db.add(
            AuditLog(
                user_id=actor[0],
                action="APPLICATION_NAMESPACE_RECOVERY_" + phase.upper(),
                entity_type="application_extension",
                entity_name=current.module_id,
                changes={
                    "source_preparation_id": ticket["source_preparation_id"],
                    "recovery_id": ticket["preparation_id"],
                    "state": value["state"],
                },
            )
        )
        mutation.advance_guard_revision()
    return {
        "state": receipt["outcome"] if phase == "finish" else "execution_unconfirmed"
    }
