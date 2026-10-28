"""Private LOCAL human forward upgrade; no staging API or I/O under Core leases.

The target must already be the exact reviewed installed binding. This does not
switch a catalog version, authorize unreviewed code or start/regrant an app.
"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services import application_relational_lifecycle as preparation
from backend.services.application_commands import invalidate_commands
from backend.services.application_requirements import require_platform_requirements
from backend.services.application_policy_reviews import _actor
from backend.services.application_relational_activation import _start_consent
from backend.services.authority_metadata import (
    authority_transaction,
    read_application_authority,
)
from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeResult,
    _RelationalUpgradeTicket,
    upgrade_worker_profile_digest,
    upgraded_lifecycle,
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

OPERATION = "relational_upgrade_prepared"
SOURCE_FIELDS = (
    "package_sha256",
    "service_sha256",
    "configuration_sha256",
    "profile_sha256",
    "schema_revision",
    "database_lineage",
)


def _source(db, key, installation_id, identifier, secret):
    row = db.get(Action, identifier, populate_existing=True)
    value = authority._load(db, key, "action", row, identifier)
    if (
        value["installation_id"] != installation_id
        or value["state"] not in {"prepared", "recovered", "upgraded"}
        or "receipt" not in value["data"]
    ):
        raise authority.AuthorityManagementError("upgrade_source_unavailable")
    operation = value["data"].get("operation")
    raw = value["data"]["result"]["ticket"]
    if operation == OPERATION:
        ticket = _RelationalUpgradeTicket.model_validate(raw).model_dump(mode="json")
        purpose, state, model = "database_upgrade", "upgraded", _RelationalUpgradeResult
        record = upgraded_lifecycle(ticket, secret)
    elif operation == "relational_recovery":
        ticket = _RelationalRecoveryTicket.model_validate(raw).model_dump(mode="json")
        purpose, state, model = "recovery", "recovered", _RelationalPreparationResult
        record = recovered_lifecycle(ticket, secret)
    else:
        ticket, purpose = _preparation_ticket(raw)
        expected = {
            "prepare_existing_schema": "relational_prepare",
            "prepare_migrated_schema": "relational_prepare_migrated",
        }.get(ticket["action"])
        if operation != expected or expected is None:
            raise authority.AuthorityManagementError("upgrade_source_unavailable")
        state, model = "prepared", _RelationalPreparationResult
        record = prepared_lifecycle(ticket, secret)
    verify_metadata(secret, purpose, ticket)
    if operation == OPERATION:
        from backend.services.application_relational_upgrade_confirmation import (
            require_confirmed_upgrade,
        )

        require_confirmed_upgrade(db, key, value, ticket, secret)
    receipt = model.model_validate(value["data"]["receipt"]).model_dump(mode="json")
    verify_metadata(
        secret,
        (
            purpose + "_result"
            if purpose in {"database_upgrade", "recovery"}
            else "preparation_result"
        ),
        receipt,
    )
    digest = hashlib.sha256(canonical(record)).hexdigest()
    if (
        value["installation_id"] != installation_id
        or value["state"] != state
        or ticket["preparation_id"] != identifier
        or receipt["preparation_id"] != identifier
        or receipt["lifecycle_sha256"] != digest
        or value["data"].get("recovery_id") is not None
    ):
        raise authority.AuthorityManagementError("upgrade_source_unavailable")
    return row, value, ticket, digest


def issue_prepared_database_upgrade(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    source_preparation_id,
    expected_source_revision,
    expected_grant_record_revision,
    confirm_owned_forward_upgrade,
    transport_secret,
):
    if confirm_owned_forward_upgrade is not True:
        raise authority.AuthorityManagementError("upgrade_confirmation_required")
    source_id = authority._identifier(source_preparation_id)
    expected_source = authority._identifier(expected_source_revision)
    expected_grant = authority._identifier(expected_grant_record_revision)
    prepared = manager._prepare(installation_id)
    require_platform_requirements(prepared[1].application_extension)
    with manager._write(
        installation_id,
        actor_token,
        request_id,
        OPERATION,
        {
            "source_preparation_id": source_id,
            "source_revision": expected_source,
            "grant_record_revision": expected_grant,
        },
    ) as (db, key, mutation, actor, result):
        if result:
            raise authority.AuthorityManagementError("upgrade_ticket_consumed")
        grant, definition = preparation._current(
            manager, db, key, installation_id, prepared
        )
        if (
            grant["revision"] != expected_grant
            or db.scalar(
                select(func.count())
                .select_from(Action)
                .where(Action.installation_id == installation_id)
            )
            >= preparation.MAX_PREPARATION_ACTIONS
        ):
            raise authority.AuthorityManagementError("upgrade_unavailable")
        row, source, old, digest = _source(
            db, key, installation_id, source_id, transport_secret
        )
        bindings = preparation._bindings(
            db, installation_id, prepared, grant, definition, mutation.guard.generation
        )
        if (
            source["revision"] != expected_source
            or any(
                old[name] != bindings[name]
                for name in ("instance_id", "owner_sha256", "recovery_generation")
            )
            or old["schema_revision"] == bindings["schema_revision"]
        ):
            raise authority.AuthorityManagementError("upgrade_source_changed")
        if source["data"].get("upgrade_id") is not None:
            from backend.services.application_relational_upgrade_rollback import (
                require_confirmed_rollback,
            )

            require_confirmed_rollback(db, key, source, old, transport_secret)
            result["previous_upgrade_id"] = source["data"]["upgrade_id"]
        # Preserve original outcomes/receipts. Old host SQL cannot acknowledge
        # old-lineage work after this explicit lifecycle fence, even on refusal.
        for old_row in db.scalars(
            select(Action)
            .where(Action.installation_id == installation_id)
            .limit(preparation.MAX_PREPARATION_ACTIONS)
        ):
            entry = authority._load(db, key, "action", old_row, old_row.request_id)
            if (
                entry["data"].get("operation") == "relational_transaction"
                and entry["data"]["permit"]["database_lineage"]
                == old["database_lineage"]
            ):
                entry["data"]["recovery_fenced_by"] = request_id
                entry["revision"] = authority.new_authority_generation()
                authority._save(db, key, "action", old_row, entry)
        invalidate_commands(db, installation_id)
        fenced = mutation.set_application_mode(
            read_application_authority(db, installation_id), "review_required"
        )
        bindings["authority_epoch"] = fenced.epoch
        boot, now = authority._clock()
        ticket = _RelationalUpgradeTicket.model_validate(
            sign_metadata(
                transport_secret,
                "database_upgrade",
                {
                    "version": 1,
                    "action": "upgrade_prepared_schema",
                    "preparation_id": request_id,
                    "source_preparation_id": source_id,
                    "source_preparation_revision": expected_source,
                    "source_ticket_sha256": hashlib.sha256(canonical(old)).hexdigest(),
                    "source_lifecycle_sha256": digest,
                    **{"source_" + name: old[name] for name in SOURCE_FIELDS},
                    "database_lineage": authority.new_authority_generation(),
                    "transport_key_sha256": hashlib.sha256(
                        transport_secret
                    ).hexdigest(),
                    "worker_profile_sha256": upgrade_worker_profile_digest(),
                    **bindings,
                    "boot_id": boot,
                    "issued_at_ms": now,
                    "deadline_ms": now + 300000,
                },
            )
        ).model_dump(mode="json")
        source["data"]["upgrade_id"] = request_id
        source["data"]["upgrade_source_revision"] = expected_source
        source["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, source)
        result["ticket"] = ticket
    return ticket


def upgrade_checkpoint(
    manager,
    installation_id,
    ticket,
    phase,
    *,
    actor_token,
    transport_secret,
    receipt=None,
):
    ticket = _RelationalUpgradeTicket.model_validate(ticket).model_dump(mode="json")
    verify_metadata(transport_secret, "database_upgrade", ticket)
    if ticket["worker_profile_sha256"] != upgrade_worker_profile_digest():
        raise authority.AuthorityManagementError("upgrade_worker_profile_changed")
    if (
        phase not in {"authorize", "begin", "check", "finish"}
        or phase != "finish"
        and receipt is not None
    ):
        raise authority.AuthorityManagementError("invalid_upgrade_phase")
    if ticket["transport_key_sha256"] != hashlib.sha256(transport_secret).hexdigest():
        raise authority.AuthorityManagementError("upgrade_key_changed")
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
            or value["data"].get("operation") != OPERATION
            or value["data"]["actor"] != actor
            or value["data"]["result"]["ticket"] != ticket
            or value["data"].get("upgrade_id") is not None
            or value["data"].get("upgrade_confirmation_id") is not None
            or value["data"].get("rollback_confirmation_id") is not None
        ):
            raise authority.AuthorityManagementError("upgrade_unavailable")
        grant, definition = _start_consent(
            manager, db, key, installation_id, prepared, ticket
        )
        current = read_application_authority(db, installation_id)
        installed = db.get(Installation, installation_id, populate_existing=True)
        boot, now = authority._clock()
        bindings = preparation._bindings(
            db, installation_id, prepared, grant, definition, mutation.guard.generation
        )
        _, source, old, digest = _source(
            db, key, installation_id, ticket["source_preparation_id"], transport_secret
        )
        if (
            current.mode != "review_required"
            or installed.enabled
            or installed.status != "disabled"
            or boot != ticket["boot_id"]
            or not ticket["issued_at_ms"] <= now < ticket["deadline_ms"]
            or any(ticket[name] != expected for name, expected in bindings.items())
            or source["data"].get("upgrade_id") != ticket["preparation_id"]
            or source["data"].get("upgrade_source_revision")
            != ticket["source_preparation_revision"]
            or hashlib.sha256(canonical(old)).hexdigest()
            != ticket["source_ticket_sha256"]
            or digest != ticket["source_lifecycle_sha256"]
            or any(old[name] != ticket["source_" + name] for name in SOURCE_FIELDS)
        ):
            raise authority.AuthorityManagementError("upgrade_changed")
        mutation.lock_application(current)
        if phase in {"authorize", "begin"}:
            if value["state"] != "recorded":
                raise authority.AuthorityManagementError("upgrade_ticket_consumed")
            if phase == "authorize":
                return {"state": "authorized_not_started"}
            value["state"] = "execution_unconfirmed"
        else:
            if value["state"] not in {"execution_unconfirmed", "upgraded"}:
                raise authority.AuthorityManagementError("upgrade_not_started")
            if phase == "check":
                if value["state"] != "execution_unconfirmed":
                    raise authority.AuthorityManagementError("upgrade_ticket_consumed")
                return {"state": "execution_unconfirmed"}
            receipt = _RelationalUpgradeResult.model_validate(receipt).model_dump(
                mode="json"
            )
            verify_metadata(transport_secret, "database_upgrade_result", receipt)
            if (
                receipt["preparation_id"] != ticket["preparation_id"]
                or receipt["lifecycle_sha256"]
                != hashlib.sha256(
                    canonical(upgraded_lifecycle(ticket, transport_secret))
                ).hexdigest()
            ):
                raise authority.AuthorityManagementError("upgrade_receipt_changed")
            if value["state"] == "upgraded":
                if value["data"]["receipt"] != receipt:
                    raise authority.AuthorityManagementError("upgrade_receipt_changed")
                return {"state": "upgraded_not_started", "historical": True}
            value["state"] = "upgraded"
            value["data"]["receipt"] = receipt
        value["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, value)
        db.add(
            AuditLog(
                user_id=actor[0],
                action="APPLICATION_RELATIONAL_UPGRADE_" + phase.upper(),
                entity_type="application_extension",
                entity_name=current.module_id,
                changes={
                    "upgrade_id": ticket["preparation_id"],
                    "source_preparation_id": ticket["source_preparation_id"],
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
