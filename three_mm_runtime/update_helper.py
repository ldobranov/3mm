"""Root-only immutable update scheduler exposed through a local Unix socket."""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, Sequence

from backend.services.update_staging import (
    UpdateOperationStatus,
    UpdateStagingError,
    validate_staged_payload,
    write_operation_status,
)
from backend.services.backups import build_backup_preview
from deployment.create_backup import production_settings
from deployment.portable_backup import (
    create_portable_export,
    import_portable_backup,
)
from three_mm_provisioning import (
    FileNetworkRecoveryMarker,
    FileNetworkRecoveryPolicyStore,
    FileProvisioningStore,
    NetworkManagerReadOnlyAdapter,
    ProvisioningState,
)
from three_mm_provisioning.network_recovery import RecoveryTrigger
from three_mm_runtime.network_recovery import NetworkRecoveryMonitor
from three_mm_runtime.application_activation import (
    activate_application_package,
    erase_application_instance_data,
    SystemdApplicationSupervisor,
    uninstall_application_instance,
)

MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_PORTABLE_ARCHIVE_BYTES = 512 * 1024 * 1024
LOGGER = logging.getLogger(__name__)


def _service_ids(user_name: str, group_name: str) -> tuple[int, int]:
    import grp
    import pwd

    return pwd.getpwnam(user_name).pw_uid, grp.getgrnam(group_name).gr_gid


class UpdateCommandRunner(Protocol):
    def run(self, arguments: Sequence[str]) -> int: ...  # noqa: E704


class SubprocessUpdateCommandRunner:
    def run(self, arguments: Sequence[str]) -> int:
        try:
            result = subprocess.run(
                list(arguments),
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                env={**os.environ, "LC_ALL": "C"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UpdateStagingError("Update worker could not be scheduled") from exc
        return result.returncode


class UpdateMutationBoundary:
    """Schedule fixed reviewed workers; never accept commands or package names."""

    def __init__(
        self,
        *,
        systemd_run: str = "/usr/bin/systemd-run",
        python: str = "/opt/3mm/current/.venv/bin/python",
        worker: str = "/opt/3mm/current/deployment/apply_staged_update.py",
        repository: str = "ldobranov/3mm",
        manifest_asset_name: str = "3mm-update-manifest.json",
        runner: UpdateCommandRunner | None = None,
    ) -> None:
        self._systemd_run = systemd_run
        self._python = python
        self._worker = worker
        self._repository = repository
        self._manifest_asset_name = manifest_asset_name
        self._runner = runner or SubprocessUpdateCommandRunner()

    def schedule(
        self,
        *,
        stage_root: Path,
        state_root: Path,
        allowlist: Path,
        release_id: str,
        approval_nonce: str,
        requested_by_user_id: int,
    ) -> None:
        arguments = (
            self._systemd_run,
            "--unit=3mm-update-apply",
            "--collect",
            "--property=Type=exec",
            "--property=TimeoutStartSec=45min",
            "--property=PrivateTmp=true",
            "--property=ProtectHome=true",
            "/usr/bin/env",
            "PYTHONPATH=/opt/3mm/current",
            self._python,
            self._worker,
            "--stage-root",
            str(stage_root),
            "--state-root",
            str(state_root),
            "--allowlist",
            str(allowlist),
            "--release-id",
            release_id,
            "--approval-nonce",
            approval_nonce,
            "--requested-by-user-id",
            str(requested_by_user_id),
            "--repository",
            self._repository,
            "--manifest-asset",
            self._manifest_asset_name,
        )
        if self._runner.run(arguments) != 0:
            raise UpdateStagingError("Update worker could not be scheduled")

    def schedule_network_setup(
        self,
        trigger: RecoveryTrigger,
        *,
        data_dir: Path = Path("/var/lib/3mm/provisioning"),
        service_user: str = "3mm",
        service_group: str = "3mm",
    ) -> None:
        if trigger not in {"manual", "automatic"}:
            raise ValueError("Network recovery trigger is invalid")
        arguments = (
            self._systemd_run,
            "--unit=3mm-network-recovery",
            "--collect",
            "--on-active=2s",
            "--property=Type=exec",
            "--property=TimeoutStartSec=2min",
            "--property=PrivateTmp=true",
            "--property=ProtectSystem=strict",
            f"--property=ReadWritePaths={data_dir.as_posix()}",
            "--property=ReadWritePaths=/run/lock",
            "--property=ProtectHome=true",
            "/usr/bin/env",
            "PYTHONPATH=/opt/3mm/current",
            self._python,
            "-m",
            "three_mm_runtime.network_recovery",
            "--data-dir",
            data_dir.as_posix(),
            "--trigger",
            trigger,
            "--user",
            service_user,
            "--group",
            service_group,
        )
        if self._runner.run(arguments) != 0:
            raise RuntimeError("Network setup worker could not be scheduled")

    def schedule_system_action(self, action: str) -> None:
        if action == "restart_device":
            unit = "3mm-system-restart"
            worker = ("/usr/bin/systemctl", "reboot")
            timeout = "2min"
            protection = ()
        elif action == "factory_reset":
            unit = "3mm-factory-reset"
            worker = (
                "/usr/bin/env",
                "PYTHONPATH=/opt/3mm/current",
                self._python,
                "/opt/3mm/current/deployment/factory_reset.py",
            )
            timeout = "5min"
            protection = (
                "--property=ProtectSystem=strict",
                "--property=ReadWritePaths=/var/lib/3mm",
                "--property=ReadWritePaths=/etc/3mm",
                "--property=ReadWritePaths=/run/lock",
                "--property=NoNewPrivileges=true",
            )
        else:
            raise ValueError("System action is invalid")

        arguments = (
            self._systemd_run,
            f"--unit={unit}",
            "--collect",
            "--on-active=2s",
            "--property=Type=exec",
            f"--property=TimeoutStartSec={timeout}",
            "--property=PrivateTmp=true",
            "--property=ProtectHome=true",
            *protection,
            *worker,
        )
        if self._runner.run(arguments) != 0:
            raise RuntimeError("System action could not be scheduled")

    def schedule_backup(self, *, backup_root: Path, requested_by_user_id: int) -> None:
        arguments = (
            self._systemd_run,
            "--unit=3mm-backup-create",
            "--collect",
            "--property=Type=exec",
            "--property=TimeoutStartSec=15min",
            "--property=PrivateTmp=true",
            "--property=ProtectSystem=strict",
            f"--property=ReadWritePaths={backup_root.as_posix()}",
            "--property=ReadWritePaths=/etc/3mm",
            "--property=ReadWritePaths=/run/lock",
            "--property=ProtectHome=true",
            "/usr/bin/env",
            "PYTHONPATH=/opt/3mm/current",
            self._python,
            "/opt/3mm/current/deployment/create_backup.py",
            "--backup-root",
            backup_root.as_posix(),
            "--key-file",
            "/etc/3mm/backup.key",
            "--requested-by-user-id",
            str(requested_by_user_id),
        )
        if self._runner.run(arguments) != 0:
            raise RuntimeError("Backup worker could not be scheduled")

    def schedule_restore(
        self,
        *,
        backup_root: Path,
        backup_id: str,
        requested_by_user_id: int,
    ) -> None:
        arguments = (
            self._systemd_run,
            "--unit=3mm-backup-restore",
            "--collect",
            "--property=Type=exec",
            "--property=TimeoutStartSec=20min",
            "--property=PrivateTmp=true",
            "--property=ProtectSystem=strict",
            "--property=ReadWritePaths=/var/lib/3mm",
            "--property=ReadWritePaths=/etc/3mm",
            "--property=ReadWritePaths=/run/lock",
            "--property=ProtectHome=true",
            "/usr/bin/env",
            "PYTHONPATH=/opt/3mm/current",
            self._python,
            "/opt/3mm/current/deployment/restore_backup.py",
            "--backup-root",
            backup_root.as_posix(),
            "--key-file",
            "/etc/3mm/backup.key",
            "--backup-id",
            backup_id,
            "--requested-by-user-id",
            str(requested_by_user_id),
        )
        if self._runner.run(arguments) != 0:
            raise RuntimeError("Restore worker could not be scheduled")

    def stop_application_extension(self, instance_id: str) -> None:
        SystemdApplicationSupervisor().stop(instance_id)

    def uninstall_application_extension(
        self,
        instance_id: str,
        *,
        root: Path,
        key_root: Path,
    ) -> None:
        uninstall_application_instance(
            instance_id,
            root=root,
            key_root=key_root,
        )

    def erase_application_extension_data(
        self,
        instance_id: str,
        *,
        root: Path,
    ) -> None:
        erase_application_instance_data(instance_id, root=root)


def _handle_request(
    payload: object,
    *,
    stage_root: Path,
    state_root: Path,
    allowlist: Path,
    status_file: Path,
    service_user: str = "3mm",
    service_group: str = "3mm",
    boundary: UpdateMutationBoundary | None = None,
    provisioning_data_dir: Path = Path("/var/lib/3mm/provisioning"),
    backup_root: Path = Path("/var/lib/3mm/backups"),
    application_upload_root: Path = Path("/var/lib/3mm/core/uploads/modules"),
    application_root: Path = Path("/var/lib/3mm/application-extensions"),
    application_key_root: Path = Path("/etc/3mm/application-extensions"),
    application_user: str = "3mm-app",
    application_group: str = "3mm-app",
) -> dict[str, object]:
    if isinstance(payload, dict) and set(payload) in (
        {"action", "sha256", "requested_by_user_id"},
        {"action", "sha256", "requested_by_user_id", "configuration"},
    ):
        sha256 = payload.get("sha256")
        user_id = payload.get("requested_by_user_id")
        configuration = payload.get("configuration", {})
        if (
            payload.get("action") != "activate_application_extension"
            or not isinstance(sha256, str)
            or not __import__("re").fullmatch(r"[0-9a-f]{64}", sha256)
            or not isinstance(user_id, int)
            or isinstance(user_id, bool)
            or user_id <= 0
            or not isinstance(configuration, dict)
        ):
            return {"ok": False, "error": "invalid_request"}
        try:
            service_uid, service_gid = _service_ids(
                application_user, application_group
            )
            activated = activate_application_package(
                application_upload_root / f"{sha256}.zip",
                sha256,
                configuration=configuration,
                root=application_root,
                key_root=application_key_root,
                service_uid=service_uid,
                service_gid=service_gid,
            )
        except Exception:
            LOGGER.exception("Application extension activation failed")
            return {"ok": False, "error": "application_activation_failed"}
        return {
            "ok": True,
            "status": "active",
            "module_id": activated.module_id,
            "version": activated.version,
            "sha256": activated.sha256,
            "instance_id": activated.instance_id,
            "socket_path": str(activated.socket_path),
        }

    if isinstance(payload, dict) and set(payload) == {
        "action",
        "instance_id",
        "requested_by_user_id",
    }:
        instance_id = payload.get("instance_id")
        user_id = payload.get("requested_by_user_id")
        action = payload.get("action")
        if (
            action not in {
                "disable_application_extension",
                "erase_application_extension_data",
                "uninstall_application_extension",
            }
            or not isinstance(instance_id, str)
            or not __import__("re").fullmatch(r"[0-9a-f]{24}", instance_id)
            or not isinstance(user_id, int)
            or isinstance(user_id, bool)
            or user_id <= 0
        ):
            return {"ok": False, "error": "invalid_request"}
        try:
            selected_boundary = boundary or UpdateMutationBoundary()
            if action == "uninstall_application_extension":
                selected_boundary.uninstall_application_extension(
                    instance_id,
                    root=application_root,
                    key_root=application_key_root,
                )
            elif action == "erase_application_extension_data":
                selected_boundary.erase_application_extension_data(
                    instance_id,
                    root=application_root,
                )
            else:
                selected_boundary.stop_application_extension(instance_id)
        except Exception:
            error = {
                "uninstall_application_extension": "application_uninstall_failed",
                "erase_application_extension_data": "application_data_erase_failed",
            }.get(action, "application_disable_failed")
            return {"ok": False, "error": error}
        return {
            "ok": True,
            "status": {
                "uninstall_application_extension": "uninstalled",
                "erase_application_extension_data": "erased",
            }.get(action, "disabled"),
        }

    if isinstance(payload, dict) and set(payload) == {
        "action",
        "backup_id",
        "passphrase",
        "requested_by_user_id",
    }:
        backup_id = payload.get("backup_id")
        passphrase = payload.get("passphrase")
        user_id = payload.get("requested_by_user_id")
        if (
            payload.get("action") != "export_backup"
            or not isinstance(backup_id, str)
            or not __import__("re").fullmatch(
                r"bkp_\d{8}T\d{6}Z_[0-9a-f]{8}", backup_id
            )
            or not isinstance(passphrase, str)
            or not isinstance(user_id, int)
            or isinstance(user_id, bool)
            or user_id <= 0
        ):
            return {"ok": False, "error": "invalid_request"}
        try:
            _service_uid, service_gid = _service_ids(service_user, service_group)
            exported = create_portable_export(
                backup_root,
                Path("/etc/3mm/backup.key"),
                backup_id,
                passphrase,
                owner=(0, service_gid),
            )
        except Exception:
            return {"ok": False, "error": "backup_export_failed"}
        return {
            "ok": True,
            "status": "ready",
            "export_id": exported.export_id,
            "backup_id": exported.backup_id,
            "filename": exported.filename,
        }

    if isinstance(payload, dict) and set(payload) == {
        "action",
        "upload_id",
        "passphrase",
        "requested_by_user_id",
    }:
        upload_id = payload.get("upload_id")
        passphrase = payload.get("passphrase")
        user_id = payload.get("requested_by_user_id")
        if (
            payload.get("action") != "restore_portable_backup"
            or not isinstance(upload_id, str)
            or not __import__("re").fullmatch(r"[0-9a-f]{32}", upload_id)
            or not isinstance(passphrase, str)
            or not isinstance(user_id, int)
            or isinstance(user_id, bool)
            or user_id <= 0
        ):
            return {"ok": False, "error": "invalid_request"}
        upload = backup_root.parent / "core/backup-imports" / (
            f"{upload_id}.3mmrecovery"
        )
        try:
            _service_uid, service_gid = _service_ids(service_user, service_group)
            backup_id = import_portable_backup(
                upload,
                backup_root,
                Path("/etc/3mm/backup.key"),
                passphrase,
                max_archive_bytes=MAX_PORTABLE_ARCHIVE_BYTES,
                owner=(0, service_gid),
            )
            (boundary or UpdateMutationBoundary()).schedule_restore(
                backup_root=backup_root,
                backup_id=backup_id,
                requested_by_user_id=user_id,
            )
        except Exception:
            upload.unlink(missing_ok=True)
            return {"ok": False, "error": "portable_restore_failed"}
        return {
            "ok": True,
            "status": "queued",
            "backup_id": backup_id,
        }

    if isinstance(payload, dict) and set(payload) == {
        "action",
        "backup_id",
        "requested_by_user_id",
    }:
        backup_id = payload.get("backup_id")
        user_id = payload.get("requested_by_user_id")
        if (
            payload.get("action") != "restore_backup"
            or not isinstance(backup_id, str)
            or not __import__("re").fullmatch(
                r"bkp_\d{8}T\d{6}Z_[0-9a-f]{8}", backup_id
            )
            or not isinstance(user_id, int)
            or isinstance(user_id, bool)
            or user_id <= 0
        ):
            return {"ok": False, "error": "invalid_request"}
        try:
            (boundary or UpdateMutationBoundary()).schedule_restore(
                backup_root=backup_root,
                backup_id=backup_id,
                requested_by_user_id=user_id,
            )
        except Exception:
            return {"ok": False, "error": "restore_schedule_failed"}
        return {"ok": True, "status": "queued"}

    if isinstance(payload, dict) and set(payload) == {
        "action",
        "requested_by_user_id",
    }:
        user_id = payload.get("requested_by_user_id")
        action = payload.get("action")
        if (
            action
            not in {
                "preview_backup",
                "start_network_setup",
                "restart_device",
                "factory_reset",
                "create_backup",
            }
            or not isinstance(user_id, int)
            or isinstance(user_id, bool)
            or user_id <= 0
        ):
            return {"ok": False, "error": "invalid_request"}

        if action == "preview_backup":
            try:
                preview = build_backup_preview(production_settings(backup_root))
            except Exception:
                LOGGER.exception("Backup preview failed")
                return {"ok": False, "error": "backup_preview_failed"}
            return {
                "ok": True,
                "status": "inspected",
                "preview": preview.model_dump(mode="json"),
            }

        if action == "create_backup":
            try:
                (boundary or UpdateMutationBoundary()).schedule_backup(
                    backup_root=backup_root,
                    requested_by_user_id=user_id,
                )
            except Exception:
                return {"ok": False, "error": "backup_schedule_failed"}
            return {"ok": True, "status": "queued"}

        if action in {"restart_device", "factory_reset"}:
            try:
                (boundary or UpdateMutationBoundary()).schedule_system_action(action)
            except Exception:
                return {"ok": False, "error": "system_action_schedule_failed"}
            return {"ok": True, "status": "queued"}

        marker = FileNetworkRecoveryMarker(
            provisioning_data_dir / "network-recovery.json"
        )
        try:
            snapshot = FileProvisioningStore(provisioning_data_dir).load()
            if marker.is_active():
                return {"ok": True, "status": "queued"}
            if snapshot is None or snapshot.state is not ProvisioningState.PROVISIONED:
                return {"ok": False, "error": "setup_not_available"}
            (boundary or UpdateMutationBoundary()).schedule_network_setup(
                "manual",
                data_dir=provisioning_data_dir,
                service_user=service_user,
                service_group=service_group,
            )
        except Exception:
            return {"ok": False, "error": "network_setup_schedule_failed"}
        return {"ok": True, "status": "queued"}

    if not isinstance(payload, dict) or set(payload) != {
        "action",
        "release_id",
        "approval_nonce",
        "requested_by_user_id",
    }:
        return {"ok": False, "error": "invalid_request"}
    release_id = payload.get("release_id")
    approval_nonce = payload.get("approval_nonce")
    user_id = payload.get("requested_by_user_id")
    if (
        payload.get("action") != "apply"
        or not isinstance(release_id, str)
        or not 1 <= len(release_id) <= 160
        or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in release_id
        )
        or not isinstance(approval_nonce, str)
        or len(approval_nonce) != 64
        or any(character not in "0123456789abcdef" for character in approval_nonce)
        or not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
    ):
        return {"ok": False, "error": "invalid_request"}

    service_gid: int | None = None
    staged = None
    try:
        service_uid, service_gid = _service_ids(service_user, service_group)
        if status_file.is_file():
            operation = UpdateOperationStatus.model_validate_json(
                status_file.read_text(encoding="utf-8")
            )
            if operation.state in {"queued", "applying"}:
                return {"ok": False, "error": "update_busy"}
        staged = validate_staged_payload(
            stage_root,
            allowlist,
            release_id=release_id,
            approval_nonce=approval_nonce,
            expected_owner_uid=service_uid,
        )
        queued = UpdateOperationStatus(
            state="queued",
            message="The verified update is queued for installation",
            release_id=staged.release_id,
            version=staged.version,
            commit=staged.commit,
            requested_by_user_id=user_id,
            started_at=datetime.now(UTC),
        )
        write_operation_status(status_file, queued, owner=(0, service_gid))
        (boundary or UpdateMutationBoundary()).schedule(
            stage_root=stage_root,
            state_root=state_root,
            allowlist=allowlist,
            release_id=release_id,
            approval_nonce=approval_nonce,
            requested_by_user_id=user_id,
        )
    except Exception:
        if service_gid is not None:
            try:
                write_operation_status(
                    status_file,
                    UpdateOperationStatus(
                        state="failed",
                        message="The verified update could not be scheduled",
                        release_id=staged.release_id if staged else release_id,
                        version=staged.version if staged else None,
                        commit=staged.commit if staged else None,
                        requested_by_user_id=user_id,
                        started_at=datetime.now(UTC),
                        completed_at=datetime.now(UTC),
                        error_code="schedule_failed",
                    ),
                    owner=(0, service_gid),
                )
            except Exception:
                pass
        return {"ok": False, "error": "update_schedule_failed"}
    return {"ok": True, "status": "queued"}


def serve(
    socket_path: Path,
    *,
    stage_root: Path,
    state_root: Path,
    allowlist: Path,
    repository: str,
    manifest_asset_name: str,
    group_name: str = "3mm",
    network_recovery_policy: Path = Path(
        "/var/lib/3mm/core/network-recovery-policy.json"
    ),
    provisioning_data_dir: Path = Path("/var/lib/3mm/provisioning"),
    backup_root: Path = Path("/var/lib/3mm/backups"),
    application_upload_root: Path = Path("/var/lib/3mm/core/uploads/modules"),
    application_root: Path = Path("/var/lib/3mm/application-extensions"),
    application_key_root: Path = Path("/etc/3mm/application-extensions"),
) -> None:
    import grp

    group_id = grp.getgrnam(group_name).gr_gid
    boundary = UpdateMutationBoundary(
        repository=repository,
        manifest_asset_name=manifest_asset_name,
    )
    recovery_monitor = NetworkRecoveryMonitor(
        policy_store=FileNetworkRecoveryPolicyStore(network_recovery_policy),
        marker=FileNetworkRecoveryMarker(
            provisioning_data_dir / "network-recovery.json"
        ),
        provisioning_store=FileProvisioningStore(provisioning_data_dir),
        inspector=NetworkManagerReadOnlyAdapter.from_system(),
        scheduler=boundary,
    )
    socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    os.chown(socket_path.parent, 0, group_id)
    os.chmod(socket_path.parent, 0o750)
    socket_path.unlink(missing_ok=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(socket_path))
        os.chown(socket_path, 0, group_id)
        os.chmod(socket_path, 0o660)
        server.listen(4)
        server.settimeout(5.0)
        while True:
            try:
                connection, _ = server.accept()
            except socket.timeout:
                recovery_monitor.poll()
                continue
            with connection:
                request = b""
                while len(request) <= MAX_REQUEST_BYTES:
                    chunk = connection.recv(1024)
                    if not chunk:
                        break
                    request += chunk
                    if b"\n" in request:
                        break
                try:
                    if len(request) > MAX_REQUEST_BYTES:
                        raise ValueError("request_too_large")
                    payload = json.loads(request.split(b"\n", 1)[0])
                    response = _handle_request(
                        payload,
                        stage_root=stage_root,
                        state_root=state_root,
                        allowlist=allowlist,
                        status_file=state_root / "status.json",
                        service_group=group_name,
                        boundary=boundary,
                        provisioning_data_dir=provisioning_data_dir,
                        backup_root=backup_root,
                        application_upload_root=application_upload_root,
                        application_root=application_root,
                        application_key_root=application_key_root,
                    )
                except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                    response = {"ok": False, "error": "invalid_request"}
                encoded = (
                    json.dumps(response, separators=(",", ":")).encode("utf-8")
                    + b"\n"
                )
                if len(encoded) > MAX_RESPONSE_BYTES:
                    encoded = b'{"ok":false,"error":"response_too_large"}\n'
                connection.sendall(encoded)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--stage-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--manifest-asset", required=True)
    parser.add_argument("--group", default="3mm")
    parser.add_argument(
        "--network-recovery-policy",
        type=Path,
        default=Path("/var/lib/3mm/core/network-recovery-policy.json"),
    )
    parser.add_argument(
        "--provisioning-data-dir",
        type=Path,
        default=Path("/var/lib/3mm/provisioning"),
    )
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=Path("/var/lib/3mm/backups"),
    )
    parser.add_argument(
        "--application-upload-root",
        type=Path,
        default=Path("/var/lib/3mm/core/uploads/modules"),
    )
    parser.add_argument(
        "--application-root",
        type=Path,
        default=Path("/var/lib/3mm/application-extensions"),
    )
    parser.add_argument(
        "--application-key-root",
        type=Path,
        default=Path("/etc/3mm/application-extensions"),
    )
    arguments = parser.parse_args()
    serve(
        arguments.socket,
        stage_root=arguments.stage_root,
        state_root=arguments.state_root,
        allowlist=arguments.allowlist,
        repository=arguments.repository,
        manifest_asset_name=arguments.manifest_asset,
        group_name=arguments.group,
        network_recovery_policy=arguments.network_recovery_policy,
        provisioning_data_dir=arguments.provisioning_data_dir,
        backup_root=arguments.backup_root,
        application_upload_root=arguments.application_upload_root,
        application_root=arguments.application_root,
        application_key_root=arguments.application_key_root,
    )


if __name__ == "__main__":
    main()
