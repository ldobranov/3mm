#!/usr/bin/env python3
"""Apply one verified staged update through the immutable installer boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import stat
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol, Sequence

from backend.services.update_staging import (
    UpdateOperationStatus,
    StagedUpdate,
    UpdateStagingError,
    inspect_installed_dependencies,
    revalidate_official_release,
    validate_staged_payload,
    verify_release_archive,
    write_operation_status,
)
from deployment.deployment_contract import INSTALLER_PATH, MAX_INSTALLER_BYTES

LOGGER = logging.getLogger(__name__)


def _prepare_target(
    stage_root: Path, private_root: Path, staged: StagedUpdate, owner_uid: int
):
    """Freeze approved bytes before executing anything from a service-writable stage.

    No tar extraction to disk: only the fixed, regular installer is copied. The
    root-private snapshot is rehashed and revalidated; concurrent stage rewrites
    cannot substitute the code or payload after privileged verification.
    """
    snapshot = private_root / "release.tar.gz"
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(stage_root / "staged-release.tar.gz", flags)
    digest = hashlib.sha256()
    received = 0
    with os.fdopen(descriptor, "rb") as source, snapshot.open("xb") as output:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != owner_uid:
            raise UpdateStagingError("Target archive ownership or file type changed")
        os.chmod(snapshot, 0o600)
        while chunk := source.read(1024 * 1024):
            received += len(chunk)
            if received > staged.artifact_size_bytes:
                raise UpdateStagingError("Target archive size changed during snapshot")
            digest.update(chunk)
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    if (
        received != staged.artifact_size_bytes
        or digest.hexdigest() != staged.artifact_sha256
    ):
        raise UpdateStagingError("Target archive checksum changed during snapshot")
    contract = verify_release_archive(
        snapshot,
        release_id=staged.release_id,
        version=staged.version,
        commit=staged.commit,
        architecture=staged.architecture,
        dependencies=staged.dependencies,
    )
    installer = private_root / "install-systemd.sh"
    with tarfile.open(snapshot, "r:gz") as archive:
        member = next(
            item
            for item in archive.getmembers()
            if PurePosixPath(item.name).as_posix() == INSTALLER_PATH
        )
        if not member.isfile() or not 0 < member.size <= MAX_INSTALLER_BYTES:
            raise UpdateStagingError("Verified target installer is invalid")
        with archive.extractfile(member) as source, installer.open("xb") as output:
            os.chmod(installer, 0o700)
            output.write(source.read(MAX_INSTALLER_BYTES + 1))
    return snapshot, installer, contract


def _service_ids(user_name: str, group_name: str) -> tuple[int, int]:
    import grp
    import pwd

    return pwd.getpwnam(user_name).pw_uid, grp.getgrnam(group_name).gr_gid


class ApplyCommandRunner(Protocol):
    def run(
        self,
        arguments: Sequence[str],
        *,
        environment: dict[str, str] | None = None,
    ) -> int:
        raise NotImplementedError


class SubprocessApplyCommandRunner:
    def run(
        self,
        arguments: Sequence[str],
        *,
        environment: dict[str, str] | None = None,
    ) -> int:
        try:
            result = subprocess.run(
                list(arguments),
                check=False,
                timeout=40 * 60,
                env=environment,
            )
        except subprocess.TimeoutExpired as exc:
            raise UpdateStagingError(
                f"{arguments[0]} exceeded the 40-minute deadline; check 3mm-update-apply logs"
            ) from exc
        except OSError as exc:
            raise UpdateStagingError(f"Could not start {arguments[0]}: {exc}") from exc
        return result.returncode


def _append_audit(path: Path, payload: dict[str, object], group_id: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o640)
        try:
            os.fchmod(descriptor, 0o640)
            os.fchown(descriptor, 0, group_id)
            os.write(
                descriptor,
                (
                    json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
                ).encode("utf-8"),
            )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise UpdateStagingError("Update audit record could not be written") from exc


def apply_staged_update(
    *,
    stage_root: Path,
    state_root: Path,
    allowlist: Path,
    release_id: str,
    approval_nonce: str,
    requested_by_user_id: int,
    service_user: str = "3mm",
    service_group: str = "3mm",
    repository: str = "ldobranov/3mm",
    manifest_asset_name: str = "3mm-update-manifest.json",
    runner: ApplyCommandRunner | None = None,
    dependency_inspector=inspect_installed_dependencies,
    catalog_checker=None,
) -> int:
    command_runner = runner or SubprocessApplyCommandRunner()
    user_id, group_id = _service_ids(service_user, service_group)
    status_file = state_root / "status.json"
    audit_file = state_root / "audit.jsonl"
    started_at = datetime.now(UTC)
    staged = None
    error_code = "validation_failed"
    private = None
    try:
        staged = validate_staged_payload(
            stage_root,
            allowlist,
            release_id=release_id,
            approval_nonce=approval_nonce,
            expected_owner_uid=user_id,
        )
        catalog_arguments = {
            "repository": repository,
            "manifest_asset_name": manifest_asset_name,
        }
        if catalog_checker is not None:
            catalog_arguments["catalog_checker"] = catalog_checker
        revalidate_official_release(staged, **catalog_arguments)
        error_code = "target_preflight_failed"
        private = tempfile.TemporaryDirectory(prefix="3mm-update-target-")
        archive_path, installer, contract = _prepare_target(
            stage_root,
            Path(private.name),
            staged,
            user_id,
        )
        if command_runner.run(("/usr/bin/bash", "-n", str(installer))) != 0:
            raise UpdateStagingError(
                "Target installer syntax preflight failed; check 3mm-update-apply logs"
            )
        write_operation_status(
            status_file,
            UpdateOperationStatus(
                state="applying",
                message="Installing the verified update",
                release_id=staged.release_id,
                version=staged.version,
                commit=staged.commit,
                requested_by_user_id=requested_by_user_id,
                started_at=started_at,
            ),
            owner=(0, group_id),
        )

        installed = dependency_inspector(staged.dependencies)
        missing = [package for package in staged.dependencies if not installed[package]]
        if missing:
            error_code = "dependency_install_failed"
            environment = {
                **os.environ,
                "DEBIAN_FRONTEND": "noninteractive",
                "LC_ALL": "C",
            }
            if (
                command_runner.run(
                    ("/usr/bin/apt-get", "update"), environment=environment
                )
                != 0
            ):
                raise UpdateStagingError("Approved dependency metadata update failed")
            if (
                command_runner.run(
                    (
                        "/usr/bin/apt-get",
                        "install",
                        "--yes",
                        "--no-install-recommends",
                        "--no-remove",
                        "--",
                        *missing,
                    ),
                    environment=environment,
                )
                != 0
            ):
                raise UpdateStagingError("Approved dependency installation failed")
            refreshed = dependency_inspector(staged.dependencies)
            if any(not refreshed[package] for package in staged.dependencies):
                raise UpdateStagingError("Approved dependencies remain unavailable")

        error_code = "installer_failed"
        installer_result = command_runner.run(
            (
                "/usr/bin/bash",
                str(installer),
                str(archive_path),
                staged.release_id,
                staged.frontend_origin,
                "",
                staged.artifact_sha256,
            )
        )
        if installer_result != 0:
            raise UpdateStagingError(
                f"Target installer exited with code {installer_result}; check journalctl -u "
                "3mm-update-apply.service for the failure and rollback result"
            )

        completed_at = datetime.now(UTC)
        succeeded = UpdateOperationStatus(
            state="succeeded",
            message="The update was installed and passed all health checks",
            release_id=staged.release_id,
            version=staged.version,
            commit=staged.commit,
            requested_by_user_id=requested_by_user_id,
            started_at=started_at,
            completed_at=completed_at,
        )
        write_operation_status(status_file, succeeded, owner=(0, group_id))
        _append_audit(
            audit_file,
            {
                "completed_at": completed_at.isoformat(),
                "dependencies": staged.dependencies,
                "deployment_contract_version": contract.schema_version,
                "installer_source": "verified_target_artifact",
                "release_id": staged.release_id,
                "requested_by_user_id": requested_by_user_id,
                "result": "succeeded",
                "version": staged.version,
            },
            group_id,
        )
        command_runner.run(
            ("/usr/bin/systemctl", "try-restart", "3mm-update-helper.service")
        )
        return 0
    except (KeyError, OSError, tarfile.TarError, UpdateStagingError) as exc:
        LOGGER.exception("Update %s failed at %s", release_id, error_code)
        completed_at = datetime.now(UTC)
        failed = UpdateOperationStatus(
            state="failed",
            message=str(exc),
            release_id=staged.release_id if staged else release_id,
            version=staged.version if staged else None,
            commit=staged.commit if staged else None,
            requested_by_user_id=requested_by_user_id,
            started_at=started_at,
            completed_at=completed_at,
            error_code=error_code,
        )
        try:
            write_operation_status(status_file, failed, owner=(0, group_id))
            _append_audit(
                audit_file,
                {
                    "completed_at": completed_at.isoformat(),
                    "error_code": error_code,
                    "release_id": release_id,
                    "requested_by_user_id": requested_by_user_id,
                    "result": "failed",
                },
                group_id,
            )
        except UpdateStagingError:
            pass
        return 1
    finally:
        if private is not None:
            private.cleanup()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--approval-nonce", required=True)
    parser.add_argument("--requested-by-user-id", type=int, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--manifest-asset", required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    if os.geteuid() != 0:
        raise SystemExit("The staged update worker must run as root")
    return apply_staged_update(
        stage_root=arguments.stage_root,
        state_root=arguments.state_root,
        allowlist=arguments.allowlist,
        release_id=arguments.release_id,
        approval_nonce=arguments.approval_nonce,
        requested_by_user_id=arguments.requested_by_user_id,
        repository=arguments.repository,
        manifest_asset_name=arguments.manifest_asset,
    )


if __name__ == "__main__":
    raise SystemExit(main())
