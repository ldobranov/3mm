"""Private LOCAL confirmation of a fully published upgrade, never SQL replay.

Only a new authenticated human action can reconcile a lost finish response.
The previous uncertainty is retained in the sealed journal; business outcomes,
permissions, lineage and runtime start authority are never inferred or renewed.
"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services import application_relational_lifecycle as preparation
from backend.services import application_relational_upgrade as upgrade
from backend.services.application_commands import invalidate_commands
from backend.services.application_policy_reviews import _actor
from backend.services.application_relational_activation import _start_consent
from backend.services.authority_metadata import (
    authority_transaction,
    read_application_authority,
)
from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeConfirmationTicket,
    _RelationalUpgradeResult,
    _RelationalUpgradeTicket,
    upgraded_lifecycle,
)
from three_mm_application_sdk.relational_wire import (
    canonical,
    sign_metadata,
    verify_metadata,
)

OPERATION = "relational_upgrade_confirmation"
POINTER = "upgrade_confirmation_id"
STABLE_FIELDS = (
    "instance_id",
    "database_lineage",
    "owner_sha256",
    "package_sha256",
    "service_sha256",
    "configuration_sha256",
    "profile_sha256",
    "schema_revision",
    "recovery_generation",
    "transport_key_sha256",
)


def _digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _source(db, key, installation_id, identifier, secret, *, rollback=False):
    row = db.get(Action, identifier, populate_existing=True)
    value = authority._load(db, key, "action", row, identifier)
    if (
        value["installation_id"] != installation_id
        or value["data"].get("operation") != upgrade.OPERATION
        or value["state"] not in {"execution_unconfirmed", "upgraded"}
        or rollback
        and value["state"] != "execution_unconfirmed"
        or not rollback
        and value["data"].get("rollback_confirmation_id") is not None
        or any(
            value["data"].get(name) is not None
            for name in ("activation_id", "upgrade_id", "recovery_id")
        )
    ):
        raise authority.AuthorityManagementError(
            "upgrade_confirmation_source_unavailable"
        )
    ticket = _RelationalUpgradeTicket.model_validate(
        value["data"]["result"]["ticket"]
    ).model_dump(mode="json")
    verify_metadata(secret, "database_upgrade", ticket)
    _, previous, old, digest = upgrade._source(
        db, key, installation_id, ticket["source_preparation_id"], secret
    )
    if (
        ticket["preparation_id"] != identifier
        or ticket["transport_key_sha256"] != hashlib.sha256(secret).hexdigest()
        or previous["data"].get("upgrade_id") != identifier
        or previous["data"].get("upgrade_source_revision")
        != ticket["source_preparation_revision"]
        or _digest(old) != ticket["source_ticket_sha256"]
        or digest != ticket["source_lifecycle_sha256"]
        or any(old[name] != ticket["source_" + name] for name in upgrade.SOURCE_FIELDS)
    ):
        raise authority.AuthorityManagementError("upgrade_confirmation_source_changed")
    receipt = sign_metadata(
        secret,
        "database_upgrade_result",
        {
            "version": 1,
            "preparation_id": identifier,
            "lifecycle_sha256": _digest(upgraded_lifecycle(ticket, secret)),
            "outcome": "upgraded_not_started",
        },
    )
    if value["state"] == "upgraded" and value["data"].get("receipt") != receipt:
        raise authority.AuthorityManagementError("upgrade_confirmation_source_changed")
    return row, value, ticket, receipt


def _confirmation(db, key, source, old, secret):
    identifier = source["data"][POINTER]
    row = db.get(Action, identifier, populate_existing=True)
    value = authority._load(db, key, "action", row, identifier)
    ticket = _RelationalUpgradeConfirmationTicket.model_validate(
        value["data"]["result"]["ticket"]
    ).model_dump(mode="json")
    verify_metadata(secret, "database_upgrade_confirmation", ticket)
    if (
        value["installation_id"] != source["installation_id"]
        or value["data"].get("operation") != OPERATION
        or value["state"] not in {"recorded", "execution_unconfirmed", "confirmed"}
        or value["data"].get("superseded_by") is not None
        or ticket["preparation_id"] != identifier
        or ticket["source_upgrade_id"] != old["preparation_id"]
        or ticket["source_ticket_sha256"] != _digest(old)
        or ticket["published_lifecycle_sha256"]
        != _digest(upgraded_lifecycle(old, secret))
        or any(ticket[name] != old[name] for name in STABLE_FIELDS)
    ):
        raise authority.AuthorityManagementError("upgrade_confirmation_changed")
    return row, value, ticket


def require_confirmed_upgrade(db, key, source, ticket, secret):
    """Completed history only, not fresh grant/start/migration authority."""
    if source["data"].get(POINTER) is None:
        return
    _, value, confirmation = _confirmation(db, key, source, ticket, secret)
    if value["state"] != "confirmed":
        raise authority.AuthorityManagementError("upgrade_confirmation_pending")
    receipt = _RelationalUpgradeResult.model_validate(
        value["data"].get("receipt")
    ).model_dump(mode="json")
    verify_metadata(secret, "database_upgrade_confirmation_result", receipt)
    if (
        receipt["preparation_id"] != confirmation["preparation_id"]
        or receipt["lifecycle_sha256"] != confirmation["published_lifecycle_sha256"]
    ):
        raise authority.AuthorityManagementError("upgrade_confirmation_pending")


def _current(
    manager, db, key, mutation, installation_id, prepared, ticket, *, live=True
):
    grant, definition = _start_consent(
        manager, db, key, installation_id, prepared, ticket
    )
    current = read_application_authority(db, installation_id)
    installed = db.get(Installation, installation_id, populate_existing=True)
    bindings = preparation._bindings(
        db, installation_id, prepared, grant, definition, mutation.guard.generation
    )
    boot, now = authority._clock()
    if (
        current.mode != "review_required"
        or installed.enabled
        or installed.status != "disabled"
        or live
        and (
            boot != ticket["boot_id"]
            or not ticket["issued_at_ms"] <= now < ticket["deadline_ms"]
        )
        or any(ticket[name] != expected for name, expected in bindings.items())
    ):
        raise authority.AuthorityManagementError("upgrade_confirmation_changed")
    return current, bindings


def issue_published_upgrade_confirmation(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    source_upgrade_id,
    expected_source_revision,
    expected_grant_record_revision,
    confirm_published_upgrade_reviewed,
    transport_secret,
):
    if confirm_published_upgrade_reviewed is not True:
        raise authority.AuthorityManagementError("upgrade_confirmation_required")
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
        },
    ) as (db, key, mutation, actor, result):
        if result:
            raise authority.AuthorityManagementError(
                "upgrade_confirmation_ticket_consumed"
            )
        row, source, old, receipt = _source(
            db, key, installation_id, source_id, transport_secret
        )
        previous = None
        binding = old
        if source["data"].get(POINTER) is not None:
            previous = _confirmation(db, key, source, old, transport_secret)
            binding = previous[2]
        current, bindings = _current(
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
            raise authority.AuthorityManagementError("upgrade_confirmation_unavailable")
        invalidate_commands(db, installation_id)
        bindings["authority_epoch"] = mutation.set_application_mode(
            current, "review_required"
        ).epoch
        boot, now = authority._clock()
        result["ticket"] = _RelationalUpgradeConfirmationTicket.model_validate(
            sign_metadata(
                transport_secret,
                "database_upgrade_confirmation",
                {
                    "version": 1,
                    "action": "confirm_published_upgrade",
                    "preparation_id": request_id,
                    "source_upgrade_id": source_id,
                    "source_ticket_sha256": _digest(old),
                    "published_lifecycle_sha256": receipt["lifecycle_sha256"],
                    "database_lineage": old["database_lineage"],
                    "transport_key_sha256": old["transport_key_sha256"],
                    **bindings,
                    "boot_id": boot,
                    "issued_at_ms": now,
                    "deadline_ms": now + 300000,
                },
            )
        ).model_dump(mode="json")
        if previous is not None:
            previous_row, value, _ = previous
            value["data"]["superseded_by"] = request_id
            value["revision"] = authority.new_authority_generation()
            authority._save(db, key, "action", previous_row, value)
        source["data"][POINTER] = request_id
        source["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, source)
    return result["ticket"]


def upgrade_confirmation_checkpoint(
    manager,
    installation_id,
    ticket,
    phase,
    *,
    actor_token,
    transport_secret,
    receipt=None,
):
    ticket = _RelationalUpgradeConfirmationTicket.model_validate(ticket).model_dump(
        mode="json"
    )
    verify_metadata(transport_secret, "database_upgrade_confirmation", ticket)
    if (
        phase not in {"authorize", "begin", "check", "finish"}
        or phase != "finish"
        and receipt is not None
        or ticket["transport_key_sha256"]
        != hashlib.sha256(transport_secret).hexdigest()
    ):
        raise authority.AuthorityManagementError("invalid_upgrade_confirmation_phase")
    prepared = manager._prepare(installation_id)
    with (
        manager.keys.locked() as key,
        Session(manager.engine) as db,
        authority_transaction(db) as mutation,
    ):
        actor = list(_actor(db, actor_token))
        source_row, source, old, old_receipt = _source(
            db, key, installation_id, ticket["source_upgrade_id"], transport_secret
        )
        row, value, issued = _confirmation(db, key, source, old, transport_secret)
        if issued != ticket or value["data"]["actor"] != actor:
            raise authority.AuthorityManagementError("upgrade_confirmation_unavailable")
        current, _ = _current(
            manager, db, key, mutation, installation_id, prepared, ticket
        )
        mutation.lock_application(current)
        if phase in {"authorize", "begin"}:
            if value["state"] != "recorded":
                raise authority.AuthorityManagementError(
                    "upgrade_confirmation_ticket_consumed"
                )
            if phase == "authorize":
                return {"state": "authorized_not_started"}
            value["state"] = "execution_unconfirmed"
        else:
            if value["state"] not in {"execution_unconfirmed", "confirmed"}:
                raise authority.AuthorityManagementError(
                    "upgrade_confirmation_not_started"
                )
            if phase == "check":
                if value["state"] == "confirmed":
                    raise authority.AuthorityManagementError(
                        "upgrade_confirmation_ticket_consumed"
                    )
                return {"state": "execution_unconfirmed"}
            receipt = _RelationalUpgradeResult.model_validate(receipt).model_dump(
                mode="json"
            )
            verify_metadata(
                transport_secret, "database_upgrade_confirmation_result", receipt
            )
            if (
                receipt["preparation_id"] != ticket["preparation_id"]
                or receipt["lifecycle_sha256"] != ticket["published_lifecycle_sha256"]
            ):
                raise authority.AuthorityManagementError(
                    "upgrade_confirmation_receipt_changed"
                )
            if value["state"] == "confirmed":
                if value["data"]["receipt"] != receipt:
                    raise authority.AuthorityManagementError(
                        "upgrade_confirmation_receipt_changed"
                    )
                return {"state": "upgraded_not_started", "historical": True}
            # This is a separately audited reconciliation, not replay of finish.
            # Preserve the prior uncertain lifecycle outcome explicitly. Other
            # transaction/command/outbox outcomes are not changed by confirmation.
            if source["state"] != "upgraded":
                source["data"]["confirmation_previous_state"] = source["state"]
                source["state"] = "upgraded"
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
                action="APPLICATION_RELATIONAL_UPGRADE_CONFIRMATION_" + phase.upper(),
                entity_type="application_extension",
                entity_name=current.module_id,
                changes={
                    "confirmation_id": ticket["preparation_id"],
                    "source_upgrade_id": ticket["source_upgrade_id"],
                    "state": value["state"],
                },
            )
        )
        mutation.advance_guard_revision()
    return {
        "state": (
            "upgraded_not_started" if phase == "finish" else "execution_unconfirmed"
        )
    }
