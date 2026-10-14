"""Narrow installed preparation/activation through the existing local helper.

Core authority stays in a fixed non-root metadata worker. Root supplies paths,
UIDs and fresh keys. No remote endpoint, automatic enable, package-selected
paths, permissions, worker commands or fallback to generic activation.
"""

import json
import os
import re
import subprocess
from pathlib import Path

from three_mm_application_sdk.relational_wire import canonical
from three_mm_runtime.application_relational_installation import (
    prepare_fresh_relational_installation,
)

MAX_FRAME = 64 * 1024


def boot_enable_request(value):
    names = {
        "action",
        "installation_id",
        "actor_token",
        "source_activation_id",
        "expected_activation_revision",
        "expected_grant_record_revision",
        "request_id",
        "confirm_enable_prepared_boot",
    }
    if (
        type(value) is not dict
        or set(value) != names
        or value["action"] != "enable_application_relational_boot"
        or type(value["installation_id"]) is not int
        or value["installation_id"] < 1
        or type(value["actor_token"]) is not str
        or not 1 <= len(value["actor_token"]) <= 4096
        or value["confirm_enable_prepared_boot"] is not True
        or any(
            type(value[name]) is not str
            or not re.fullmatch(r"[0-9a-f]{32}", value[name])
            for name in (
                "source_activation_id",
                "expected_activation_revision",
                "expected_grant_record_revision",
                "request_id",
            )
        )
    ):
        raise ValueError("Invalid relational boot enable request")
    return value


def reactivation_request(value):
    names = {
        "action",
        "installation_id",
        "actor_token",
        "source_recovery_id",
        "expected_recovery_revision",
        "expected_grant_record_revision",
        "request_id",
        "confirm_restart_stopped_prepared_service",
    }
    if (
        type(value) is not dict
        or set(value) != names
        or value["action"] != "reactivate_application_relational"
        or type(value["installation_id"]) is not int
        or value["installation_id"] < 1
        or type(value["actor_token"]) is not str
        or not 1 <= len(value["actor_token"]) <= 4096
        or value["confirm_restart_stopped_prepared_service"] is not True
        or any(
            type(value[name]) is not str
            or not re.fullmatch(r"[0-9a-f]{32}", value[name])
            for name in (
                "source_recovery_id",
                "expected_recovery_revision",
                "expected_grant_record_revision",
                "request_id",
            )
        )
    ):
        raise ValueError("Invalid relational reactivation request")
    return value


def activation_recovery_request(value):
    names = {
        "action",
        "installation_id",
        "actor_token",
        "source_activation_id",
        "expected_activation_revision",
        "request_id",
        "confirm_stop_preserve_prepared_state",
    }
    if (
        type(value) is not dict
        or set(value) != names
        or value["action"] != "recover_application_relational_start"
        or type(value["installation_id"]) is not int
        or value["installation_id"] < 1
        or type(value["actor_token"]) is not str
        or not 1 <= len(value["actor_token"]) <= 4096
        or value["confirm_stop_preserve_prepared_state"] is not True
        or any(
            type(value[name]) is not str
            or not re.fullmatch(r"[0-9a-f]{32}", value[name])
            for name in (
                "source_activation_id",
                "expected_activation_revision",
                "request_id",
            )
        )
    ):
        raise ValueError("Invalid relational start recovery request")
    return value


def activation_request(value):
    names = {
        "action",
        "installation_id",
        "actor_token",
        "expected_grant_record_revision",
        "source_preparation_id",
        "request_id",
        "confirm_start_prepared_service",
    }
    if (
        type(value) is not dict
        or set(value) != names
        or value["action"] != "activate_application_relational"
        or type(value["installation_id"]) is not int
        or value["installation_id"] < 1
        or type(value["actor_token"]) is not str
        or not 1 <= len(value["actor_token"]) <= 4096
        or value["confirm_start_prepared_service"] is not True
        or any(
            type(value[name]) is not str
            or not re.fullmatch(r"[0-9a-f]{32}", value[name])
            for name in (
                "expected_grant_record_revision",
                "source_preparation_id",
                "request_id",
            )
        )
    ):
        raise ValueError("Invalid relational activation request")
    return value


def preparation_request(value):
    names = {
        "action",
        "installation_id",
        "actor_token",
        "expected_grant_record_revision",
        "confirm_fresh_owned_namespace",
        "confirm_owned_business_migrations",
    }
    if (
        type(value) is not dict
        or set(value) != names
        or value["action"] != "prepare_application_relational"
        or type(value["installation_id"]) is not int
        or value["installation_id"] < 1
        or type(value["actor_token"]) is not str
        or not 1 <= len(value["actor_token"]) <= 4096
        or type(value["expected_grant_record_revision"]) is not str
        or not re.fullmatch(r"[0-9a-f]{32}", value["expected_grant_record_revision"])
        or value["confirm_fresh_owned_namespace"] is not True
        or value["confirm_owned_business_migrations"] is not True
    ):
        raise ValueError("Invalid relational preparation request")
    return value


class CoreMetadataClient:
    """Fixed systemd worker with private pipes; no user token/key in process argv."""

    def __init__(
        self,
        *,
        core_uid,
        core_user="3mm",
        core_group="3mm",
        database,
        application_root=Path("/var/lib/3mm/application-extensions"),
        python="/opt/3mm/current/.venv/bin/python",
        working_directory="/opt/3mm/current",
        environment_file="/etc/3mm/3mm.env",
        runner=None,
    ):
        self.core_uid, self.database = core_uid, database
        self._run = runner or subprocess.run
        self.arguments = (
            "/usr/bin/systemd-run",
            "--quiet",
            "--pipe",
            "--wait",
            "--collect",
            "--property=Type=exec",
            "--property=RuntimeMaxSec=15s",
            "--property=TimeoutStopSec=5s",
            "--property=KillMode=control-group",
            "--property=User=" + core_user,
            "--property=Group=" + core_group,
            "--property=EnvironmentFile=" + environment_file,
            "--property=WorkingDirectory=" + working_directory,
            "--property=NoNewPrivileges=yes",
            "--property=ProtectSystem=strict",
            "--property=ProtectHome=yes",
            "--property=PrivateTmp=yes",
            "--property=ReadWritePaths=" + str(database.parent),
            "/usr/bin/env",
            "PYTHONPATH=" + working_directory,
            python,
            "-m",
            "backend.services.application_relational_admin_worker",
            "--core-uid",
            str(core_uid),
            "--database",
            str(database),
            "--application-root",
            str(application_root),
        )

    def call(self, value):
        data = canonical(value) + b"\n"
        if len(data) > MAX_FRAME:
            raise ValueError("Local metadata budget exceeded")
        # The fixed worker bounds output, runtime and Core principal. Never use
        # a shell, retry a consumed phase or expose captured errors to the caller.
        process = self._run(
            self.arguments, input=data, capture_output=True, timeout=25, check=False
        )
        if process.returncode != 0 or len(process.stdout) > MAX_FRAME:
            raise ValueError("Core metadata outcome unavailable")
        from backend.services.application_authority_context import _unique_object

        result = json.loads(process.stdout, object_pairs_hook=_unique_object)
        if (
            type(result) is not dict
            or set(result) != {"ok", "result"}
            or result["ok"] is not True
            or type(result["result"]) is not dict
        ):
            raise ValueError("Core metadata outcome unavailable")
        return result["result"]


def prepare_installed_application(
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
    value = preparation_request(value)
    if os.name != "posix" or os.geteuid() != 0:
        raise ValueError("Root preparation helper required")
    common = {
        name: value[name]
        for name in ("installation_id", "actor_token", "expected_grant_record_revision")
    }
    snapshot = metadata.call(dict(common, action="inspect"))
    if (
        set(snapshot) != {"sha256", "configuration"}
        or type(snapshot["sha256"]) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", snapshot["sha256"])
        or type(snapshot["configuration"]) is not dict
    ):
        raise ValueError("Installed preparation source unavailable")

    def issue(action, *, transport_secret, request_id):
        fields = dict(
            common,
            action=action,
            transport_secret=transport_secret.hex(),
            request_id=request_id,
        )
        if action == "issue_namespace":
            fields.update(
                service_uid=service_uid,
                service_gid=service_gid,
                coordinator_uid=coordinator_uid,
            )
        return metadata.call(fields)

    def checkpoint(ticket, phase, *, transport_secret, receipt=None):
        return metadata.call(
            dict(
                common,
                action="checkpoint",
                ticket=ticket,
                phase=phase,
                transport_secret=transport_secret.hex(),
                receipt=receipt,
            )
        )

    return prepare_fresh_relational_installation(
        upload_root / (snapshot["sha256"] + ".zip"),
        configuration=snapshot["configuration"],
        root=root,
        key_root=key_root,
        state_root=state_root,
        service_uid=service_uid,
        service_gid=service_gid,
        coordinator_uid=coordinator_uid,
        confirm_fresh_owned_namespace=value["confirm_fresh_owned_namespace"],
        confirm_owned_business_migrations=value["confirm_owned_business_migrations"],
        issue_namespace=lambda **kw: issue("issue_namespace", **kw),
        issue_migration=lambda **kw: issue("issue_migration", **kw),
        checkpoint=checkpoint,
        supervisor=supervisor,
    )


def activate_installed_application(
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
    """Only an exact prepared source; no caller paths/config/key/UID or retry.

    Root reads the existing key only after a current Core/human/grant snapshot.
    Actual preparation/lifecycle verification and start stay in the existing
    serialized coordinator; no new secret/lineage/migration or boot enable.
    """
    from three_mm_runtime.application_relational_activation import (
        activate_prepared_relational_service,
    )
    from three_mm_runtime.application_relational_namespace import _roots
    from three_mm_runtime.application_relational_preparation import _key

    value = activation_request(value)
    if os.name != "posix" or os.geteuid() != 0:
        raise ValueError("Root activation helper required")
    common = {
        name: value[name]
        for name in ("installation_id", "actor_token", "expected_grant_record_revision")
    }
    snapshot = metadata.call(dict(common, action="inspect_activation"))
    if (
        type(snapshot) is not dict
        or set(snapshot) != {"sha256", "configuration", "instance_id"}
        or type(snapshot["sha256"]) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", snapshot["sha256"])
        or type(snapshot["instance_id"]) is not str
        or not re.fullmatch(r"[0-9a-f]{24}", snapshot["instance_id"])
        or type(snapshot["configuration"]) is not dict
    ):
        raise ValueError("Installed activation source unavailable")
    root, key_root, state_root = _roots((root, key_root, state_root), coordinator_uid)
    secret = _key(key_root / (snapshot["instance_id"] + ".key"))
    ticket = metadata.call(
        dict(
            common,
            action="issue_activation",
            request_id=value["request_id"],
            source_preparation_id=value["source_preparation_id"],
            transport_secret=secret.hex(),
            service_uid=service_uid,
            service_gid=service_gid,
            coordinator_uid=coordinator_uid,
        )
    )

    def checkpoint(current, phase, *, receipt=None):
        return metadata.call(
            dict(
                common,
                action="activation_checkpoint",
                ticket=current,
                phase=phase,
                receipt=receipt,
                transport_secret=secret.hex(),
            )
        )

    return activate_prepared_relational_service(
        upload_root / (snapshot["sha256"] + ".zip"),
        ticket,
        configuration=snapshot["configuration"],
        root=root,
        key_root=key_root,
        state_root=state_root,
        service_uid=service_uid,
        service_gid=service_gid,
        coordinator_uid=coordinator_uid,
        checkpoint=checkpoint,
        supervisor=supervisor,
    )


def enable_installed_application_boot(
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
    """Explicit enable-only wiring; existing current/Root pre-import gates stay.

    Caller CAS is for issue only. Checkpoints use the newly reserved source
    revision; unknown phases/replies are never replayed or silently refreshed.
    """
    from three_mm_application_sdk.relational_wire import _RelationalBootEnableTicket
    from three_mm_runtime.application_relational_boot import (
        enable_prepared_relational_boot,
    )
    from three_mm_runtime.application_relational_namespace import _roots
    from three_mm_runtime.application_relational_preparation import _key

    value = boot_enable_request(value)
    if os.name != "posix" or os.geteuid() != 0:
        raise ValueError("Root boot enable helper required")
    common = {
        name: value[name]
        for name in (
            "installation_id",
            "actor_token",
            "source_activation_id",
            "expected_activation_revision",
            "expected_grant_record_revision",
        )
    }
    snapshot = metadata.call(dict(common, action="inspect_boot_enable"))
    if (
        type(snapshot) is not dict
        or set(snapshot)
        != {"sha256", "instance_id", "configuration", "source_revision"}
        or type(snapshot["sha256"]) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", snapshot["sha256"])
        or type(snapshot["instance_id"]) is not str
        or not re.fullmatch(r"[0-9a-f]{24}", snapshot["instance_id"])
        or type(snapshot["configuration"]) is not dict
        or snapshot["source_revision"] != value["expected_activation_revision"]
    ):
        raise ValueError("Installed boot enable source unavailable")
    root, key_root, state_root = _roots((root, key_root, state_root), coordinator_uid)
    secret = _key(key_root / (snapshot["instance_id"] + ".key"))
    ticket = _RelationalBootEnableTicket.model_validate(
        metadata.call(
            dict(
                common,
                action="issue_boot_enable",
                request_id=value["request_id"],
                transport_secret=secret.hex(),
                service_uid=service_uid,
                service_gid=service_gid,
                coordinator_uid=coordinator_uid,
            )
        )
    ).model_dump(mode="json")
    if (
        ticket["preparation_id"] != value["request_id"]
        or ticket["source_activation_id"] != value["source_activation_id"]
        or ticket["grant_record_revision"] != value["expected_grant_record_revision"]
        or ticket["instance_id"] != snapshot["instance_id"]
        or ticket["package_sha256"] != snapshot["sha256"]
    ):
        raise ValueError("Boot enable issuance identity changed")

    def checkpoint(current, phase, *, receipt=None):
        return metadata.call(
            dict(
                common,
                action="boot_enable_checkpoint",
                expected_activation_revision=ticket["source_activation_revision"],
                ticket=current,
                phase=phase,
                receipt=receipt,
                transport_secret=secret.hex(),
            )
        )

    return enable_prepared_relational_boot(
        upload_root / (snapshot["sha256"] + ".zip"),
        ticket,
        configuration=snapshot["configuration"],
        root=root,
        key_root=key_root,
        state_root=state_root,
        service_uid=service_uid,
        service_gid=service_gid,
        coordinator_uid=coordinator_uid,
        checkpoint=checkpoint,
        supervisor=supervisor,
    )


def recover_installed_application_start(
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
    """Fresh stop-only request; no keys/paths/grants selected by the caller."""
    from three_mm_application_sdk.relational_wire import (
        _activation_recovery_ticket,
    )
    from three_mm_runtime.application_relational_activation_recovery import (
        reconcile_interrupted_relational_start,
    )
    from three_mm_runtime.application_relational_namespace import _roots
    from three_mm_runtime.application_relational_preparation import _key

    value = activation_recovery_request(value)
    if os.name != "posix" or os.geteuid() != 0:
        raise ValueError("Root recovery helper required")
    common = {
        name: value[name]
        for name in (
            "installation_id",
            "actor_token",
            "source_activation_id",
            "expected_activation_revision",
        )
    }
    snapshot = metadata.call(dict(common, action="inspect_activation_recovery"))
    if (
        type(snapshot) is not dict
        or set(snapshot)
        != {"sha256", "instance_id", "configuration", "source_revision"}
        or type(snapshot["sha256"]) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", snapshot["sha256"])
        or type(snapshot["instance_id"]) is not str
        or not re.fullmatch(r"[0-9a-f]{24}", snapshot["instance_id"])
        or type(snapshot["configuration"]) is not dict
        or snapshot["source_revision"] != value["expected_activation_revision"]
    ):
        raise ValueError("Installed recovery source unavailable")
    root, key_root, state_root = _roots((root, key_root, state_root), coordinator_uid)
    secret = _key(key_root / (snapshot["instance_id"] + ".key"))
    ticket, _ = _activation_recovery_ticket(
        metadata.call(
            dict(
                common,
                action="issue_activation_recovery",
                request_id=value["request_id"],
                transport_secret=secret.hex(),
                service_uid=service_uid,
                service_gid=service_gid,
                coordinator_uid=coordinator_uid,
            )
        )
    )
    if (
        ticket["preparation_id"] != value["request_id"]
        or ticket["source_activation_id"] != value["source_activation_id"]
        or ticket["instance_id"] != snapshot["instance_id"]
        or ticket["package_sha256"] != snapshot["sha256"]
    ):
        raise ValueError("Recovery issuance identity changed")

    def checkpoint(current, phase, *, receipt=None):
        return metadata.call(
            dict(
                common,
                action="activation_recovery_checkpoint",
                # Issuance reserves the source and changes its sealed revision.
                # The original caller CAS is never re-used for later phases.
                expected_activation_revision=ticket["source_activation_revision"],
                ticket=current,
                phase=phase,
                receipt=receipt,
                transport_secret=secret.hex(),
            )
        )

    return reconcile_interrupted_relational_start(
        upload_root / (snapshot["sha256"] + ".zip"),
        ticket,
        configuration=snapshot["configuration"],
        root=root,
        key_root=key_root,
        state_root=state_root,
        service_uid=service_uid,
        service_gid=service_gid,
        coordinator_uid=coordinator_uid,
        checkpoint=checkpoint,
        supervisor=supervisor,
    )


def reactivate_installed_application(
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
    """Fresh start of exact confirmed stopped state, never automatic retry.

    Core authenticates the current human/grant/source CAS BEFORE existing key
    access. Reserved post-issue CAS is used only for this ticket's callbacks.
    """
    from three_mm_application_sdk.relational_wire import _RelationalReactivationTicket
    from three_mm_runtime.application_relational_activation import (
        activate_prepared_relational_service,
    )
    from three_mm_runtime.application_relational_namespace import _roots
    from three_mm_runtime.application_relational_preparation import _key

    value = reactivation_request(value)
    if os.name != "posix" or os.geteuid() != 0:
        raise ValueError("Root reactivation helper required")
    common = {
        name: value[name]
        for name in (
            "installation_id",
            "actor_token",
            "source_recovery_id",
            "expected_recovery_revision",
            "expected_grant_record_revision",
        )
    }
    snapshot = metadata.call(dict(common, action="inspect_reactivation"))
    if (
        type(snapshot) is not dict
        or set(snapshot)
        != {"sha256", "instance_id", "configuration", "source_revision"}
        or type(snapshot["sha256"]) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", snapshot["sha256"])
        or type(snapshot["instance_id"]) is not str
        or not re.fullmatch(r"[0-9a-f]{24}", snapshot["instance_id"])
        or type(snapshot["configuration"]) is not dict
        or snapshot["source_revision"] != value["expected_recovery_revision"]
    ):
        raise ValueError("Installed reactivation source unavailable")
    root, key_root, state_root = _roots((root, key_root, state_root), coordinator_uid)
    secret = _key(key_root / (snapshot["instance_id"] + ".key"))
    ticket = _RelationalReactivationTicket.model_validate(
        metadata.call(
            dict(
                common,
                action="issue_reactivation",
                request_id=value["request_id"],
                transport_secret=secret.hex(),
                service_uid=service_uid,
                service_gid=service_gid,
                coordinator_uid=coordinator_uid,
            )
        )
    ).model_dump(mode="json")
    if (
        ticket["preparation_id"] != value["request_id"]
        or ticket["source_recovery_id"] != value["source_recovery_id"]
        or ticket["grant_record_revision"] != value["expected_grant_record_revision"]
        or ticket["instance_id"] != snapshot["instance_id"]
        or ticket["package_sha256"] != snapshot["sha256"]
    ):
        raise ValueError("Reactivation issuance identity changed")

    def checkpoint(current, phase, *, receipt=None):
        return metadata.call(
            dict(
                common,
                action="reactivation_checkpoint",
                expected_recovery_revision=ticket["source_recovery_revision"],
                ticket=current,
                phase=phase,
                receipt=receipt,
                transport_secret=secret.hex(),
            )
        )

    return activate_prepared_relational_service(
        upload_root / (snapshot["sha256"] + ".zip"),
        ticket,
        configuration=snapshot["configuration"],
        root=root,
        key_root=key_root,
        state_root=state_root,
        service_uid=service_uid,
        service_gid=service_gid,
        coordinator_uid=coordinator_uid,
        checkpoint=checkpoint,
        supervisor=supervisor,
    )
