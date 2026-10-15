"""Private LOCAL prepared-service activation, separate from preparation/grants.

No helper/runtime I/O under Core leases. Begin invalidates the old authority
epoch BEFORE startup. Its grant is thereafter historical start consent, never
runtime authority. Successful activation still requires fresh permission review.
The prepared Action is reserved once; unknown outcomes cannot issue a new start.
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services import application_relational_lifecycle as preparation
from backend.services.application_authority_context import AuthorityPolicyV5, _parse
from backend.services.application_authority_policy import PolicySubjectV5
from backend.services.application_commands import invalidate_commands
from backend.services.application_policy_reviews import _actor
from backend.services.authority_metadata import (
    authority_transaction,
    read_application_authority,
)
from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeResult,
    _RelationalUpgradeTicket,
    upgraded_lifecycle,
)
from three_mm_application_sdk.relational_wire import (
    _activation_ticket,
    _preparation_ticket,
    _RelationalActivationResult,
    _RelationalActivationTicket,
    _RelationalPreparationResult,
    canonical,
    prepared_lifecycle,
    sign_metadata,
    verify_metadata,
)

OPERATION = "relational_activate_prepared"
STABLE_FIELDS = (
    "instance_id",
    "owner_sha256",
    "package_sha256",
    "service_sha256",
    "configuration_sha256",
    "profile_sha256",
    "schema_revision",
    "recovery_generation",
)


def _source(db, key, installation_id, identifier, secret, bindings):
    row = db.get(Action, identifier, populate_existing=True)
    value = authority._load(db, key, "action", row, identifier)
    upgrade = value["data"].get("operation") == "relational_upgrade_prepared"
    if upgrade:
        ticket = _RelationalUpgradeTicket.model_validate(
            value["data"]["result"]["ticket"]
        ).model_dump(mode="json")
        purpose, receipt_purpose, expected_state = (
            "database_upgrade",
            "database_upgrade_result",
            "upgraded",
        )
        receipt_model = _RelationalUpgradeResult
        lifecycle = upgraded_lifecycle(ticket, secret)
        expected_operation = "relational_upgrade_prepared"
        from backend.services.application_relational_upgrade_confirmation import (
            require_confirmed_upgrade,
        )

        require_confirmed_upgrade(db, key, value, ticket, secret)
    else:
        ticket, purpose = _preparation_ticket(value["data"]["result"]["ticket"])
        receipt_purpose, expected_state, receipt_model = (
            "preparation_result",
            "prepared",
            _RelationalPreparationResult,
        )
        lifecycle = prepared_lifecycle(ticket, secret)
        expected_operation = {
            "prepare_existing_schema": "relational_prepare",
            "prepare_migrated_schema": "relational_prepare_migrated",
        }.get(ticket["action"])
    receipt = receipt_model.model_validate(value["data"]["receipt"]).model_dump(
        mode="json"
    )
    verify_metadata(secret, purpose, ticket)
    verify_metadata(secret, receipt_purpose, receipt)
    lifecycle_digest = hashlib.sha256(canonical(lifecycle)).hexdigest()
    if (
        value["installation_id"] != installation_id
        or value["state"] != expected_state
        or value["data"].get("upgrade_id") is not None
        or expected_operation is None
        or value["data"]["operation"] != expected_operation
        or ticket["preparation_id"] != identifier
        or receipt["preparation_id"] != identifier
        or receipt["lifecycle_sha256"] != lifecycle_digest
        or any(ticket[name] != bindings[name] for name in STABLE_FIELDS)
    ):
        raise authority.AuthorityManagementError("prepared_source_unavailable")
    return row, value, ticket, lifecycle_digest


def issue_prepared_activation(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    source_preparation_id,
    expected_grant_record_revision,
    confirm_start_prepared_service,
    transport_secret,
    service_uid,
    service_gid,
    coordinator_uid,
):
    """Trusted local coordinator supplies credentials; no public writer exists."""
    if confirm_start_prepared_service is not True:
        raise authority.AuthorityManagementError("activation_confirmation_required")
    source_id = authority._identifier(source_preparation_id)
    expected = authority._identifier(expected_grant_record_revision)
    if type(transport_secret) is not bytes or len(transport_secret) != 32:
        raise ValueError("Invalid activation signing dependency")
    prepared = manager._prepare(installation_id)
    with manager._write(
        installation_id,
        actor_token,
        request_id,
        OPERATION,
        {
            "source_preparation_id": source_id,
            "grant_record_revision": expected,
            "service_uid": service_uid,
            "service_gid": service_gid,
            "coordinator_uid": coordinator_uid,
            "transport_key_sha256": hashlib.sha256(transport_secret).hexdigest(),
        },
    ) as (db, key, mutation, _actor_value, result):
        if result:
            raise authority.AuthorityManagementError("activation_ticket_consumed")
        grant, definition = preparation._current(
            manager, db, key, installation_id, prepared
        )
        if (
            grant["revision"] != expected
            or db.scalar(
                select(func.count())
                .select_from(Action)
                .where(Action.installation_id == installation_id)
            )
            >= preparation.MAX_PREPARATION_ACTIONS
        ):
            raise authority.AuthorityManagementError("activation_unavailable")
        bindings = preparation._bindings(
            db, installation_id, prepared, grant, definition, mutation.guard.generation
        )
        row, source, source_ticket, digest = _source(
            db, key, installation_id, source_id, transport_secret, bindings
        )
        if source["data"].get("activation_id") is not None:
            raise authority.AuthorityManagementError("prepared_source_consumed")
        boot, now = authority._clock()
        ticket = _RelationalActivationTicket.model_validate(
            sign_metadata(
                transport_secret,
                "activation",
                {
                    "version": 1,
                    "action": "activate_prepared_service",
                    "preparation_id": request_id,
                    "source_preparation_id": source_id,
                    "prepared_lifecycle_sha256": digest,
                    "database_lineage": source_ticket["database_lineage"],
                    "service_uid": service_uid,
                    "service_gid": service_gid,
                    "coordinator_uid": coordinator_uid,
                    "transport_key_sha256": hashlib.sha256(
                        transport_secret
                    ).hexdigest(),
                    **bindings,
                    "boot_id": boot,
                    "issued_at_ms": now,
                    "deadline_ms": now + 300000,
                },
            )
        ).model_dump(mode="json")
        source["data"]["activation_id"] = request_id
        source["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, source)
        result["ticket"] = ticket
    return ticket


def _start_consent(manager, db, key, installation_id, prepared, ticket):
    """Historical grant only: do not use this for any runtime effect admission."""
    subject = manager._subject(db, key, installation_id, prepared)
    row = db.get(Grant, installation_id, populate_existing=True)
    grant = authority._load(db, key, "grant", row, installation_id)
    data = grant["data"]
    approved = _parse(PolicySubjectV5, data["subject"])
    native, _ = manager._policy(db, key, subject, data["native_review_id"])
    _, policy = manager._policy(db, key, approved, data["native_review_id"])
    if (
        grant["state"] != "active"
        or grant["revision"] != ticket["grant_record_revision"]
        or row.revision != data["grant_revision"]
        or native["revision"] != data["native_revision"]
        or policy != _parse(AuthorityPolicyV5, data["policy"])
        or authority._resource_identity(subject)
        != authority._resource_identity(approved)
    ):
        raise authority.AuthorityManagementError("activation_consent_changed")
    return grant, prepared[1].application_extension


def activation_checkpoint(
    manager,
    installation_id,
    ticket,
    phase,
    *,
    actor_token,
    transport_secret,
    runtime_root,
    receipt=None,
):
    """Fixed root-helper callback. Leases close before start/health/stop I/O.

    Abort is fail-closed metadata, not rollback/replay. An unavailable abort ACK
    leaves evidence for fresh local recovery; never silently clears the fence.
    """
    ticket, purpose = _activation_ticket(ticket)
    operation = (
        OPERATION if purpose == "activation" else "relational_reactivate_prepared"
    )
    verify_metadata(transport_secret, purpose, ticket)
    if (
        ticket["transport_key_sha256"] != hashlib.sha256(transport_secret).hexdigest()
        or phase not in {"authorize", "begin", "check", "finish", "abort"}
        or (phase != "finish" and receipt is not None)
        or not Path(runtime_root).is_absolute()
    ):
        raise authority.AuthorityManagementError("invalid_activation_phase")
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
            or value["data"]["operation"] != operation
            or value["data"]["actor"] != actor
            or value["data"]["result"]["ticket"] != ticket
            or value["data"].get("activation_recovery_id") is not None
        ):
            raise authority.AuthorityManagementError("activation_unavailable")
        current = read_application_authority(db, installation_id)
        if phase in {"authorize", "begin"}:
            grant, definition = preparation._current(
                manager, db, key, installation_id, prepared
            )
        else:
            grant, definition = _start_consent(
                manager, db, key, installation_id, prepared, ticket
            )
        bindings = preparation._bindings(
            db, installation_id, prepared, grant, definition, mutation.guard.generation
        )
        expected_epoch = (
            ticket["authority_epoch"]
            if phase in {"authorize", "begin"}
            else value["data"].get("activation_epoch")
        )
        boot, now = authority._clock()
        installation = db.get(Installation, installation_id, populate_existing=True)
        if (
            boot != ticket["boot_id"]
            or not ticket["issued_at_ms"] <= now < ticket["deadline_ms"]
            or current.epoch != expected_epoch
            or (
                phase not in {"authorize", "begin"}
                and current.mode != "review_required"
            )
            or any(
                ticket[name] != expected_value
                for name, expected_value in bindings.items()
                if name != "authority_epoch"
            )
            or (
                value["state"] != "activated"
                and (installation.status != "disabled" or installation.enabled)
            )
        ):
            raise authority.AuthorityManagementError("activation_changed")
        if purpose == "reactivation":
            from backend.services.application_relational_activation_recovery import (
                _stable,
            )
            from backend.services.application_relational_reactivation import (
                verify_reactivation_source,
            )

            _stable(db, key, installation_id, prepared, mutation.guard.generation)
            digest = verify_reactivation_source(
                db, key, installation_id, ticket, transport_secret, bindings
            )
        else:
            _, source, source_ticket, digest = _source(
                db,
                key,
                installation_id,
                ticket["source_preparation_id"],
                transport_secret,
                bindings,
            )
            if (
                source["data"].get("activation_id") != ticket["preparation_id"]
                or digest != ticket["prepared_lifecycle_sha256"]
                or source_ticket["database_lineage"] != ticket["database_lineage"]
            ):
                raise authority.AuthorityManagementError("activation_source_changed")
        mutation.lock_application(current)
        if phase in {"authorize", "begin"}:
            if value["state"] != "recorded":
                raise authority.AuthorityManagementError("activation_ticket_consumed")
            if phase == "authorize":
                return {"state": "authorized_not_started"}
            invalidate_commands(db, installation_id)
            resulting = mutation.set_application_mode(current, "review_required")
            value["data"]["activation_epoch"] = resulting.epoch
            value["state"] = "execution_unconfirmed"
        elif phase == "abort":
            if value["state"] not in {"execution_unconfirmed", "activated"}:
                raise authority.AuthorityManagementError("activation_not_started")
            invalidate_commands(db, installation_id)
            mutation.set_application_mode(current, "review_required")
            installation.enabled, installation.status = False, "disabled"
            value["state"] = "activation_unconfirmed"
        else:
            if value["state"] not in {"execution_unconfirmed", "activated"}:
                raise authority.AuthorityManagementError("activation_not_started")
            if phase == "check":
                if value["state"] != "execution_unconfirmed":
                    raise authority.AuthorityManagementError(
                        "activation_ticket_consumed"
                    )
                return {"state": "execution_unconfirmed"}
            receipt = _RelationalActivationResult.model_validate(receipt).model_dump(
                mode="json"
            )
            verify_metadata(transport_secret, purpose + "_result", receipt)
            if (
                receipt["preparation_id"] != ticket["preparation_id"]
                or receipt["lifecycle_sha256"] != digest
            ):
                raise authority.AuthorityManagementError("activation_receipt_changed")
            if value["state"] == "activated":
                if value["data"]["receipt"] != receipt:
                    raise authority.AuthorityManagementError(
                        "activation_receipt_changed"
                    )
                return {"state": "active_review_required", "historical": True}
            value["state"] = "activated"
            value["data"]["receipt"] = receipt
            installation.enabled, installation.status = True, "active"
            installation.active_version = prepared[0].version
            installation.socket_path = str(
                Path(runtime_root) / ticket["instance_id"] / "run" / "service.sock"
            )
            installation.activated_at = installation.health_checked_at = datetime.now(
                timezone.utc
            ).replace(tzinfo=None)
        value["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, value)
        db.add(
            AuditLog(
                user_id=actor[0],
                action="APPLICATION_RELATIONAL_"
                + purpose.upper()
                + "_"
                + phase.upper(),
                entity_type="application_extension",
                entity_name=current.module_id,
                changes={
                    "activation_id": ticket["preparation_id"],
                    "state": value["state"],
                },
            )
        )
        mutation.advance_guard_revision()
    return {
        "state": {
            "begin": "execution_unconfirmed",
            "finish": "active_review_required",
            "abort": "activation_unconfirmed",
        }[phase]
    }
