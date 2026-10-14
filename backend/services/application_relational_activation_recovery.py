"""Private fresh-human stop/reconciliation of interrupted prepared activation.

No runtime grant is required or manufactured: revoked native trust/permissions
must not prevent an authenticated administrator from stopping this exact
instance. Original signed source/preparation history is retained, never renewed.
No filesystem, business SQL or helper I/O under Core metadata leases.
"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services import application_relational_activation as activation
from backend.services.application_authority_context import _canonical_bytes
from backend.services.application_authority_sources import _configuration, _package_pin
from backend.services.application_commands import invalidate_commands
from backend.services.application_files import _principal
from backend.services.application_policy_reviews import _actor
from backend.services.application_relational_lifecycle import MAX_PREPARATION_ACTIONS
from backend.services.authority_metadata import (
    authority_transaction,
    read_application_authority,
)
from three_mm_application_sdk.relational_wire import (
    _activation_recovery_ticket,
    _activation_ticket,
    _RelationalActivationRecoveryResult,
    _RelationalActivationRecoveryTicket,
    _RelationalActivationResult,
    _RelationalActivationTicket,
    _RelationalReactivationRecoveryTicket,
    canonical,
    profile_digest,
    sign_metadata,
    verify_metadata,
)
from three_mm_runtime.application_activation import application_instance_id

OPERATION = "relational_reconcile_prepared_start"


def _stable(db, key, installation_id, prepared, generation):
    # Exact identity only, deliberately not _current/_require_grant/_policy.
    # Recovery has no application import, start or business effect to approve.
    pin = _package_pin(db, installation_id)
    if pin != prepared[0]:
        raise authority.AuthorityManagementError("activation_recovery_artifact_changed")
    if pin.active_version is None:
        from backend.services.application_relational_registration import (
            verify_registration,
        )

        verify_registration(db, key, installation_id, pin, prepared[1])
    definition = prepared[1].application_extension
    installation = db.get(Installation, installation_id, populate_existing=True)
    if (
        definition is None
        or definition.storage.relational is None
        or installation.instance_id != application_instance_id(definition.module_id)
    ):
        raise authority.AuthorityManagementError("activation_recovery_unavailable")
    return {
        "instance_id": installation.instance_id,
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
        "recovery_generation": generation,
    }


def _sealed_source(db, key, installation_id, identifier, stable):
    """Core-authenticated historical metadata, NOT a stop/start/SQL permit."""
    row = db.get(Action, identifier, populate_existing=True)
    value = authority._load(db, key, "action", row, identifier)
    ticket, purpose = _activation_ticket(value["data"]["result"]["ticket"])
    if (
        value["installation_id"] != installation_id
        or value["data"]["operation"]
        != (
            activation.OPERATION
            if purpose == "activation"
            else "relational_reactivate_prepared"
        )
        or value["state"]
        not in {
            "recorded",
            "execution_unconfirmed",
            "activation_unconfirmed",
            "activated",
        }
        or ticket["preparation_id"] != identifier
        or any(ticket[name] != expected for name, expected in stable.items())
    ):
        raise authority.AuthorityManagementError("activation_recovery_source_changed")
    return row, value, ticket


def inspect_activation_recovery_source(
    manager,
    installation_id,
    *,
    actor_token,
    source_activation_id,
    expected_activation_revision=None,
    include_configuration=False,
):
    """Read-only LOCAL-human status; never infers actual process/Root outcome.

    The helper's private snapshot may include resolved configuration. Human CLI
    output does not. No transport secret/file, effective grant or native review
    is required; exact signed source and current package/owner are still pinned.
    """
    identifier = authority._identifier(source_activation_id)
    if expected_activation_revision is not None:
        authority._identifier(expected_activation_revision)
    prepared = manager._prepare(installation_id)
    with (
        manager.keys.locked() as key,
        Session(manager.engine) as db,
        authority_transaction(db) as mutation,
    ):
        _actor(db, actor_token)
        stable = _stable(db, key, installation_id, prepared, mutation.guard.generation)
        _, value, ticket = _sealed_source(db, key, installation_id, identifier, stable)
        if (
            expected_activation_revision is not None
            and value["revision"] != expected_activation_revision
        ):
            raise authority.AuthorityManagementError(
                "activation_recovery_revision_changed"
            )
        result = {
            "installation_id": installation_id,
            "source_activation_id": identifier,
            "source_revision": value["revision"],
            "source_state": value["state"],
            "latest_recovery_id": value["data"].get("activation_recovery_id"),
            "metadata_only": True,
            "permission_approval": "not_evaluated",
        }
        if result["latest_recovery_id"] is not None:
            authority._identifier(result["latest_recovery_id"])
        if include_configuration:
            # Only the fixed worker chooses this private snapshot dialect.
            return {
                "sha256": ticket["package_sha256"],
                "instance_id": ticket["instance_id"],
                "configuration": _configuration(db, installation_id, prepared[1]),
                "source_revision": value["revision"],
            }
        return result


def _source(db, key, installation_id, identifier, secret, stable):
    row, value, ticket = _sealed_source(db, key, installation_id, identifier, stable)
    _, purpose = _activation_ticket(ticket)
    verify_metadata(secret, purpose, ticket)  # Historical, not live authority.
    if ticket["transport_key_sha256"] != hashlib.sha256(secret).hexdigest():
        raise authority.AuthorityManagementError("activation_recovery_source_changed")
    if value["state"] == "activated" or "receipt" in value["data"]:
        receipt = _RelationalActivationResult.model_validate(
            value["data"]["receipt"]
        ).model_dump(mode="json")
        verify_metadata(secret, purpose + "_result", receipt)
        if (
            receipt["preparation_id"] != identifier
            or receipt["lifecycle_sha256"] != ticket["prepared_lifecycle_sha256"]
        ):
            raise authority.AuthorityManagementError(
                "activation_recovery_receipt_changed"
            )
    _, preparation, original, digest = activation._source(
        db, key, installation_id, ticket["source_preparation_id"], secret, stable
    )
    if (
        preparation["data"].get("activation_id")
        != (ticket["origin_activation_id"] if purpose == "reactivation" else identifier)
        or digest != ticket["prepared_lifecycle_sha256"]
        or original["database_lineage"] != ticket["database_lineage"]
    ):
        raise authority.AuthorityManagementError("activation_recovery_source_changed")
    return row, value, ticket


def issue_activation_recovery(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    source_activation_id,
    expected_activation_revision,
    confirm_stop_preserve_prepared_state,
    transport_secret,
    service_uid,
    service_gid,
    coordinator_uid,
):
    """Reserve a new stop only; atomically fence ALL old start/SQL authority.

    A fresh request can supersede an unknown recovery, but never reissues its
    ticket or invents an original start outcome. Existing grants remain history.
    """
    if confirm_stop_preserve_prepared_state is not True:
        raise authority.AuthorityManagementError(
            "activation_recovery_confirmation_required"
        )
    source_id = authority._identifier(source_activation_id)
    expected = authority._identifier(expected_activation_revision)
    if type(transport_secret) is not bytes or len(transport_secret) != 32:
        raise ValueError("Invalid activation recovery key dependency")
    prepared = manager._prepare(installation_id)
    with manager._write(
        installation_id,
        actor_token,
        request_id,
        OPERATION,
        {
            "source_activation_id": source_id,
            "source_revision": expected,
            "service_uid": service_uid,
            "service_gid": service_gid,
            "coordinator_uid": coordinator_uid,
            "transport_key_sha256": hashlib.sha256(transport_secret).hexdigest(),
        },
    ) as (db, key, mutation, _actor_value, result):
        if result:
            raise authority.AuthorityManagementError(
                "activation_recovery_ticket_consumed"
            )
        stable = _stable(db, key, installation_id, prepared, mutation.guard.generation)
        row, source, original = _source(
            db, key, installation_id, source_id, transport_secret, stable
        )
        if (
            source["revision"] != expected
            or source["data"].get("reactivation_id") is not None
            or any(
                original[name] != value
                for name, value in {
                    "service_uid": service_uid,
                    "service_gid": service_gid,
                    "coordinator_uid": coordinator_uid,
                }.items()
            )
            or db.scalar(
                select(func.count())
                .select_from(Action)
                .where(Action.installation_id == installation_id)
            )
            >= MAX_PREPARATION_ACTIONS
        ):
            raise authority.AuthorityManagementError("activation_recovery_changed")
        current = read_application_authority(db, installation_id)
        invalidate_commands(db, installation_id)
        fenced = mutation.set_application_mode(current, "review_required")
        installation = db.get(Installation, installation_id, populate_existing=True)
        installation.enabled, installation.status = False, "disabled"
        source["data"]["activation_recovery_id"] = request_id
        source["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, source)
        boot, now = authority._clock()
        reactivated = original["action"] == "reactivate_prepared_service"
        recovery_model = (
            _RelationalReactivationRecoveryTicket
            if reactivated
            else _RelationalActivationRecoveryTicket
        )
        result["ticket"] = recovery_model.model_validate(
            sign_metadata(
                transport_secret,
                "reactivation_recovery" if reactivated else "activation_recovery",
                {
                    **{
                        name: original[name]
                        for name in _RelationalActivationTicket.model_fields
                    },
                    "action": (
                        "reconcile_reactivated_start"
                        if reactivated
                        else "reconcile_prepared_start"
                    ),
                    "preparation_id": request_id,
                    "source_activation_id": source_id,
                    "source_activation_revision": source["revision"],
                    "source_ticket_sha256": hashlib.sha256(
                        canonical(original)
                    ).hexdigest(),
                    "source_state": source["state"],
                    "authority_epoch": fenced.epoch,
                    "boot_id": boot,
                    "issued_at_ms": now,
                    "deadline_ms": now + 300000,
                },
            )
        ).model_dump(mode="json")
    return result["ticket"]


def activation_recovery_checkpoint(
    manager,
    installation_id,
    ticket,
    phase,
    *,
    actor_token,
    transport_secret,
    receipt=None,
):
    ticket, purpose = _activation_recovery_ticket(ticket)
    verify_metadata(transport_secret, purpose, ticket)
    if phase not in {"authorize", "begin", "check", "finish"} or (
        phase != "finish" and receipt is not None
    ):
        raise authority.AuthorityManagementError("invalid_activation_recovery_phase")
    prepared = manager._prepare(installation_id)
    with (
        manager.keys.locked() as key,
        Session(manager.engine) as db,
        authority_transaction(db) as mutation,
    ):
        actor = list(_actor(db, actor_token))
        row = db.get(Action, ticket["preparation_id"], populate_existing=True)
        value = authority._load(db, key, "action", row, ticket["preparation_id"])
        stable = _stable(db, key, installation_id, prepared, mutation.guard.generation)
        _, source, original = _source(
            db,
            key,
            installation_id,
            ticket["source_activation_id"],
            transport_secret,
            stable,
        )
        current = read_application_authority(db, installation_id)
        installation = db.get(Installation, installation_id, populate_existing=True)
        boot, now = authority._clock()
        if (
            value["installation_id"] != installation_id
            or value["data"]["operation"] != OPERATION
            or value["data"]["actor"] != actor
            or value["data"]["result"]["ticket"] != ticket
            or source["data"].get("activation_recovery_id") != ticket["preparation_id"]
            or source["data"].get("reactivation_id") is not None
            or value["data"].get("reactivation_id") is not None
            or source["revision"] != ticket["source_activation_revision"]
            or source["state"] != ticket["source_state"]
            or (purpose == "reactivation_recovery")
            != (original["action"] == "reactivate_prepared_service")
            or hashlib.sha256(canonical(original)).hexdigest()
            != ticket["source_ticket_sha256"]
            or any(
                ticket[name] != original[name]
                for name in (
                    *activation.STABLE_FIELDS,
                    "database_lineage",
                    "source_preparation_id",
                    "prepared_lifecycle_sha256",
                    "service_uid",
                    "service_gid",
                    "coordinator_uid",
                    "transport_key_sha256",
                    "grant_record_revision",
                    "binding_sha256",
                )
            )
            or current.epoch != ticket["authority_epoch"]
            or current.mode != "review_required"
            or installation.enabled
            or installation.status != "disabled"
            or boot != ticket["boot_id"]
            or not ticket["issued_at_ms"] <= now < ticket["deadline_ms"]
        ):
            raise authority.AuthorityManagementError(
                "activation_recovery_superseded_or_changed"
            )
        mutation.lock_application(current)
        if phase in {"authorize", "begin"}:
            if value["state"] != "recorded":
                raise authority.AuthorityManagementError(
                    "activation_recovery_ticket_consumed"
                )
            if phase == "authorize":
                return {"state": "authorized_stop_only"}
            value["state"] = "execution_unconfirmed"
        else:
            if value["state"] not in {"execution_unconfirmed", "confirmed"}:
                raise authority.AuthorityManagementError(
                    "activation_recovery_not_started"
                )
            if phase == "check":
                if value["state"] != "execution_unconfirmed":
                    raise authority.AuthorityManagementError(
                        "activation_recovery_ticket_consumed"
                    )
                return {"state": "execution_unconfirmed"}
            receipt = _RelationalActivationRecoveryResult.model_validate(
                receipt
            ).model_dump(mode="json")
            verify_metadata(transport_secret, "activation_recovery_result", receipt)
            if (
                receipt["preparation_id"] != ticket["preparation_id"]
                or receipt["source_activation_id"] != ticket["source_activation_id"]
                or receipt["ticket_sha256"]
                != hashlib.sha256(canonical(ticket)).hexdigest()
                or receipt["lifecycle_sha256"] != ticket["prepared_lifecycle_sha256"]
            ):
                raise authority.AuthorityManagementError(
                    "activation_recovery_receipt_changed"
                )
            if value["state"] == "confirmed":
                if value["data"]["receipt"] != receipt:
                    raise authority.AuthorityManagementError(
                        "activation_recovery_receipt_changed"
                    )
                return {"state": "stopped_review_required", "historical": True}
            value["state"] = "confirmed"
            value["data"]["receipt"] = receipt
        value["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, value)
        db.add(
            AuditLog(
                user_id=actor[0],
                action="APPLICATION_START_RECOVERY_" + phase.upper(),
                entity_type="application_extension",
                entity_name=current.module_id,
                changes={
                    "source_activation_id": ticket["source_activation_id"],
                    "recovery_id": ticket["preparation_id"],
                    "state": value["state"],
                },
            )
        )
        mutation.advance_guard_revision()
    return {
        "state": (
            "stopped_review_required" if phase == "finish" else "execution_unconfirmed"
        )
    }
