"""Private fresh LOCAL start consent after confirmed interrupted-start recovery.

Consumes the exact latest stop once; never resets the database preparation or
original start reservation. Unknown delivery requires another explicit stop of
the NEW start action. No runtime/filesystem/business SQL I/O under Core leases.
"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.services import application_authority_management as authority
from backend.services import application_relational_activation as activation
from backend.services import application_relational_activation_recovery as recovery
from backend.services import application_relational_lifecycle as preparation
from backend.services.application_authority_sources import _configuration
from backend.services.application_policy_reviews import _actor
from backend.services.authority_metadata import authority_transaction
from three_mm_application_sdk.relational_wire import (
    _activation_recovery_ticket,
    _RelationalActivationRecoveryResult,
    _RelationalReactivationTicket,
    canonical,
    sign_metadata,
    verify_metadata,
)

OPERATION = "relational_reactivate_prepared"


def inspect_reactivation_source(
    manager,
    installation_id,
    *,
    actor_token,
    source_recovery_id,
    expected_recovery_revision=None,
    expected_grant_record_revision=None,
    include_configuration=False,
):
    """Core-sealed historical status, NOT actual Root/process outcome evidence.

    Human status needs no instance key/grant and performs no mutation. Only the
    fixed helper worker chooses the private disabled/current-grant snapshot;
    full historical transport signatures are checked separately at issuance.
    """
    identifier = authority._identifier(source_recovery_id)
    if expected_recovery_revision is not None:
        authority._identifier(expected_recovery_revision)
    if expected_grant_record_revision is not None:
        authority._identifier(expected_grant_record_revision)
    prepared = manager._prepare(installation_id)
    with (
        manager.keys.locked() as key,
        Session(manager.engine) as db,
        authority_transaction(db) as mutation,
    ):
        _actor(db, actor_token)
        stable = recovery._stable(
            db, key, installation_id, prepared, mutation.guard.generation
        )
        row = db.get(Action, identifier, populate_existing=True)
        value = authority._load(db, key, "action", row, identifier)
        if (
            value["installation_id"] != installation_id
            or value["data"]["operation"] != recovery.OPERATION
            or value["state"] not in {"recorded", "execution_unconfirmed", "confirmed"}
        ):
            raise authority.AuthorityManagementError("reactivation_source_changed")
        ticket, purpose = _activation_recovery_ticket(value["data"]["result"]["ticket"])
        _, source, original = recovery._sealed_source(
            db, key, installation_id, ticket["source_activation_id"], stable
        )
        reserved = value["data"].get("reactivation_id")
        if reserved is not None:
            authority._identifier(reserved)
        if (
            value["installation_id"] != installation_id
            or value["data"]["operation"] != recovery.OPERATION
            or value["state"] not in {"recorded", "execution_unconfirmed", "confirmed"}
            or ticket["preparation_id"] != identifier
            or source["data"].get("activation_recovery_id") != identifier
            or source["data"].get("reactivation_id") != reserved
            or source["state"] != ticket["source_state"]
            or (
                reserved is None
                and source["revision"] != ticket["source_activation_revision"]
            )
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
            or (
                expected_recovery_revision is not None
                and value["revision"] != expected_recovery_revision
            )
        ):
            raise authority.AuthorityManagementError("reactivation_source_changed")
        if value["state"] == "confirmed":
            receipt = _RelationalActivationRecoveryResult.model_validate(
                value["data"]["receipt"]
            ).model_dump(mode="json")
            if (
                receipt["preparation_id"] != identifier
                or receipt["source_activation_id"] != ticket["source_activation_id"]
                or receipt["ticket_sha256"]
                != hashlib.sha256(canonical(ticket)).hexdigest()
                or receipt["lifecycle_sha256"] != ticket["prepared_lifecycle_sha256"]
            ):
                raise authority.AuthorityManagementError("reactivation_source_changed")
        if include_configuration:
            grant, _ = preparation._current(manager, db, key, installation_id, prepared)
            if (
                expected_grant_record_revision is None
                or grant["revision"] != expected_grant_record_revision
                or value["state"] != "confirmed"
                or reserved is not None
                or expected_recovery_revision is None
            ):
                raise authority.AuthorityManagementError("reactivation_unavailable")
            return {
                "sha256": ticket["package_sha256"],
                "instance_id": ticket["instance_id"],
                "configuration": _configuration(db, installation_id, prepared[1]),
                "source_revision": value["revision"],
            }
        return {
            "installation_id": installation_id,
            "source_recovery_id": identifier,
            "source_revision": value["revision"],
            "source_state": value["state"],
            "recovered_activation_id": ticket["source_activation_id"],
            "latest_reactivation_id": reserved,
            "metadata_only": True,
            "permission_approval": "not_evaluated",
        }


def _stopped_source(
    db, key, installation_id, identifier, secret, bindings, reserved=None
):
    row = db.get(Action, identifier, populate_existing=True)
    value = authority._load(db, key, "action", row, identifier)
    ticket, purpose = _activation_recovery_ticket(value["data"]["result"]["ticket"])
    receipt = _RelationalActivationRecoveryResult.model_validate(
        value["data"]["receipt"]
    ).model_dump(mode="json")
    verify_metadata(secret, purpose, ticket)  # Historical stop, not renewed authority.
    verify_metadata(secret, "activation_recovery_result", receipt)
    source_row, source, original = recovery._source(
        db,
        key,
        installation_id,
        ticket["source_activation_id"],
        secret,
        {name: bindings[name] for name in activation.STABLE_FIELDS},
    )
    if (
        value["installation_id"] != installation_id
        or value["data"]["operation"] != recovery.OPERATION
        or value["state"] != "confirmed"
        or ticket["preparation_id"] != identifier
        or source["data"].get("activation_recovery_id") != identifier
        or source["state"] != ticket["source_state"]
        or (purpose == "reactivation_recovery")
        != (original["action"] == "reactivate_prepared_service")
        or value["data"].get("reactivation_id") != reserved
        or source["data"].get("reactivation_id") != reserved
        or (
            reserved is None
            and source["revision"] != ticket["source_activation_revision"]
        )
        or receipt["preparation_id"] != identifier
        or receipt["source_activation_id"] != ticket["source_activation_id"]
        or receipt["ticket_sha256"] != hashlib.sha256(canonical(ticket)).hexdigest()
        or receipt["lifecycle_sha256"] != original["prepared_lifecycle_sha256"]
        or ticket["source_ticket_sha256"]
        != hashlib.sha256(canonical(original)).hexdigest()
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
    ):
        raise authority.AuthorityManagementError("reactivation_stop_source_changed")
    return row, value, ticket, receipt, source_row, source, original


def issue_prepared_reactivation(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    source_recovery_id,
    expected_recovery_revision,
    expected_grant_record_revision,
    confirm_restart_stopped_prepared_service,
    transport_secret,
    service_uid,
    service_gid,
    coordinator_uid,
):
    """Fresh current rights/native review AND explicit new start are required."""
    if confirm_restart_stopped_prepared_service is not True:
        raise authority.AuthorityManagementError("reactivation_confirmation_required")
    source_id = authority._identifier(source_recovery_id)
    expected = authority._identifier(expected_recovery_revision)
    grant_revision = authority._identifier(expected_grant_record_revision)
    if type(transport_secret) is not bytes or len(transport_secret) != 32:
        raise ValueError("Invalid reactivation signing dependency")
    prepared = manager._prepare(installation_id)
    with manager._write(
        installation_id,
        actor_token,
        request_id,
        OPERATION,
        {
            "source_recovery_id": source_id,
            "source_revision": expected,
            "grant_record_revision": grant_revision,
            "service_uid": service_uid,
            "service_gid": service_gid,
            "coordinator_uid": coordinator_uid,
            "transport_key_sha256": hashlib.sha256(transport_secret).hexdigest(),
        },
    ) as (db, key, mutation, _actor_value, result):
        if result:
            raise authority.AuthorityManagementError("reactivation_ticket_consumed")
        grant, definition = preparation._current(
            manager, db, key, installation_id, prepared
        )
        # Recheck the uploaded package pin in the final transaction as well as
        # current rights. Preparation outside the lease is never final authority.
        stable = recovery._stable(
            db, key, installation_id, prepared, mutation.guard.generation
        )
        bindings = preparation._bindings(
            db, installation_id, prepared, grant, definition, mutation.guard.generation
        )
        row, source, stop_ticket, stop_receipt, prior_row, prior, original = (
            _stopped_source(
                db, key, installation_id, source_id, transport_secret, stable
            )
        )
        if (
            source["revision"] != expected
            or grant["revision"] != grant_revision
            or any(
                original[name] != item
                for name, item in {
                    "service_uid": service_uid,
                    "service_gid": service_gid,
                    "coordinator_uid": coordinator_uid,
                    "transport_key_sha256": hashlib.sha256(
                        transport_secret
                    ).hexdigest(),
                }.items()
            )
            or db.scalar(
                select(func.count())
                .select_from(Action)
                .where(Action.installation_id == installation_id)
            )
            >= preparation.MAX_PREPARATION_ACTIONS
        ):
            raise authority.AuthorityManagementError("reactivation_changed")
        # Fence both the old stop callback and attempts to stop/restart from the
        # old source. Their immutable tickets, outcomes and receipts stay intact.
        for saved_row, saved in ((row, source), (prior_row, prior)):
            saved["data"]["reactivation_id"] = request_id
            saved["revision"] = authority.new_authority_generation()
            authority._save(db, key, "action", saved_row, saved)
        boot, now = authority._clock()
        result["ticket"] = _RelationalReactivationTicket.model_validate(
            sign_metadata(
                transport_secret,
                "reactivation",
                {
                    "version": 1,
                    "action": "reactivate_prepared_service",
                    "preparation_id": request_id,
                    "source_preparation_id": original["source_preparation_id"],
                    "prepared_lifecycle_sha256": original["prepared_lifecycle_sha256"],
                    "database_lineage": original["database_lineage"],
                    "origin_activation_id": original.get(
                        "origin_activation_id", original["preparation_id"]
                    ),
                    "source_recovery_id": source_id,
                    "source_recovery_revision": source["revision"],
                    "source_activation_revision": prior["revision"],
                    "source_recovery_ticket": stop_ticket,
                    "source_recovery_receipt": stop_receipt,
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
    return result["ticket"]


def verify_reactivation_source(db, key, installation_id, ticket, secret, bindings):
    _, source, stop_ticket, stop_receipt, _, prior, original = _stopped_source(
        db,
        key,
        installation_id,
        ticket["source_recovery_id"],
        secret,
        bindings,
        reserved=ticket["preparation_id"],
    )
    if (
        source["revision"] != ticket["source_recovery_revision"]
        or prior["revision"] != ticket["source_activation_revision"]
        or stop_ticket != ticket["source_recovery_ticket"]
        or stop_receipt != ticket["source_recovery_receipt"]
        or ticket["origin_activation_id"]
        != original.get("origin_activation_id", original["preparation_id"])
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
            )
        )
    ):
        raise authority.AuthorityManagementError("reactivation_source_changed")
    return original["prepared_lifecycle_sha256"]
