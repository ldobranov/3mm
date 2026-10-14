"""Private LOCAL one-use boot enable, independent of start and SQL permission.

Current grants/native review are checked, never created or restored. The exact
successful start is reserved once in the existing sealed Action journal. No
Root files, process I/O or application SQL under Core leases. Not public/SDK or
deployed CLI dispatch; actual boot acceptance remains a separate test gate.
"""

import hashlib
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services import application_relational_activation as activation
from backend.services import application_relational_activation_recovery as recovery
from backend.services import application_relational_lifecycle as preparation
from backend.services.application_authority_sources import _configuration
from backend.services.application_policy_reviews import _actor
from backend.services.authority_metadata import (
    authority_transaction,
    read_application_authority,
)
from three_mm_application_sdk.relational_wire import (
    _RelationalBootEnableResult,
    _RelationalBootEnableTicket,
    canonical,
    sign_metadata,
    verify_metadata,
)

OPERATION = "relational_enable_prepared_boot"


def _current(manager, db, key, installation_id, prepared, generation, runtime_root):
    if not Path(runtime_root).is_absolute():
        raise authority.AuthorityManagementError("boot_enable_layout_unavailable")
    stable = recovery._stable(db, key, installation_id, prepared, generation)
    definition = prepared[1].application_extension
    grant = manager._require_grant(
        db, key, installation_id, prepared, "storage:relational_read"
    )
    if definition.storage.relational.mode == "read_write":
        manager._require_grant(
            db, key, installation_id, prepared, "storage:relational_write"
        )
    row = db.get(Installation, installation_id, populate_existing=True)
    if (
        not row.enabled
        or row.status != "active"
        or row.active_version != prepared[0].version
        or row.socket_path
        != str(Path(runtime_root) / stable["instance_id"] / "run/service.sock")
    ):
        raise authority.AuthorityManagementError("active_boot_enable_required")
    bindings = preparation._bindings(
        db, installation_id, prepared, grant, definition, generation
    )
    if any(bindings[name] != value for name, value in stable.items()):
        raise authority.AuthorityManagementError("boot_enable_binding_changed")
    return bindings


def _source(db, key, installation_id, source_id, secret, bindings, *, reserved=None):
    row, source, original = recovery._source(
        db,
        key,
        installation_id,
        source_id,
        secret,
        {name: bindings[name] for name in activation.STABLE_FIELDS},
    )
    if (
        source["state"] != "activated"
        or source["data"].get("activation_recovery_id") is not None
        or source["data"].get("reactivation_id") is not None
        or source["data"].get("boot_enable_id") != reserved
    ):
        raise authority.AuthorityManagementError(
            "successful_start_unavailable_or_consumed"
        )
    return row, source, original


def inspect_boot_enable_source(
    manager,
    installation_id,
    *,
    actor_token,
    source_activation_id,
    expected_activation_revision,
    expected_grant_record_revision,
    runtime_root,
):
    """Private read-only snapshot BEFORE Root opens the instance key.

    Core seal/current rights authenticate this snapshot. Transport signatures,
    prepared chain and physical Root witness are checked separately at issue/
    execution; this snapshot is never a boot permission or process statement.
    """
    source_id = authority._identifier(source_activation_id)
    expected = authority._identifier(expected_activation_revision)
    grant = authority._identifier(expected_grant_record_revision)
    prepared = manager._prepare(installation_id)
    with (
        manager.keys.locked() as key,
        Session(manager.engine) as db,
        authority_transaction(db) as mutation,
    ):
        _actor(db, actor_token)
        bindings = _current(
            manager,
            db,
            key,
            installation_id,
            prepared,
            mutation.guard.generation,
            runtime_root,
        )
        _, source, ticket = recovery._sealed_source(
            db,
            key,
            installation_id,
            source_id,
            {name: bindings[name] for name in activation.STABLE_FIELDS},
        )
        if (
            source["state"] != "activated"
            or source["revision"] != expected
            or bindings["grant_record_revision"] != grant
            or any(
                source["data"].get(name) is not None
                for name in (
                    "activation_recovery_id",
                    "reactivation_id",
                    "boot_enable_id",
                )
            )
        ):
            raise authority.AuthorityManagementError("boot_enable_source_changed")
        return {
            "sha256": ticket["package_sha256"],
            "instance_id": ticket["instance_id"],
            "configuration": _configuration(db, installation_id, prepared[1]),
            "source_revision": source["revision"],
        }


def issue_boot_enable(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    source_activation_id,
    expected_activation_revision,
    expected_grant_record_revision,
    confirm_enable_prepared_boot,
    transport_secret,
    service_uid,
    service_gid,
    coordinator_uid,
    runtime_root,
):
    """Trusted private coordinator supplies key/principals, never a package."""
    if confirm_enable_prepared_boot is not True:
        raise authority.AuthorityManagementError("boot_enable_confirmation_required")
    source_id = authority._identifier(source_activation_id)
    expected = authority._identifier(expected_activation_revision)
    grant_revision = authority._identifier(expected_grant_record_revision)
    if type(transport_secret) is not bytes or len(transport_secret) != 32:
        raise ValueError("Invalid boot enable signing dependency")
    if any(
        type(value) is not int or not 0 < value <= 2147483647
        for value in (service_uid, service_gid, coordinator_uid)
    ):
        raise authority.AuthorityManagementError("invalid_boot_enable_principal")
    prepared = manager._prepare(installation_id)
    with manager._write(
        installation_id,
        actor_token,
        request_id,
        OPERATION,
        {
            "source_activation_id": source_id,
            "source_revision": expected,
            "grant_record_revision": grant_revision,
            "service_uid": service_uid,
            "service_gid": service_gid,
            "coordinator_uid": coordinator_uid,
            "transport_key_sha256": hashlib.sha256(transport_secret).hexdigest(),
        },
    ) as (db, key, mutation, _actor_value, result):
        if result:
            raise authority.AuthorityManagementError("boot_enable_ticket_consumed")
        bindings = _current(
            manager,
            db,
            key,
            installation_id,
            prepared,
            mutation.guard.generation,
            runtime_root,
        )
        row, source, original = _source(
            db, key, installation_id, source_id, transport_secret, bindings
        )
        if (
            source["revision"] != expected
            or bindings["grant_record_revision"] != grant_revision
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
            >= preparation.MAX_PREPARATION_ACTIONS
        ):
            raise authority.AuthorityManagementError("boot_enable_changed")
        source["data"]["boot_enable_id"] = request_id
        source["revision"] = authority.new_authority_generation()
        boot, now = authority._clock()
        ticket = _RelationalBootEnableTicket.model_validate(
            sign_metadata(
                transport_secret,
                "boot_enable",
                {
                    "version": 1,
                    "action": "enable_prepared_boot",
                    "preparation_id": request_id,
                    "source_activation_id": source_id,
                    "source_activation_revision": source["revision"],
                    "source_activation_action": original["action"],
                    "source_ticket_sha256": hashlib.sha256(
                        canonical(original)
                    ).hexdigest(),
                    "source_receipt_sha256": hashlib.sha256(
                        canonical(source["data"]["receipt"])
                    ).hexdigest(),
                    **{
                        name: original[name]
                        for name in (
                            "source_preparation_id",
                            "prepared_lifecycle_sha256",
                            "database_lineage",
                            "service_uid",
                            "service_gid",
                            "coordinator_uid",
                            "transport_key_sha256",
                        )
                    },
                    **bindings,
                    "boot_id": boot,
                    "issued_at_ms": now,
                    "deadline_ms": now + 300000,
                },
            )
        ).model_dump(mode="json")
        authority._save(db, key, "action", row, source)
        result["ticket"] = ticket
    return ticket


def boot_enable_checkpoint(
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
    """Fixed helper callback; never changes grant, enabled row, epoch or SQL."""
    ticket = _RelationalBootEnableTicket.model_validate(ticket).model_dump(mode="json")
    verify_metadata(transport_secret, "boot_enable", ticket)
    if (
        phase not in {"authorize", "begin", "check", "finish"}
        or (phase != "finish" and receipt is not None)
        or ticket["transport_key_sha256"]
        != hashlib.sha256(transport_secret).hexdigest()
    ):
        raise authority.AuthorityManagementError("invalid_boot_enable_phase")
    prepared = manager._prepare(installation_id)
    with (
        manager.keys.locked() as key,
        Session(manager.engine) as db,
        authority_transaction(db) as mutation,
    ):
        actor = list(_actor(db, actor_token))
        row = db.get(Action, ticket["preparation_id"], populate_existing=True)
        value = authority._load(db, key, "action", row, ticket["preparation_id"])
        bindings = _current(
            manager,
            db,
            key,
            installation_id,
            prepared,
            mutation.guard.generation,
            runtime_root,
        )
        _, source, original = _source(
            db,
            key,
            installation_id,
            ticket["source_activation_id"],
            transport_secret,
            bindings,
            reserved=ticket["preparation_id"],
        )
        boot, now = authority._clock()
        if (
            value["installation_id"] != installation_id
            or value["data"]["operation"] != OPERATION
            or value["data"]["actor"] != actor
            or value["data"]["result"]["ticket"] != ticket
            or source["revision"] != ticket["source_activation_revision"]
            or original["action"] != ticket["source_activation_action"]
            or hashlib.sha256(canonical(original)).hexdigest()
            != ticket["source_ticket_sha256"]
            or hashlib.sha256(canonical(source["data"]["receipt"])).hexdigest()
            != ticket["source_receipt_sha256"]
            or any(ticket[name] != expected for name, expected in bindings.items())
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
            or boot != ticket["boot_id"]
            or not ticket["issued_at_ms"] <= now < ticket["deadline_ms"]
        ):
            raise authority.AuthorityManagementError(
                "boot_enable_superseded_or_changed"
            )
        mutation.lock_application(read_application_authority(db, installation_id))
        if phase in {"authorize", "begin"}:
            if value["state"] != "recorded":
                raise authority.AuthorityManagementError("boot_enable_ticket_consumed")
            if phase == "authorize":
                return {"state": "authorized_enable_only"}
            value["state"] = "execution_unconfirmed"
        else:
            if value["state"] != "execution_unconfirmed":
                raise authority.AuthorityManagementError("boot_enable_ticket_consumed")
            if phase == "check":
                return {"state": "execution_unconfirmed"}
            receipt = _RelationalBootEnableResult.model_validate(receipt).model_dump(
                mode="json"
            )
            verify_metadata(transport_secret, "boot_enable_result", receipt)
            if (
                receipt["preparation_id"] != ticket["preparation_id"]
                or receipt["ticket_sha256"]
                != hashlib.sha256(canonical(ticket)).hexdigest()
                or receipt["source_activation_id"] != ticket["source_activation_id"]
                or receipt["lifecycle_sha256"] != ticket["prepared_lifecycle_sha256"]
            ):
                raise authority.AuthorityManagementError("boot_enable_receipt_changed")
            value["state"] = "confirmed"
            value["data"]["receipt"] = receipt
        value["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, value)
        db.add(
            AuditLog(
                user_id=actor[0],
                action="APPLICATION_RELATIONAL_BOOT_" + phase.upper(),
                entity_type="application_extension",
                entity_name=prepared[0].module_id,
                changes={
                    "boot_enable_id": ticket["preparation_id"],
                    "source_activation_id": ticket["source_activation_id"],
                    "state": value["state"],
                },
            )
        )
        mutation.advance_guard_revision()
    return {
        "state": (
            "boot_enabled_not_started" if phase == "finish" else "execution_unconfirmed"
        )
    }
