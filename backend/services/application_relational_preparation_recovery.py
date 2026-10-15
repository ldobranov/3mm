"""Exact LOCAL consent for restored-empty initial migration reconciliation.

Original uncertainty stays historical. No SQL, paths, rekey, grant or start.
Current native review/session/grants and the exact source revision are required.
"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.services import application_authority_management as authority
from backend.services.application_authority_sources import _configuration
from backend.services.application_policy_reviews import _actor
from backend.services.application_relational_lifecycle import (
    MAX_PREPARATION_ACTIONS,
    _bindings,
    _current,
    _issue_preparation,
)
from backend.services.authority_metadata import (
    authority_transaction,
    read_application_authority,
)
from three_mm_application_sdk.relational_preparation_recovery_wire import (
    _EmptyPreparationRecoveryResult,
    _EmptyPreparationRecoveryTicket,
)
from three_mm_application_sdk.relational_wire import (
    _RelationalMigrationPreparationTicket,
    _RelationalNamespacePreparationResult,
    _RelationalNamespacePreparationTicket,
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


def _sources(db, key, installation_id, source_id, namespace_id, secret=None):
    row = db.get(Action, source_id, populate_existing=True)
    value = authority._load(db, key, "action", row, source_id)
    ns_row = db.get(Action, namespace_id, populate_existing=True)
    ns_value = authority._load(db, key, "action", ns_row, namespace_id)
    if (
        source_id == namespace_id
        or value["installation_id"] != installation_id
        or value["data"].get("operation") != "relational_prepare_migrated"
        or value["state"] != "execution_unconfirmed"
        or "receipt" in value["data"]
        or ns_value["installation_id"] != installation_id
        or ns_value["data"].get("operation") != "relational_prepare_namespace"
        or ns_value["state"] != "prepared"
        or ns_value["data"].get("namespace_recovery_id") is not None
    ):
        raise authority.AuthorityManagementError("empty_preparation_source_unavailable")
    source = _RelationalMigrationPreparationTicket.model_validate(
        value["data"]["result"]["ticket"]
    ).model_dump(mode="json")
    namespace = _RelationalNamespacePreparationTicket.model_validate(
        ns_value["data"]["result"]["ticket"]
    ).model_dump(mode="json")
    receipt = _RelationalNamespacePreparationResult.model_validate(
        ns_value["data"].get("receipt")
    ).model_dump(mode="json")
    if (
        source["preparation_id"] != source_id
        or namespace["preparation_id"] != namespace_id
        or any(source[name] != namespace[name] for name in STABLE)
        or receipt["preparation_id"] != namespace_id
        or receipt["ticket_sha256"] != hashlib.sha256(canonical(namespace)).hexdigest()
    ):
        raise authority.AuthorityManagementError("empty_preparation_source_changed")
    if secret is not None:
        verify_metadata(secret, "migration_preparation", source)
        verify_metadata(secret, "namespace_preparation", namespace)
        verify_metadata(secret, "namespace_preparation_result", receipt)
        if namespace["transport_key_sha256"] != hashlib.sha256(secret).hexdigest():
            raise authority.AuthorityManagementError("empty_preparation_key_changed")
    return row, value, source, namespace


def inspect_empty_preparation_source(
    manager,
    installation_id,
    *,
    actor_token,
    source_preparation_id,
    source_namespace_id,
    expected_grant_record_revision,
    expected_preparation_revision=None,
    include_configuration=False,
):
    source_id = authority._identifier(source_preparation_id)
    namespace_id = authority._identifier(source_namespace_id)
    expected = authority._identifier(expected_grant_record_revision)
    prepared = manager._prepare(installation_id)
    with (
        manager.keys.locked() as key,
        Session(manager.engine) as db,
        authority_transaction(db) as mutation,
    ):
        _actor(db, actor_token)
        _, value, source, namespace = _sources(
            db, key, installation_id, source_id, namespace_id
        )
        grant, definition = _current(manager, db, key, installation_id, prepared)
        bindings = _bindings(
            db, installation_id, prepared, grant, definition, mutation.guard.generation
        )
        if (
            grant["revision"] != expected
            or any(bindings[name] != source[name] for name in STABLE)
            or (
                expected_preparation_revision is not None
                and value["revision"]
                != authority._identifier(expected_preparation_revision)
            )
        ):
            raise authority.AuthorityManagementError("empty_preparation_changed")
        result = {
            "source_preparation_id": source_id,
            "source_namespace_id": namespace_id,
            "source_revision": value["revision"],
            "state": value["state"],
        }
        if include_configuration:
            result.update(
                sha256=prepared[0].sha256,
                instance_id=source["instance_id"],
                configuration=_configuration(db, installation_id, prepared[1]),
                source_ticket=source,
                namespace_ticket=namespace,
            )
        return result


def issue_empty_preparation_recovery(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    source_preparation_id,
    source_namespace_id,
    expected_preparation_revision,
    expected_grant_record_revision,
    confirm_restored_empty_checkpoint,
    transport_secret,
):
    if confirm_restored_empty_checkpoint is not True:
        raise authority.AuthorityManagementError(
            "empty_preparation_confirmation_required"
        )
    source_id = authority._identifier(source_preparation_id)
    namespace_id = authority._identifier(source_namespace_id)
    expected_source = authority._identifier(expected_preparation_revision)
    expected_grant = authority._identifier(expected_grant_record_revision)
    prepared = manager._prepare(installation_id)
    with manager._write(
        installation_id,
        actor_token,
        request_id,
        "relational_empty_preparation_recovery",
        {
            "source_preparation_id": source_id,
            "source_namespace_id": namespace_id,
            "source_revision": expected_source,
            "grant_record_revision": expected_grant,
        },
    ) as (db, key, mutation, actor, result):
        if result:
            raise authority.AuthorityManagementError(
                "empty_preparation_ticket_consumed"
            )
        row, value, source, namespace = _sources(
            db, key, installation_id, source_id, namespace_id, transport_secret
        )
        grant, definition = _current(manager, db, key, installation_id, prepared)
        bindings = _bindings(
            db, installation_id, prepared, grant, definition, mutation.guard.generation
        )
        if (
            value["revision"] != expected_source
            or grant["revision"] != expected_grant
            or any(bindings[name] != source[name] for name in STABLE)
            or db.scalar(
                select(func.count())
                .select_from(Action)
                .where(Action.installation_id == installation_id)
            )
            >= MAX_PREPARATION_ACTIONS
        ):
            raise authority.AuthorityManagementError("empty_preparation_changed")
        value["revision"] = authority.new_authority_generation()
        value["data"]["preparation_recovery_id"] = request_id
        boot, now = authority._clock()
        result["ticket"] = _EmptyPreparationRecoveryTicket.model_validate(
            sign_metadata(
                transport_secret,
                "empty_preparation_recovery",
                {
                    "version": 1,
                    "action": "reconcile_restored_empty_preparation",
                    "preparation_id": request_id,
                    "source_preparation_id": source_id,
                    "source_preparation_revision": value["revision"],
                    "source_ticket_sha256": hashlib.sha256(
                        canonical(source)
                    ).hexdigest(),
                    "source_namespace_id": namespace_id,
                    "source_namespace_sha256": hashlib.sha256(
                        canonical(namespace)
                    ).hexdigest(),
                    "database_lineage": source["database_lineage"],
                    **bindings,
                    **{
                        name: namespace[name]
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
        authority._save(db, key, "action", row, value)
    return result["ticket"]


def empty_preparation_recovery_checkpoint(
    manager,
    installation_id,
    ticket,
    phase,
    *,
    actor_token,
    transport_secret,
    receipt=None,
):
    ticket = _EmptyPreparationRecoveryTicket.model_validate(ticket).model_dump(
        mode="json"
    )
    verify_metadata(transport_secret, "empty_preparation_recovery", ticket)
    if phase not in {"authorize", "begin", "check", "finish"} or (
        phase != "finish" and receipt is not None
    ):
        raise authority.AuthorityManagementError("invalid_empty_preparation_phase")
    prepared = manager._prepare(installation_id)
    with (
        manager.keys.locked() as key,
        Session(manager.engine) as db,
        authority_transaction(db) as mutation,
    ):
        actor = list(_actor(db, actor_token))
        row = db.get(Action, ticket["preparation_id"], populate_existing=True)
        value = authority._load(db, key, "action", row, ticket["preparation_id"])
        _, source_value, source, namespace = _sources(
            db,
            key,
            installation_id,
            ticket["source_preparation_id"],
            ticket["source_namespace_id"],
            transport_secret,
        )
        if (
            value["installation_id"] != installation_id
            or value["data"].get("operation") != "relational_empty_preparation_recovery"
            or value["data"]["actor"] != actor
            or value["data"]["result"]["ticket"] != ticket
            or source_value["data"].get("preparation_recovery_id")
            != ticket["preparation_id"]
            or source_value["revision"] != ticket["source_preparation_revision"]
            or ticket["source_ticket_sha256"]
            != hashlib.sha256(canonical(source)).hexdigest()
            or ticket["source_namespace_sha256"]
            != hashlib.sha256(canonical(namespace)).hexdigest()
        ):
            raise authority.AuthorityManagementError(
                "empty_preparation_superseded_or_changed"
            )
        grant, definition = _current(manager, db, key, installation_id, prepared)
        bindings = _bindings(
            db, installation_id, prepared, grant, definition, mutation.guard.generation
        )
        boot, now = authority._clock()
        if (
            boot != ticket["boot_id"]
            or not ticket["issued_at_ms"] <= now < ticket["deadline_ms"]
            or any(ticket[name] != expected for name, expected in bindings.items())
        ):
            raise authority.AuthorityManagementError("empty_preparation_changed")
        current = read_application_authority(db, installation_id)
        mutation.lock_application(current)
        if phase in {"authorize", "begin"}:
            if value["state"] != "recorded":
                raise authority.AuthorityManagementError(
                    "empty_preparation_ticket_consumed"
                )
            if phase == "authorize":
                return {"state": "authorized_not_started"}
            value["state"] = "execution_unconfirmed"
        else:
            if value["state"] not in {"execution_unconfirmed", "confirmed"}:
                raise authority.AuthorityManagementError(
                    "empty_preparation_not_started"
                )
            if phase == "check":
                if value["state"] == "confirmed":
                    raise authority.AuthorityManagementError(
                        "empty_preparation_ticket_consumed"
                    )
                return {"state": "execution_unconfirmed"}
            receipt = _EmptyPreparationRecoveryResult.model_validate(
                receipt
            ).model_dump(mode="json")
            verify_metadata(
                transport_secret, "empty_preparation_recovery_result", receipt
            )
            if (
                receipt["preparation_id"] != ticket["preparation_id"]
                or receipt["ticket_sha256"]
                != hashlib.sha256(canonical(ticket)).hexdigest()
            ):
                raise authority.AuthorityManagementError(
                    "empty_preparation_receipt_changed"
                )
            if value["state"] == "confirmed":
                if value["data"].get("receipt") != receipt:
                    raise authority.AuthorityManagementError(
                        "empty_preparation_receipt_changed"
                    )
                return {"state": receipt["outcome"], "historical": True}
            value["state"] = "confirmed"
            value["data"]["receipt"] = receipt
        value["revision"] = authority.new_authority_generation()
        authority._save(db, key, "action", row, value)
        db.add(
            AuditLog(
                user_id=actor[0],
                action="APPLICATION_EMPTY_PREPARATION_RECOVERY_" + phase.upper(),
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


def _resume_source(db, key, installation_id, source_id, expected_revision, secret):
    row = db.get(Action, source_id, populate_existing=True)
    value = authority._load(db, key, "action", row, source_id)
    if (
        value["installation_id"] != installation_id
        or value["data"].get("operation") != "relational_empty_preparation_recovery"
        or value["state"] != "confirmed"
        or value["revision"] != expected_revision
        or value["data"].get("resumption_id") is not None
    ):
        raise authority.AuthorityManagementError("preparation_resumption_unavailable")
    ticket = _EmptyPreparationRecoveryTicket.model_validate(
        value["data"]["result"]["ticket"]
    ).model_dump(mode="json")
    receipt = _EmptyPreparationRecoveryResult.model_validate(
        value["data"].get("receipt")
    ).model_dump(mode="json")
    _, source_value, _, _ = _sources(
        db,
        key,
        installation_id,
        ticket["source_preparation_id"],
        ticket["source_namespace_id"],
        secret,
    )
    if (
        source_value["data"].get("preparation_recovery_id") != source_id
        or source_value["revision"] != ticket["source_preparation_revision"]
        or ticket["preparation_id"] != source_id
        or receipt["preparation_id"] != source_id
        or receipt["ticket_sha256"] != hashlib.sha256(canonical(ticket)).hexdigest()
    ):
        raise authority.AuthorityManagementError("preparation_resumption_changed")
    if secret is not None:
        verify_metadata(secret, "empty_preparation_recovery", ticket)
        verify_metadata(secret, "empty_preparation_recovery_result", receipt)
    return row, value, ticket, receipt


def inspect_empty_recovery_record(
    manager, installation_id, *, actor_token, source_recovery_id
):
    source_id = authority._identifier(source_recovery_id)
    with (
        manager.keys.locked() as key,
        Session(manager.engine) as db,
        authority_transaction(db),
    ):
        _actor(db, actor_token)
        row = db.get(Action, source_id, populate_existing=True)
        value = authority._load(db, key, "action", row, source_id)
        if (
            value["installation_id"] != installation_id
            or value["data"].get("operation") != "relational_empty_preparation_recovery"
        ):
            raise authority.AuthorityManagementError("empty_recovery_unavailable")
        ticket = _EmptyPreparationRecoveryTicket.model_validate(
            value["data"]["result"]["ticket"]
        )
        if ticket.preparation_id != source_id:
            raise authority.AuthorityManagementError("empty_recovery_changed")
        return {
            "source_recovery_id": source_id,
            "source_revision": value["revision"],
            "state": value["state"],
            "resumption_reserved": value["data"].get("resumption_id") is not None,
            "permission_approval": "not_evaluated",
        }


def inspect_preparation_resumption(
    manager,
    installation_id,
    *,
    actor_token,
    source_recovery_id,
    expected_recovery_revision,
    expected_grant_record_revision,
):
    source_id = authority._identifier(source_recovery_id)
    expected = authority._identifier(expected_recovery_revision)
    prepared = manager._prepare(installation_id)
    with (
        manager.keys.locked() as key,
        Session(manager.engine) as db,
        authority_transaction(db) as mutation,
    ):
        _actor(db, actor_token)
        _, _, ticket, receipt = _resume_source(
            db, key, installation_id, source_id, expected, None
        )
        grant, definition = _current(manager, db, key, installation_id, prepared)
        bindings = _bindings(
            db, installation_id, prepared, grant, definition, mutation.guard.generation
        )
        if grant["revision"] != authority._identifier(
            expected_grant_record_revision
        ) or any(bindings[name] != ticket[name] for name in STABLE):
            raise authority.AuthorityManagementError("preparation_resumption_changed")
        return {
            "sha256": prepared[0].sha256,
            "instance_id": ticket["instance_id"],
            "configuration": _configuration(db, installation_id, prepared[1]),
            "recovery_ticket": ticket,
            "recovery_receipt": receipt,
        }


def reserve_preparation_resumption(
    db, key, installation_id, recovery_source, *, transport_secret, request_id, bindings
):
    row, value, ticket, _ = _resume_source(
        db, key, installation_id, *recovery_source, transport_secret
    )
    if any(bindings[name] != ticket[name] for name in STABLE):
        raise authority.AuthorityManagementError("preparation_resumption_changed")
    value["data"]["resumption_id"] = request_id
    value["revision"] = authority.new_authority_generation()
    authority._save(db, key, "action", row, value)


def issue_preparation_resumption(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    source_recovery_id,
    expected_recovery_revision,
    expected_grant_record_revision,
    confirm_owned_business_migrations,
    transport_secret,
):
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
        recovery_source=(
            authority._identifier(source_recovery_id),
            authority._identifier(expected_recovery_revision),
        ),
    )
