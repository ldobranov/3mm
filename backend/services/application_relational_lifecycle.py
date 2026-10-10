"""Private LOCAL-admin existing-schema preparation, not an install/SDK endpoint.

Uses the same exact reviews/grants and sealed Action journal. No business SQL,
runtime files or helper calls occur while Core leases are held. No staged new
artifact, automatic restore/rekey or enable. Business migrations require a
separate explicit LOCAL human action and signing purpose.
"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services.application_authority_context import _canonical_bytes
from backend.services.application_authority_sources import _configuration
from backend.services.application_files import _principal
from backend.services.application_policy_reviews import _actor
from backend.services.authority_metadata import (
    authority_transaction,
    read_application_authority,
)
from three_mm_application_sdk.relational_wire import (
    _preparation_ticket,
    _RelationalMigrationPreparationTicket,
    _RelationalPreparationResult,
    _RelationalPreparationTicket,
    canonical,
    migration_worker_profile_digest,
    prepared_lifecycle,
    profile_digest,
    sign_metadata,
    verify_metadata,
)
from three_mm_runtime.application_activation import application_instance_id

MAX_PREPARATION_ACTIONS = 4096


def _current(manager, db, key, installation_id, prepared):
    definition = prepared[1].application_extension
    if definition is None or definition.storage.relational is None:
        raise authority.AuthorityManagementError("relational_preparation_unavailable")
    grant = manager._require_grant(
        db, key, installation_id, prepared, "storage:relational_read"
    )
    if definition.storage.relational.mode == "read_write":
        manager._require_grant(
            db, key, installation_id, prepared, "storage:relational_write"
        )
    installation = db.get(Installation, installation_id, populate_existing=True)
    if (
        installation.enabled
        or installation.status != "disabled"
        or installation.instance_id != application_instance_id(definition.module_id)
    ):
        raise authority.AuthorityManagementError("disabled_preparation_required")
    return grant, definition


def _bindings(db, installation_id, prepared, grant, definition, generation):
    return {
        "instance_id": application_instance_id(definition.module_id),
        "owner_sha256": hashlib.sha256(
            _canonical_bytes(_principal(db, installation_id))
        ).hexdigest(),
        "package_sha256": prepared[0].sha256,
        "service_sha256": definition.service.artifact_sha256,
        "configuration_sha256": hashlib.sha256(
            canonical(_configuration(db, installation_id, prepared[1]))
        ).hexdigest(),
        "profile_sha256": profile_digest(
            definition.storage.relational, definition.storage.schema_revision
        ),
        "schema_revision": definition.storage.schema_revision,
        "grant_record_revision": grant["revision"],
        "binding_sha256": hashlib.sha256(
            _canonical_bytes(grant["data"]["subject"])
        ).hexdigest(),
        "authority_epoch": read_application_authority(db, installation_id).epoch,
        "recovery_generation": generation,
    }


def issue_existing_schema_preparation(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    expected_grant_record_revision,
    confirm_owned_metadata_preparation,
    transport_secret,
):
    """Explicit human action AFTER exact review/approve/apply, while disabled.

    Approving a resource grant alone does not call this or run package code.
    The transport key is a trusted Core dependency, not a request body field.
    No duplicate request reissues a possibly delivered preparation ticket.
    """
    if confirm_owned_metadata_preparation is not True:
        raise authority.AuthorityManagementError("preparation_confirmation_required")
    return _issue_preparation(
        manager,
        installation_id,
        actor_token=actor_token,
        request_id=request_id,
        expected_grant_record_revision=expected_grant_record_revision,
        transport_secret=transport_secret,
        migrate=False,
    )


def issue_migrated_schema_preparation(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    expected_grant_record_revision,
    confirm_owned_business_migrations,
    transport_secret,
):
    """Separate explicit consent to bounded non-root migration code execution.

    Metadata-only approval/ticket cannot authorize this action. No public route,
    module name, path, automatic startup migration or service-side toggle.
    """
    if confirm_owned_business_migrations is not True:
        raise authority.AuthorityManagementError("migration_confirmation_required")
    return _issue_preparation(
        manager,
        installation_id,
        actor_token=actor_token,
        request_id=request_id,
        expected_grant_record_revision=expected_grant_record_revision,
        transport_secret=transport_secret,
        migrate=True,
    )


def _issue_preparation(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    expected_grant_record_revision,
    transport_secret,
    migrate,
):
    action = "prepare_migrated_schema" if migrate else "prepare_existing_schema"
    operation = "relational_prepare_migrated" if migrate else "relational_prepare"
    model = (
        _RelationalMigrationPreparationTicket
        if migrate
        else _RelationalPreparationTicket
    )
    purpose = "migration_preparation" if migrate else "preparation"
    expected = authority._identifier(expected_grant_record_revision)
    prepared = manager._prepare(installation_id)
    with manager._write(
        installation_id,
        actor_token,
        request_id,
        operation,
        {"grant_record_revision": expected, "action": action},
    ) as (db, key, mutation, actor, result):
        if result:
            raise authority.AuthorityManagementError("preparation_ticket_consumed")
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
            raise authority.AuthorityManagementError("preparation_unavailable")
        boot, now = authority._clock()
        result["ticket"] = model.model_validate(
            sign_metadata(
                transport_secret,
                purpose,
                {
                    "version": 1,
                    "action": action,
                    "preparation_id": request_id,
                    "database_lineage": authority.new_authority_generation(),
                    **(
                        {"worker_profile_sha256": migration_worker_profile_digest()}
                        if migrate
                        else {}
                    ),
                    **_bindings(
                        db,
                        installation_id,
                        prepared,
                        grant,
                        definition,
                        mutation.guard.generation,
                    ),
                    "boot_id": boot,
                    "issued_at_ms": now,
                    "deadline_ms": now + 300000,
                },
            )
        ).model_dump(mode="json")
    return result["ticket"]


def preparation_checkpoint(
    manager,
    installation_id,
    ticket,
    phase,
    *,
    actor_token,
    transport_secret,
    receipt=None,
):
    """Trusted root-helper callback; leases close before any application I/O.

    Begin is durably one-use. Checks still require current human/session/grant.
    Completion is metadata, not independent hostile-code attestation or runtime
    authority. Lost ACK/deadline keeps uncertainty and never restarts/replays.
    """
    ticket, purpose = _preparation_ticket(ticket)
    verify_metadata(transport_secret, purpose, ticket)
    operation = (
        "relational_prepare_migrated"
        if ticket["action"] == "prepare_migrated_schema"
        else "relational_prepare"
    )
    if (
        ticket["action"] == "prepare_migrated_schema"
        and ticket["worker_profile_sha256"] != migration_worker_profile_digest()
    ):
        raise authority.AuthorityManagementError("migration_worker_profile_changed")
    if phase not in {"authorize", "begin", "check", "finish"} or (
        phase != "finish" and receipt is not None
    ):
        raise authority.AuthorityManagementError("invalid_preparation_phase")
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
            or value["data"].get("operation") != operation
            or value["data"]["actor"] != actor
            or value["data"]["result"]["ticket"] != ticket
        ):
            raise authority.AuthorityManagementError("preparation_unavailable")
        grant, definition = _current(manager, db, key, installation_id, prepared)
        boot, now = authority._clock()
        if (
            boot != ticket["boot_id"]
            or not ticket["issued_at_ms"] <= now < ticket["deadline_ms"]
            or any(
                ticket[name] != expected
                for name, expected in _bindings(
                    db,
                    installation_id,
                    prepared,
                    grant,
                    definition,
                    mutation.guard.generation,
                ).items()
            )
        ):
            raise authority.AuthorityManagementError("preparation_changed")
        current = read_application_authority(db, installation_id)
        mutation.lock_application(current)
        if phase in {"authorize", "begin"}:
            if value["state"] != "recorded":
                raise authority.AuthorityManagementError("preparation_ticket_consumed")
            if phase == "authorize":
                return {"state": "authorized_not_started"}
            value["state"] = "execution_unconfirmed"
        else:
            if value["state"] not in {"execution_unconfirmed", "prepared"}:
                raise authority.AuthorityManagementError("preparation_not_started")
            if phase == "check":
                if value["state"] != "execution_unconfirmed":
                    raise authority.AuthorityManagementError(
                        "preparation_ticket_consumed"
                    )
                return {"state": "execution_unconfirmed"}
            receipt = _RelationalPreparationResult.model_validate(receipt).model_dump(
                mode="json"
            )
            verify_metadata(transport_secret, "preparation_result", receipt)
            if (
                receipt["preparation_id"] != ticket["preparation_id"]
                or receipt["lifecycle_sha256"]
                != hashlib.sha256(
                    canonical(prepared_lifecycle(ticket, transport_secret))
                ).hexdigest()
            ):
                raise authority.AuthorityManagementError("preparation_receipt_changed")
            if value["state"] == "prepared":
                if value["data"]["receipt"] != receipt:
                    raise authority.AuthorityManagementError(
                        "preparation_receipt_changed"
                    )
                return {"state": "prepared_not_started", "historical": True}
            value["state"] = "prepared"
            value["data"]["receipt"] = receipt
        value["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, value)
        db.add(
            AuditLog(
                user_id=actor[0],
                action="APPLICATION_RELATIONAL_PREPARATION_" + phase.upper(),
                entity_type="application_extension",
                entity_name=current.module_id,
                changes={
                    "preparation_id": ticket["preparation_id"],
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
