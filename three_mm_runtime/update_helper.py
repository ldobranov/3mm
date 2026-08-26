"""Root-only immutable update scheduler exposed through a local Unix socket."""

from __future__ import annotations

import argparse
import json
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

MAX_REQUEST_BYTES = 4096


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
    """Schedule one fixed reviewed worker; never accept commands or package names."""

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
) -> dict[str, object]:
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
) -> None:
    import grp

    group_id = grp.getgrnam(group_name).gr_gid
    boundary = UpdateMutationBoundary(
        repository=repository,
        manifest_asset_name=manifest_asset_name,
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
        while True:
            connection, _ = server.accept()
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
                    )
                except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                    response = {"ok": False, "error": "invalid_request"}
                connection.sendall(
                    json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--stage-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--manifest-asset", required=True)
    parser.add_argument("--group", default="3mm")
    arguments = parser.parse_args()
    serve(
        arguments.socket,
        stage_root=arguments.stage_root,
        state_root=arguments.state_root,
        allowlist=arguments.allowlist,
        repository=arguments.repository,
        manifest_asset_name=arguments.manifest_asset,
        group_name=arguments.group,
    )


if __name__ == "__main__":
    main()
