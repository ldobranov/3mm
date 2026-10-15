"""Fixed installed recovery/resumption wiring; no caller paths or secrets."""

import os
import re

from three_mm_application_sdk.relational_preparation_recovery_wire import (
    _EmptyPreparationRecoveryTicket,
)
from three_mm_application_sdk.relational_wire import (
    _RelationalMigrationPreparationTicket,
    verify_metadata,
)
from three_mm_runtime.application_relational_namespace import _roots
from three_mm_runtime.application_relational_preparation import (
    _key,
    prepare_migrated_relational_database,
)
from three_mm_runtime.application_relational_preparation_recovery import (
    reconcile_restored_empty_preparation,
    validate_preparation_resumption,
)

ACTIONS = {
    "recover_application_relational_preparation",
    "resume_application_relational_preparation",
}
METADATA_ACTIONS = {
    "inspect_empty_preparation",
    "issue_empty_preparation_recovery",
    "empty_preparation_recovery_checkpoint",
    "inspect_preparation_resumption",
    "issue_preparation_resumption",
}


def preparation_recovery_request(value):
    common = {
        "action",
        "installation_id",
        "actor_token",
        "expected_grant_record_revision",
        "request_id",
    }
    operation = value.get("action") if type(value) is dict else None
    if operation == "recover_application_relational_preparation":
        fields = common | {
            "source_preparation_id",
            "source_namespace_id",
            "expected_preparation_revision",
            "confirm_restored_empty_checkpoint",
        }
        confirmation = "confirm_restored_empty_checkpoint"
    elif operation == "resume_application_relational_preparation":
        fields = common | {
            "source_recovery_id",
            "expected_recovery_revision",
            "confirm_owned_business_migrations",
        }
        confirmation = "confirm_owned_business_migrations"
    else:
        raise ValueError("Unsupported preparation recovery action")
    if (
        set(value) != fields
        or type(value["installation_id"]) is not int
        or value["installation_id"] < 1
        or type(value["actor_token"]) is not str
        or not 1 <= len(value["actor_token"]) <= 4096
        or value[confirmation] is not True
        or any(
            type(value[name]) is not str
            or not re.fullmatch(r"[0-9a-f]{32}", value[name])
            for name in fields
            - {"action", "installation_id", "actor_token", confirmation}
        )
    ):
        raise ValueError("Invalid preparation recovery request")
    return value


def preparation_recovery_metadata(manager, value):
    """Core-UID dispatch for exactly five metadata operations, never a generic RPC."""
    from backend.services import (
        application_relational_preparation_recovery as coordinator,
    )

    common = {
        "action",
        "installation_id",
        "actor_token",
        "expected_grant_record_revision",
    }
    operation = value["action"]
    resume = operation in {
        "inspect_preparation_resumption",
        "issue_preparation_resumption",
    }
    fields = common | (
        {"source_recovery_id", "expected_recovery_revision"}
        if resume
        else {
            "source_preparation_id",
            "source_namespace_id",
            "expected_preparation_revision",
        }
    )
    if operation in {
        "issue_empty_preparation_recovery",
        "issue_preparation_resumption",
    }:
        fields |= {"request_id", "transport_secret"}
    if operation == "empty_preparation_recovery_checkpoint":
        fields |= {"ticket", "phase", "receipt", "transport_secret"}
    if (
        type(value) is not dict
        or set(value) != fields
        or type(value["installation_id"]) is not int
        or value["installation_id"] < 1
        or type(value["actor_token"]) is not str
        or not 1 <= len(value["actor_token"]) <= 4096
    ):
        raise ValueError("Invalid preparation recovery metadata")
    arguments = {
        name: value[name]
        for name in fields
        - {
            "action",
            "installation_id",
            "request_id",
            "transport_secret",
            "ticket",
            "phase",
            "receipt",
        }
    }
    if operation == "inspect_empty_preparation":
        return coordinator.inspect_empty_preparation_source(
            manager, value["installation_id"], **arguments, include_configuration=True
        )
    if operation == "inspect_preparation_resumption":
        return coordinator.inspect_preparation_resumption(
            manager, value["installation_id"], **arguments
        )
    secret = value["transport_secret"]
    if type(secret) is not str or not re.fullmatch(r"[0-9a-f]{64}", secret):
        raise ValueError("Invalid private recovery dependency")
    secret = bytes.fromhex(secret)
    if operation == "issue_empty_preparation_recovery":
        return coordinator.issue_empty_preparation_recovery(
            manager,
            value["installation_id"],
            **arguments,
            request_id=value["request_id"],
            transport_secret=secret,
            confirm_restored_empty_checkpoint=True,
        )
    if operation == "issue_preparation_resumption":
        return coordinator.issue_preparation_resumption(
            manager,
            value["installation_id"],
            **arguments,
            request_id=value["request_id"],
            transport_secret=secret,
            confirm_owned_business_migrations=True,
        )
    ticket = _EmptyPreparationRecoveryTicket.model_validate(value["ticket"]).model_dump(
        mode="json"
    )
    if any(
        ticket[name] != value[name]
        for name in (
            "source_preparation_id",
            "source_namespace_id",
            "grant_record_revision",
        )
        if name != "grant_record_revision"
    ) or (
        ticket["grant_record_revision"] != value["expected_grant_record_revision"]
        or ticket["source_preparation_revision"]
        != value["expected_preparation_revision"]
    ):
        raise ValueError("Preparation recovery frame changed")
    return coordinator.empty_preparation_recovery_checkpoint(
        manager,
        value["installation_id"],
        ticket,
        value["phase"],
        actor_token=value["actor_token"],
        transport_secret=secret,
        receipt=value["receipt"],
    )


def recover_installed_preparation(
    value,
    *,
    metadata,
    upload_root,
    root,
    key_root,
    state_root,
    service_uid,
    service_gid,
    coordinator_uid,
    supervisor=None,
):
    value = preparation_recovery_request(value)
    if os.name != "posix" or os.geteuid() != 0:
        raise ValueError("Root preparation recovery helper required")
    resume = value["action"] == "resume_application_relational_preparation"
    common = {
        name: value[name]
        for name in (
            "installation_id",
            "actor_token",
            "expected_grant_record_revision",
            *(
                ("source_recovery_id", "expected_recovery_revision")
                if resume
                else (
                    "source_preparation_id",
                    "source_namespace_id",
                    "expected_preparation_revision",
                )
            ),
        )
    }
    snapshot = metadata.call(
        dict(
            common,
            action=(
                "inspect_preparation_resumption"
                if resume
                else "inspect_empty_preparation"
            ),
        )
    )
    expected_fields = (
        {
            "sha256",
            "instance_id",
            "configuration",
            "recovery_ticket",
            "recovery_receipt",
        }
        if resume
        else {
            "sha256",
            "instance_id",
            "configuration",
            "source_preparation_id",
            "source_namespace_id",
            "source_revision",
            "state",
            "source_ticket",
            "namespace_ticket",
        }
    )
    if (
        type(snapshot) is not dict
        or set(snapshot) != expected_fields
        or type(snapshot["sha256"]) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", snapshot["sha256"])
        or type(snapshot["instance_id"]) is not str
        or not re.fullmatch(r"[0-9a-f]{24}", snapshot["instance_id"])
        or type(snapshot["configuration"]) is not dict
    ):
        raise ValueError("Installed preparation recovery source unavailable")
    root, key_root, state_root = _roots((root, key_root, state_root), coordinator_uid)
    instance = root / snapshot["instance_id"]
    secret = _key(key_root / (instance.name + ".key"))
    if resume:
        # Capability and local witness checks precede issuance of new SQL consent.
        from three_mm_runtime.application_relational_migrations import (
            require_migration_worker_privileges,
        )

        require_migration_worker_privileges()
        validate_preparation_resumption(
            instance, snapshot["recovery_ticket"], snapshot["recovery_receipt"], secret
        )
    ticket = metadata.call(
        dict(
            common,
            action=(
                "issue_preparation_resumption"
                if resume
                else "issue_empty_preparation_recovery"
            ),
            request_id=value["request_id"],
            transport_secret=secret.hex(),
        )
    )
    model = (
        _RelationalMigrationPreparationTicket
        if resume
        else _EmptyPreparationRecoveryTicket
    )
    ticket = model.model_validate(ticket).model_dump(mode="json")
    verify_metadata(
        secret,
        "migration_preparation" if resume else "empty_preparation_recovery",
        ticket,
    )
    if (
        ticket["preparation_id"] != value["request_id"]
        or ticket["instance_id"] != instance.name
        or ticket["package_sha256"] != snapshot["sha256"]
        or ticket["grant_record_revision"] != value["expected_grant_record_revision"]
    ):
        raise ValueError("Preparation recovery issuance changed")

    def checkpoint(current, phase, *, receipt=None):
        if resume:
            fields = {
                name: common[name]
                for name in (
                    "installation_id",
                    "actor_token",
                    "expected_grant_record_revision",
                )
            }
        else:
            fields = dict(
                common,
                expected_preparation_revision=ticket["source_preparation_revision"],
            )
        return metadata.call(
            dict(
                fields,
                action=(
                    "checkpoint" if resume else "empty_preparation_recovery_checkpoint"
                ),
                ticket=current,
                phase=phase,
                receipt=receipt,
                transport_secret=secret.hex(),
            )
        )

    arguments = dict(
        configuration=snapshot["configuration"],
        root=root,
        key_root=key_root,
        state_root=state_root,
        service_uid=service_uid,
        service_gid=service_gid,
        checkpoint=checkpoint,
        supervisor=supervisor,
    )
    package = upload_root / (snapshot["sha256"] + ".zip")
    if resume:
        return prepare_migrated_relational_database(
            package,
            ticket,
            **arguments,
            resumption=(snapshot["recovery_ticket"], snapshot["recovery_receipt"]),
        )
    return reconcile_restored_empty_preparation(
        package,
        ticket,
        snapshot["source_ticket"],
        snapshot["namespace_ticket"],
        **arguments,
        transport_secret=secret,
        coordinator_uid=coordinator_uid,
    )
