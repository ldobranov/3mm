"""Closed local upgrade/reconciliation dialect. No caller paths, SQL or UIDs."""

import hashlib
import os
import re

from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeConfirmationTicket,
    _RelationalUpgradeResult,
    _RelationalUpgradeRollbackResult,
    _RelationalUpgradeTicket,
    _rollback_ticket,
)
from three_mm_application_sdk.relational_wire import canonical, verify_metadata
from three_mm_runtime.application_relational_namespace import _roots
from three_mm_runtime.application_relational_preparation import _key

# Fixed operations, not caller-selected function names or executable paths.
OPERATIONS = {
    "upgrade_application_relational": ("upgrade", "confirm_owned_forward_upgrade"),
    "confirm_application_relational_upgrade": (
        "published",
        "confirm_published_upgrade_reviewed",
    ),
    "confirm_application_relational_rollback": (
        "rollback",
        "confirm_restored_state_reviewed",
    ),
    "finish_application_relational_restore": (
        "restore",
        "confirm_finish_interrupted_restore",
    ),
}
ACTIONS = set(OPERATIONS)
METADATA_ACTIONS = {
    "inspect_upgrade_source",
    "issue_relational_upgrade",
    "relational_upgrade_checkpoint",
}
COMMON = {
    "installation_id",
    "actor_token",
    "source_action_id",
    "expected_source_revision",
    "expected_grant_record_revision",
}


def _common(value):
    if (
        type(value["installation_id"]) is not int
        or value["installation_id"] < 1
        or type(value["actor_token"]) is not str
        or not 1 <= len(value["actor_token"]) <= 4096
        or any(
            type(value[name]) is not str
            or not re.fullmatch(r"[0-9a-f]{32}", value[name])
            for name in COMMON - {"installation_id", "actor_token"}
        )
    ):
        raise ValueError("Invalid local upgrade identity")


def upgrade_request(value):
    operation = value.get("action") if type(value) is dict else None
    if type(operation) is not str or operation not in ACTIONS:
        raise ValueError("Unsupported local upgrade action")
    _, consent = OPERATIONS[operation]
    if (
        set(value) != COMMON | {"action", "request_id", consent}
        or value[consent] is not True
        or type(value["request_id"]) is not str
        or not re.fullmatch(r"[0-9a-f]{32}", value["request_id"])
    ):
        raise ValueError("Invalid local upgrade request")
    _common(value)
    return value


def upgrade_metadata(manager, value):
    if (
        type(value) is not dict
        or type(value.get("action")) is not str
        or value["action"] not in METADATA_ACTIONS
    ):
        raise ValueError("Unsupported local upgrade metadata action")
    from backend.services import application_relational_upgrade as upgrade
    from backend.services import (
        application_relational_upgrade_confirmation as published,
    )
    from backend.services import application_relational_upgrade_rollback as rollback
    from backend.services.application_relational_upgrade_admin import (
        inspect_upgrade_source,
    )

    operation = value["action"]
    fields = COMMON | {"action", "kind"}
    if operation == "issue_relational_upgrade":
        fields |= {"request_id", "transport_secret"}
    elif operation == "relational_upgrade_checkpoint":
        fields |= {"ticket", "phase", "receipt", "transport_secret"}
    if (
        set(value) != fields
        or type(value["kind"]) is not str
        or value["kind"] not in {"upgrade", "published", "rollback", "restore"}
    ):
        raise ValueError("Invalid local upgrade metadata")
    _common(value)
    if operation == "inspect_upgrade_source":
        return inspect_upgrade_source(
            manager,
            value["installation_id"],
            **{name: value[name] for name in COMMON - {"installation_id"}},
            include_configuration=True,
        )
    secret = value["transport_secret"]
    if type(secret) is not str or not re.fullmatch(r"[0-9a-f]{64}", secret):
        raise ValueError("Invalid local signing dependency")
    secret = bytes.fromhex(secret)
    arguments = {"actor_token": value["actor_token"], "transport_secret": secret}
    kind = value["kind"]
    if operation == "issue_relational_upgrade":
        arguments.update(
            request_id=value["request_id"],
            expected_source_revision=value["expected_source_revision"],
            expected_grant_record_revision=value["expected_grant_record_revision"],
        )
        if kind == "upgrade":
            return upgrade.issue_prepared_database_upgrade(
                manager,
                value["installation_id"],
                source_preparation_id=value["source_action_id"],
                confirm_owned_forward_upgrade=True,
                **arguments,
            )
        arguments["source_upgrade_id"] = value["source_action_id"]
        if kind == "published":
            return published.issue_published_upgrade_confirmation(
                manager,
                value["installation_id"],
                confirm_published_upgrade_reviewed=True,
                **arguments,
            )
        return rollback.issue_restored_upgrade_confirmation(
            manager,
            value["installation_id"],
            confirm_restored_state_reviewed=True,
            confirm_finish_interrupted_restore=kind == "restore",
            **arguments,
        )
    ticket, _ = decode_ticket(kind, value["ticket"])
    source_field = "source_preparation_id" if kind == "upgrade" else "source_upgrade_id"
    if (
        ticket[source_field] != value["source_action_id"]
        or ticket["grant_record_revision"] != value["expected_grant_record_revision"]
    ):
        raise ValueError("Upgrade checkpoint frame changed")
    callback = (
        upgrade.upgrade_checkpoint
        if kind == "upgrade"
        else (
            published.upgrade_confirmation_checkpoint
            if kind == "published"
            else rollback.rollback_confirmation_checkpoint
        )
    )
    return callback(
        manager,
        value["installation_id"],
        ticket,
        value["phase"],
        receipt=value["receipt"],
        **arguments,
    )


def decode_ticket(kind, value):
    if kind in {"rollback", "restore"}:
        ticket, purpose = _rollback_ticket(value)
        if (kind == "restore") != (
            ticket["action"] == "finish_interrupted_upgrade_restore"
        ):
            raise ValueError("Upgrade consent kind changed")
        return ticket, purpose
    model, purpose = (
        (_RelationalUpgradeTicket, "database_upgrade")
        if kind == "upgrade"
        else (_RelationalUpgradeConfirmationTicket, "database_upgrade_confirmation")
    )
    return model.model_validate(value).model_dump(mode="json"), purpose


def installed_upgrade(
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
    value = upgrade_request(value)
    if os.name != "posix" or os.geteuid() != 0:
        raise ValueError("Root upgrade helper required")
    kind, _ = OPERATIONS[value["action"]]
    common = {name: value[name] for name in COMMON}
    snapshot = metadata.call(dict(common, action="inspect_upgrade_source", kind=kind))
    if (
        type(snapshot) is not dict
        or set(snapshot)
        != {
            "sha256",
            "instance_id",
            "configuration",
            "source_ticket",
            "source_revision",
            "state",
        }
        or type(snapshot["sha256"]) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", snapshot["sha256"])
        or type(snapshot["instance_id"]) is not str
        or not re.fullmatch(r"[0-9a-f]{24}", snapshot["instance_id"])
        or type(snapshot["configuration"]) is not dict
        or snapshot["source_revision"] != value["expected_source_revision"]
    ):
        raise ValueError("Installed upgrade source unavailable")
    root, key_root, state_root = _roots((root, key_root, state_root), coordinator_uid)
    secret = _key(key_root / (snapshot["instance_id"] + ".key"))
    ticket, purpose = decode_ticket(
        kind,
        metadata.call(
            dict(
                common,
                action="issue_relational_upgrade",
                kind=kind,
                request_id=value["request_id"],
                transport_secret=secret.hex(),
            )
        ),
    )
    verify_metadata(secret, purpose, ticket)
    if (
        ticket["preparation_id"] != value["request_id"]
        or ticket["instance_id"] != snapshot["instance_id"]
        or ticket["package_sha256"] != snapshot["sha256"]
        or ticket["grant_record_revision"] != value["expected_grant_record_revision"]
    ):
        raise ValueError("Upgrade issuance identity changed")

    def checkpoint(current, phase, *, receipt=None):
        return metadata.call(
            dict(
                common,
                action="relational_upgrade_checkpoint",
                kind=kind,
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
    from three_mm_runtime.application_relational_upgrade import (
        upgrade_prepared_relational_database,
    )
    from three_mm_runtime.application_relational_upgrade_confirmation import (
        confirm_published_relational_upgrade,
    )
    from three_mm_runtime.application_relational_upgrade_rollback import (
        confirm_restored_relational_upgrade,
    )

    if kind == "upgrade":
        return upgrade_prepared_relational_database(
            upload_root / (ticket["source_package_sha256"] + ".zip"),
            upload_root / (ticket["package_sha256"] + ".zip"),
            ticket,
            **arguments,
        )
    source = _RelationalUpgradeTicket.model_validate(
        snapshot["source_ticket"]
    ).model_dump(mode="json")
    verify_metadata(secret, "database_upgrade", source)
    if ticket["source_ticket_sha256"] != hashlib.sha256(canonical(source)).hexdigest():
        raise ValueError("Upgrade source ticket changed")
    execute = (
        confirm_published_relational_upgrade
        if kind == "published"
        else confirm_restored_relational_upgrade
    )
    return execute(
        upload_root / (source["source_package_sha256"] + ".zip"),
        upload_root / (ticket["package_sha256"] + ".zip"),
        ticket,
        source,
        **arguments,
    )


def response_model(action):
    return (
        _RelationalUpgradeRollbackResult
        if OPERATIONS[action][0] in {"rollback", "restore"}
        else _RelationalUpgradeResult
    )


def response_status(action):
    return (
        "restored_not_started"
        if OPERATIONS[action][0] in {"rollback", "restore"}
        else "upgraded_not_started"
    )
