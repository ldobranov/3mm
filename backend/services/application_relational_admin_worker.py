"""Fixed Core-UID metadata worker for the privileged helper's private stdin.

No listener, package imports, runtime filesystem changes or grant approval.
Prepared activation has a separate fixed dialect. Each call closes its Core
leases before the helper performs effects.
Tokens and transport secrets are never argv, environment overrides or output.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from backend.services import application_authority_management as authority
from backend.services import application_relational_activation as activation
from backend.services import application_relational_activation_recovery as recovery
from backend.services import application_relational_boot as boot
from backend.services import application_relational_lifecycle as lifecycle
from backend.services import application_relational_reactivation as reactivation
from backend.services.application_authority_sources import _configuration
from backend.services.application_policy_reviews import _actor
from backend.services.authority_metadata import authority_transaction
from three_mm_application_sdk.relational_wire import canonical
from three_mm_runtime.application_relational_preparation_recovery_control import (
    METADATA_ACTIONS as PREPARATION_RECOVERY_OPERATIONS,
)
from three_mm_runtime.application_relational_upgrade_control import (
    METADATA_ACTIONS as UPGRADE_OPERATIONS,
)

MAX_FRAME = 64 * 1024
RECOVERY_OPERATIONS = {
    "inspect_activation_recovery",
    "issue_activation_recovery",
    "activation_recovery_checkpoint",
}
REACTIVATION_OPERATIONS = {
    "inspect_reactivation",
    "issue_reactivation",
    "reactivation_checkpoint",
}
BOOT_OPERATIONS = {"inspect_boot_enable", "issue_boot_enable", "boot_enable_checkpoint"}


def _fields(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise ValueError("Invalid local metadata frame")


def dispatch(manager, value, *, application_root=None):
    """Only Root's fixed metadata dialect, never a generic function/method RPC."""
    if (
        type(value) is dict
        and type(value.get("action")) is str
        and value["action"] in UPGRADE_OPERATIONS
    ):
        from three_mm_runtime.application_relational_upgrade_control import (
            upgrade_metadata,
        )

        return upgrade_metadata(manager, value)
    if (
        type(value) is dict
        and type(value.get("action")) is str
        and value["action"] in PREPARATION_RECOVERY_OPERATIONS
    ):
        from three_mm_runtime.application_relational_preparation_recovery_control import (
            preparation_recovery_metadata,
        )

        return preparation_recovery_metadata(manager, value)
    if (
        type(value) is dict
        and type(value.get("action")) is str
        and value["action"] in BOOT_OPERATIONS
    ):
        return _dispatch_boot(manager, value, application_root)
    if (
        type(value) is dict
        and type(value.get("action")) is str
        and value["action"] in REACTIVATION_OPERATIONS
    ):
        return _dispatch_reactivation(manager, value, application_root)
    if (
        type(value) is dict
        and type(value.get("action")) is str
        and value["action"] in RECOVERY_OPERATIONS
    ):
        return _dispatch_recovery(manager, value)
    common = {
        "action",
        "installation_id",
        "actor_token",
        "expected_grant_record_revision",
    }
    if type(value) is not dict or not common <= set(value):
        raise ValueError("Invalid local metadata frame")
    identifier = value["installation_id"]
    if type(identifier) is not int or identifier < 1:
        raise ValueError("Invalid installation")
    expected = authority._identifier(value["expected_grant_record_revision"])
    token = value["actor_token"]
    if type(token) is not str or not 1 <= len(token) <= 4096:
        raise ValueError("Invalid local actor")
    operation = value["action"]
    if type(operation) is not str:
        raise ValueError("Invalid local metadata operation")
    if operation in {"inspect", "inspect_activation"}:
        _fields(value, common)
        prepared = manager._prepare(identifier)
        with (
            manager.keys.locked() as key,
            Session(manager.engine) as db,
            authority_transaction(db),
        ):
            _actor(db, token)
            grant, definition = lifecycle._current(
                manager, db, key, identifier, prepared
            )
            if grant["revision"] != expected:
                raise authority.AuthorityManagementError("preparation_changed")
            result = {
                "sha256": prepared[0].sha256,
                "configuration": _configuration(db, identifier, prepared[1]),
            }
            if operation == "inspect_activation":
                from three_mm_runtime.application_activation import (
                    application_instance_id,
                )

                result["instance_id"] = application_instance_id(definition.module_id)
            return result
    secret = value.get("transport_secret")
    if type(secret) is not str or not re.fullmatch(r"[0-9a-f]{64}", secret):
        raise ValueError("Invalid private signing dependency")
    secret = bytes.fromhex(secret)
    if operation in {"issue_namespace", "issue_migration", "issue_activation"}:
        names = common | {"transport_secret", "request_id"}
        if operation in {"issue_namespace", "issue_activation"}:
            names |= {"service_uid", "service_gid", "coordinator_uid"}
        if operation == "issue_activation":
            names.add("source_preparation_id")
        _fields(value, names)
        arguments = dict(
            actor_token=token,
            request_id=value["request_id"],
            expected_grant_record_revision=expected,
            transport_secret=secret,
        )
        if operation == "issue_activation":
            return activation.issue_prepared_activation(
                manager,
                identifier,
                source_preparation_id=value["source_preparation_id"],
                confirm_start_prepared_service=True,
                **{
                    name: value[name]
                    for name in ("service_uid", "service_gid", "coordinator_uid")
                },
                **arguments,
            )
        if operation == "issue_namespace":
            return lifecycle.issue_namespace_preparation(
                manager,
                identifier,
                confirm_fresh_owned_namespace=True,
                **{
                    name: value[name]
                    for name in ("service_uid", "service_gid", "coordinator_uid")
                },
                **arguments,
            )
        return lifecycle.issue_migrated_schema_preparation(
            manager, identifier, confirm_owned_business_migrations=True, **arguments
        )
    if operation in {"checkpoint", "activation_checkpoint"}:
        _fields(value, common | {"transport_secret", "ticket", "phase", "receipt"})
        if type(value["ticket"]) is not dict:
            raise ValueError("Invalid local metadata ticket")
        if value["ticket"].get("grant_record_revision") != expected:
            raise authority.AuthorityManagementError("preparation_changed")
        if operation == "activation_checkpoint":
            from three_mm_application_sdk.relational_wire import (
                _RelationalActivationTicket,
            )

            ticket = _RelationalActivationTicket.model_validate(
                value["ticket"]
            ).model_dump(mode="json")
            if application_root is None or not Path(application_root).is_absolute():
                raise ValueError("Trusted installed application root required")
            return activation.activation_checkpoint(
                manager,
                identifier,
                ticket,
                value["phase"],
                actor_token=token,
                transport_secret=secret,
                runtime_root=application_root,
                receipt=value["receipt"],
            )
        return lifecycle.preparation_checkpoint(
            manager,
            identifier,
            value["ticket"],
            value["phase"],
            actor_token=token,
            transport_secret=secret,
            receipt=value["receipt"],
        )
    raise ValueError("Unsupported local metadata operation")


def _dispatch_recovery(manager, value):
    common = {
        "action",
        "installation_id",
        "actor_token",
        "source_activation_id",
        "expected_activation_revision",
    }
    operation = value["action"]
    names = common
    if operation == "issue_activation_recovery":
        names |= {
            "transport_secret",
            "request_id",
            "service_uid",
            "service_gid",
            "coordinator_uid",
        }
    elif operation == "activation_recovery_checkpoint":
        names |= {"transport_secret", "ticket", "phase", "receipt"}
    _fields(value, names)
    identifier, token = value["installation_id"], value["actor_token"]
    if (
        type(identifier) is not int
        or identifier < 1
        or type(token) is not str
        or not 1 <= len(token) <= 4096
    ):
        raise ValueError("Invalid recovery actor/installation")
    source = authority._identifier(value["source_activation_id"])
    expected = authority._identifier(value["expected_activation_revision"])
    if operation == "inspect_activation_recovery":
        return recovery.inspect_activation_recovery_source(
            manager,
            identifier,
            actor_token=token,
            source_activation_id=source,
            expected_activation_revision=expected,
            include_configuration=True,
        )
    secret = value["transport_secret"]
    if type(secret) is not str or not re.fullmatch(r"[0-9a-f]{64}", secret):
        raise ValueError("Invalid recovery signing dependency")
    secret = bytes.fromhex(secret)
    if operation == "issue_activation_recovery":
        return recovery.issue_activation_recovery(
            manager,
            identifier,
            actor_token=token,
            request_id=value["request_id"],
            source_activation_id=source,
            expected_activation_revision=expected,
            confirm_stop_preserve_prepared_state=True,
            transport_secret=secret,
            **{
                name: value[name]
                for name in ("service_uid", "service_gid", "coordinator_uid")
            },
        )
    from three_mm_application_sdk.relational_wire import _activation_recovery_ticket

    ticket, _ = _activation_recovery_ticket(value["ticket"])
    if (
        ticket["source_activation_id"] != source
        or ticket["source_activation_revision"] != expected
    ):
        raise authority.AuthorityManagementError("activation_recovery_frame_changed")
    return recovery.activation_recovery_checkpoint(
        manager,
        identifier,
        ticket,
        value["phase"],
        actor_token=token,
        transport_secret=secret,
        receipt=value["receipt"],
    )


def _dispatch_reactivation(manager, value, application_root):
    common = {
        "action",
        "installation_id",
        "actor_token",
        "source_recovery_id",
        "expected_recovery_revision",
        "expected_grant_record_revision",
    }
    operation = value["action"]
    names = common
    if operation == "issue_reactivation":
        names |= {
            "transport_secret",
            "request_id",
            "service_uid",
            "service_gid",
            "coordinator_uid",
        }
    elif operation == "reactivation_checkpoint":
        names |= {"transport_secret", "ticket", "phase", "receipt"}
    _fields(value, names)
    identifier, token = value["installation_id"], value["actor_token"]
    if (
        type(identifier) is not int
        or identifier < 1
        or type(token) is not str
        or not 1 <= len(token) <= 4096
    ):
        raise ValueError("Invalid reactivation actor/installation")
    source = authority._identifier(value["source_recovery_id"])
    expected = authority._identifier(value["expected_recovery_revision"])
    grant = authority._identifier(value["expected_grant_record_revision"])
    common_arguments = dict(
        actor_token=token,
        source_recovery_id=source,
        expected_recovery_revision=expected,
        expected_grant_record_revision=grant,
    )
    if operation == "inspect_reactivation":
        return reactivation.inspect_reactivation_source(
            manager,
            identifier,
            **common_arguments,
            include_configuration=True,
        )
    secret = value["transport_secret"]
    if type(secret) is not str or not re.fullmatch(r"[0-9a-f]{64}", secret):
        raise ValueError("Invalid reactivation signing dependency")
    secret = bytes.fromhex(secret)
    if operation == "issue_reactivation":
        return reactivation.issue_prepared_reactivation(
            manager,
            identifier,
            **common_arguments,
            request_id=value["request_id"],
            confirm_restart_stopped_prepared_service=True,
            transport_secret=secret,
            **{
                name: value[name]
                for name in ("service_uid", "service_gid", "coordinator_uid")
            },
        )
    from three_mm_application_sdk.relational_wire import _RelationalReactivationTicket

    ticket = _RelationalReactivationTicket.model_validate(value["ticket"]).model_dump(
        mode="json"
    )
    if (
        ticket["source_recovery_id"] != source
        or ticket["source_recovery_revision"] != expected
        or ticket["grant_record_revision"] != grant
        or application_root is None
        or not Path(application_root).is_absolute()
    ):
        raise authority.AuthorityManagementError("reactivation_frame_changed")
    return activation.activation_checkpoint(
        manager,
        identifier,
        ticket,
        value["phase"],
        actor_token=token,
        transport_secret=secret,
        runtime_root=application_root,
        receipt=value["receipt"],
    )


def _dispatch_boot(manager, value, application_root):
    common = {
        "action",
        "installation_id",
        "actor_token",
        "source_activation_id",
        "expected_activation_revision",
        "expected_grant_record_revision",
    }
    operation = value["action"]
    names = common
    if operation == "issue_boot_enable":
        names |= {
            "transport_secret",
            "request_id",
            "service_uid",
            "service_gid",
            "coordinator_uid",
        }
    elif operation == "boot_enable_checkpoint":
        names |= {"transport_secret", "ticket", "phase", "receipt"}
    _fields(value, names)
    identifier, token = value["installation_id"], value["actor_token"]
    if (
        type(identifier) is not int
        or identifier < 1
        or type(token) is not str
        or not 1 <= len(token) <= 4096
        or application_root is None
        or not Path(application_root).is_absolute()
    ):
        raise ValueError("Invalid boot actor/installation/layout")
    source = authority._identifier(value["source_activation_id"])
    expected = authority._identifier(value["expected_activation_revision"])
    grant = authority._identifier(value["expected_grant_record_revision"])
    arguments = dict(
        actor_token=token,
        source_activation_id=source,
        expected_activation_revision=expected,
        expected_grant_record_revision=grant,
        runtime_root=application_root,
    )
    if operation == "inspect_boot_enable":
        return boot.inspect_boot_enable_source(manager, identifier, **arguments)
    secret = value["transport_secret"]
    if type(secret) is not str or not re.fullmatch(r"[0-9a-f]{64}", secret):
        raise ValueError("Invalid boot signing dependency")
    secret = bytes.fromhex(secret)
    if operation == "issue_boot_enable":
        return boot.issue_boot_enable(
            manager,
            identifier,
            **arguments,
            request_id=value["request_id"],
            confirm_enable_prepared_boot=True,
            transport_secret=secret,
            **{
                name: value[name]
                for name in ("service_uid", "service_gid", "coordinator_uid")
            },
        )
    from three_mm_application_sdk.relational_wire import _RelationalBootEnableTicket

    ticket = _RelationalBootEnableTicket.model_validate(value["ticket"]).model_dump(
        mode="json"
    )
    if (
        ticket["source_activation_id"] != source
        or ticket["source_activation_revision"] != expected
        or ticket["grant_record_revision"] != grant
    ):
        raise authority.AuthorityManagementError("boot_enable_frame_changed")
    return boot.boot_enable_checkpoint(
        manager,
        identifier,
        ticket,
        value["phase"],
        actor_token=token,
        transport_secret=secret,
        runtime_root=application_root,
        receipt=value["receipt"],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-uid", required=True, type=int)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--application-root", type=Path)
    args = parser.parse_args()
    try:
        if (
            os.name != "posix"
            or args.core_uid <= 0
            or os.getuid() != args.core_uid
            or os.geteuid() != args.core_uid
        ):
            raise ValueError("Core service principal required")
        from sqlalchemy.engine import make_url

        from backend.config import get_settings

        url = make_url(get_settings().database_url)
        if (
            url.drivername != "sqlite"
            or url.query
            or not url.database
            or not args.database.is_file()
            or Path(url.database).resolve() != args.database.resolve()
        ):
            raise ValueError("Installed Core database required")
        data = sys.stdin.buffer.readline(MAX_FRAME + 1)
        if len(data) > MAX_FRAME or not data.endswith(b"\n"):
            raise ValueError("Local metadata frame exceeds budget")
        from backend.services.application_authority_context import _unique_object

        value = json.loads(data, object_pairs_hook=_unique_object)
        if (
            type(value) is dict
            and type(value.get("action")) is str
            and value.get("action")
            in {
                "inspect_activation",
                "issue_activation",
                "activation_checkpoint",
            }
            | RECOVERY_OPERATIONS
            | REACTIVATION_OPERATIONS
            | BOOT_OPERATIONS
            | PREPARATION_RECOVERY_OPERATIONS
            | UPGRADE_OPERATIONS
        ):
            # Root supplies this fixed dependency through protected worker argv,
            # never a JSON field. Refuse Core/helper layout divergence before
            # engine import or any authority write.
            if (
                args.application_root is None
                or not args.application_root.is_absolute()
                or args.application_root.resolve()
                != get_settings().applications.root.resolve()
            ):
                raise ValueError("Installed application layout changed")
        from backend.database import engine

        result = dispatch(
            authority.configured_manager(engine),
            value,
            application_root=args.application_root,
        )
        encoded = canonical({"ok": True, "result": result})
        if len(encoded) > MAX_FRAME:
            raise ValueError("Local metadata response exceeds budget")
        sys.stdout.buffer.write(encoded + b"\n")
    except Exception:
        # No traceback/payload: errors may involve live tokens/signing material.
        sys.stdout.buffer.write(b'{"ok":false,"error":"local_authority_unavailable"}\n')
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
