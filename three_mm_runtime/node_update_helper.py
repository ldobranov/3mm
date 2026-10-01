"""Narrow root boundary for already prepared, immutable ARMv6 Node updates.

No downloads, shell strings, caller paths or Core/backend imports are accepted.
An unresolved attempt is never permission to execute the installer again.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import socket
import stat
import struct
import subprocess
import sys
import tarfile
import threading
import uuid
import shutil

from pydantic import ValidationError
from three_mm_protocol.node_updates import (
    NodeUpdateApplyRequest,
    NodeUpdateAuthorization,
    NodeUpdateOperation,
    NodeUpdatePrepareRequest,
    NodeUpdatePreparedArtifact,
    NodeUpdateSupport,
)

STATE_ROOT = Path("/var/lib/3mm-node-update")
SOCKET_PATH = Path("/run/3mm-node-update/helper.sock")
CURRENT_ROOT = Path("/opt/3mm/current")
AGENT_DATA = Path("/var/lib/3mm/agent")
AGENT_UPDATE_INBOX = AGENT_DATA / "node-update-inbox"
MAX_REQUEST_BYTES = 16 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 10000
MAX_OPERATIONS = 128
ACTIVE_STATES = {"accepted", "running", "unknown"}
REQUIRED_FILES = {
    ".3mm-release.json", ".3mm-install-profile", "VERSION",
    "agent/main.py", "agent/requirements.txt", "agent/node_update_execution.py", "setup_service/main.py",
    "deployment/install-systemd.sh", "deployment/node-requirements.txt",
    "deployment/node_preflight.py", "deployment/node-wheels/provenance.json",
    "deployment/apply_node_update.py", "three_mm_runtime/node_update_helper.py",
    "deployment/trust_node_update_hub.py", "three_mm_runtime/node_update_trust.py",
    "three_mm_protocol/node_updates.py", "deployment/systemd/3mm-node-update-helper.service",
}


class NodeUpdateError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def unit_name(operation_id: str) -> str:
    if not isinstance(operation_id, str) or not re.fullmatch(r"nodeupd_[0-9a-f]{32}", operation_id):
        raise NodeUpdateError("invalid_request", "Invalid operation identity")
    return "3mm-node-update-" + operation_id.removeprefix("nodeupd_") + ".service"


def trusted_path(path: Path, *, directory=False, permissions=True) -> None:
    """Reject links and writable/untrusted ancestors before privileged use."""
    path = path.absolute()
    for ancestor in reversed((path, *path.parents)):
        info = ancestor.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise NodeUpdateError("unsafe_path", "Node update path is a symlink")
        if permissions and (info.st_uid != 0 or info.st_mode & 0o022):
            raise NodeUpdateError("unsafe_path", "Node update path is not root-owned and protected")
        if ancestor != path and not stat.S_ISDIR(info.st_mode):
            raise NodeUpdateError("unsafe_path", "Node update ancestor is not a directory")
    kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not kind or (not directory and info.st_nlink != 1):
        raise NodeUpdateError("unsafe_path", "Node update path is not a private regular file/directory")


def read_small(path: Path, limit=64 * 1024) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
        raise NodeUpdateError("invalid_file", "Node update file is invalid or too large")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        value = source.read(limit + 1)
    if len(value) > limit:
        raise NodeUpdateError("invalid_file", "Node update file is too large")
    return value


def request_digest(request: NodeUpdateApplyRequest | NodeUpdateAuthorization) -> str:
    return hashlib.sha256(json.dumps(request.model_dump(mode="json"),
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class NodeUpdateStore:
    def __init__(self, root=STATE_ROOT, *, enforce_permissions=True):
        self.root = Path(root).absolute()
        self.enforce_permissions = enforce_permissions
        self._thread_lock = threading.RLock()
        for directory in (self.root, self.root / "operations", self.root / "staging"):
            if not directory.exists():
                trusted_path(directory.parent, directory=True, permissions=enforce_permissions)
                directory.mkdir(mode=0o700)
            trusted_path(directory, directory=True, permissions=enforce_permissions)

    @contextmanager
    def locked(self):
        with self._thread_lock:
            path = self.root / "helper.lock"
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                trusted_path(path, permissions=self.enforce_permissions)
                if os.name == "posix":
                    import fcntl
                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                yield
            finally:
                os.close(descriptor)

    def read(self, operation_id):
        unit_name(operation_id)
        path = self.root / "operations" / (operation_id + ".json")
        if not path.exists():
            return None
        trusted_path(path, permissions=self.enforce_permissions)
        try:
            raw = json.loads(read_small(path))
            if not isinstance(raw, dict):
                raise ValueError("record must be an object")
            request = NodeUpdateApplyRequest.model_validate_json(json.dumps(raw["request"]))
            # Legacy unsigned records remain observable, never executable.
            authorization = (NodeUpdateAuthorization.model_validate_json(json.dumps(raw["authorization"]))
                             if raw.get("authorization") is not None else None)
            operation = NodeUpdateOperation.model_validate_json(json.dumps(raw["operation"]))
            if (request.operation_id != operation_id or operation.operation_id != operation_id
                    or any(getattr(request, field) != getattr(operation, field)
                           for field in ("device_id", "release_id", "archive_sha256"))
                    or (authorization is not None and authorization.request != request)
                    or raw["digest"] != request_digest(authorization or request)):
                raise ValueError("record identity mismatch")
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise NodeUpdateError("invalid_state", "Node update operation record is invalid") from exc
        return {"request": request, "authorization": authorization,
                "operation": operation, "digest": raw["digest"]}

    def records(self):
        return [self.read(path.stem) for path in sorted((self.root / "operations").glob("*.json"))]

    def write(self, record):
        operation = record["operation"]
        unit_name(operation.operation_id)
        directory = self.root / "operations"
        trusted_path(directory, directory=True, permissions=self.enforce_permissions)
        temporary = directory / (".status-" + uuid.uuid4().hex)
        payload = json.dumps({"request": record["request"].model_dump(mode="json"),
            "authorization": (record["authorization"].model_dump(mode="json")
                              if record.get("authorization") is not None else None),
            "operation": operation.model_dump(mode="json"), "digest": record["digest"]}, sort_keys=True).encode()
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as saved:
                saved.write(payload)
                saved.flush()
                os.fsync(saved.fileno())
            os.replace(temporary, directory / (operation.operation_id + ".json"))
            if os.name == "posix":
                descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    def transition(self, record, status, *, error_code=None, previous_release_id=None):
        updates = {"status": status, "updated_at": datetime.now(UTC), "error_code": error_code}
        if previous_release_id is not None:
            updates["previous_release_id"] = previous_release_id
        record["operation"] = NodeUpdateOperation.model_validate(
            {**record["operation"].model_dump(), **updates})
        self.write(record)
        return record["operation"]


def prepare_downloaded_archive(
    request: NodeUpdatePrepareRequest,
    *,
    store: NodeUpdateStore,
    service_uid: int,
    agent_data: Path = AGENT_DATA,
) -> NodeUpdatePreparedArtifact:
    """Copy one completed Agent download into root-owned immutable staging."""

    inbox_root = Path(agent_data) / "node-update-inbox"
    source_dir = inbox_root / request.operation_id
    source_path = source_dir / "release.tar.gz"

    for directory in (Path(agent_data), inbox_root, source_dir):
        info = directory.lstat()

        if not stat.S_ISDIR(info.st_mode):
            raise NodeUpdateError(
                "unsafe_download",
                "Agent update inbox is not a directory",
            )

        if os.name == "posix" and (
            info.st_uid != service_uid
            or info.st_mode & 0o022
        ):
            raise NodeUpdateError(
                "unsafe_download",
                "Agent update inbox is not private to the service user",
            )

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)

    try:
        source_fd = os.open(source_path, flags)
    except OSError as exc:
        raise NodeUpdateError(
            "missing_download",
            "Downloaded Node update archive is unavailable",
        ) from exc

    try:
        before = os.fstat(source_fd)

        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size != request.archive_size_bytes
            or before.st_size > MAX_ARCHIVE_BYTES
        ):
            raise NodeUpdateError(
                "unsafe_download",
                "Downloaded Node update archive is invalid",
            )

        if os.name == "posix" and (
            before.st_uid != service_uid
            or before.st_mode & 0o022
        ):
            raise NodeUpdateError(
                "unsafe_download",
                "Downloaded Node update archive is not private to the service user",
            )

        staging_dir = store.root / "staging" / request.operation_id

        if not staging_dir.exists():
            trusted_path(
                staging_dir.parent,
                directory=True,
                permissions=store.enforce_permissions,
            )
            staging_dir.mkdir(mode=0o700)

        trusted_path(
            staging_dir,
            directory=True,
            permissions=store.enforce_permissions,
        )

        metadata_path = staging_dir / "prepared.json"
        target_path = staging_dir / "release.tar.gz"

        if metadata_path.exists() or target_path.exists():
            if not metadata_path.exists() or not target_path.exists():
                raise NodeUpdateError(
                    "invalid_state",
                    "Prepared Node update staging is incomplete",
                )

            trusted_path(
                metadata_path,
                permissions=store.enforce_permissions,
            )
            trusted_path(
                target_path,
                permissions=store.enforce_permissions,
            )

            try:
                prepared = NodeUpdatePreparedArtifact.model_validate_json(
                    read_small(metadata_path)
                )
            except (ValidationError, ValueError) as exc:
                raise NodeUpdateError(
                    "invalid_state",
                    "Prepared Node update metadata is invalid",
                ) from exc

            for field in (
                "operation_id",
                "device_id",
                "release_id",
                "archive_sha256",
                "archive_size_bytes",
            ):
                if getattr(prepared, field) != getattr(request, field):
                    raise NodeUpdateError(
                        "identity_conflict",
                        "Prepared operation identity has different content",
                    )

            return prepared

        temporary_path = staging_dir / (
            ".release-" + uuid.uuid4().hex
        )

        destination_fd = os.open(
            temporary_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )

        checksum = hashlib.sha256()
        copied = 0

        try:
            with os.fdopen(
                os.dup(source_fd),
                "rb",
            ) as source, os.fdopen(
                destination_fd,
                "wb",
            ) as destination:
                while True:
                    chunk = source.read(1024 * 1024)

                    if not chunk:
                        break

                    copied += len(chunk)

                    if copied > MAX_ARCHIVE_BYTES:
                        raise NodeUpdateError(
                            "archive_too_large",
                            "Downloaded Node archive exceeds its limit",
                        )

                    checksum.update(chunk)
                    destination.write(chunk)

                destination.flush()
                os.fsync(destination.fileno())

            after = os.fstat(source_fd)

            if (
                copied != request.archive_size_bytes
                or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns
            ):
                raise NodeUpdateError(
                    "download_changed",
                    "Downloaded Node archive changed during preparation",
                )

            if checksum.hexdigest() != request.archive_sha256:
                raise NodeUpdateError(
                    "checksum_mismatch",
                    "Downloaded Node archive checksum differs",
                )

            os.replace(temporary_path, target_path)

            prepared = NodeUpdatePreparedArtifact(
                operation_id=request.operation_id,
                device_id=request.device_id,
                release_id=request.release_id,
                archive_sha256=request.archive_sha256,
                archive_size_bytes=request.archive_size_bytes,
                prepared_at=datetime.now(UTC),
            )

            temporary_metadata = staging_dir / (
                ".prepared-" + uuid.uuid4().hex
            )

            descriptor = os.open(
                temporary_metadata,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )

            with os.fdopen(descriptor, "wb") as saved:
                saved.write(
                    prepared.model_dump_json().encode()
                )
                saved.flush()
                os.fsync(saved.fileno())

            os.replace(temporary_metadata, metadata_path)

            if os.name == "posix":
                directory_fd = os.open(
                    staging_dir,
                    os.O_RDONLY | os.O_DIRECTORY,
                )
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)

            return prepared

        finally:
            temporary_path.unlink(missing_ok=True)

    finally:
        os.close(source_fd)
        

def inspect_prepared_archive(request, *, store, current_root=CURRENT_ROOT,
                             agent_data=AGENT_DATA, machine=None, python_version=None,
                             system=None, now=None):
    """Validate again at the root boundary; do not extract or mutate an archive."""
    if ((system or platform.system()) != "Linux" or (machine or platform.machine()) != "armv6l"
            or tuple(python_version or sys.version_info[:2]) != (3, 13)):
        raise NodeUpdateError("unsupported_target", "Node update requires Linux ARMv6 and Python 3.13")
    instant = now or datetime.now(UTC)
    if request.created_at > instant or request.expires_at <= instant:
        raise NodeUpdateError("expired", "Node update handoff is not currently authorized")
    current = Path(current_root).resolve(strict=True)
    trusted_path(current, directory=True, permissions=store.enforce_permissions)
    trusted_path(current / ".3mm-install-profile", permissions=store.enforce_permissions)
    if read_small(current / ".3mm-install-profile").strip() != b"node":
        raise NodeUpdateError("wrong_profile", "Current installation is not a Node")
    identity = json.loads(read_small(Path(agent_data) / "identity.json"))
    if not isinstance(identity, dict) or identity.get("device_id") != request.device_id:
        raise NodeUpdateError("identity_mismatch", "Node update targets another device")
    archive_path = store.root / "staging" / request.operation_id / "release.tar.gz"
    trusted_path(archive_path, permissions=store.enforce_permissions)
    if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise NodeUpdateError("archive_too_large", "Node update archive is too large")
    checksum = hashlib.sha256()
    with archive_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    if checksum.hexdigest() != request.archive_sha256:
        raise NodeUpdateError("checksum_mismatch", "Node update archive checksum differs")
    names, files, metadata, marker, version, total = set(), set(), None, None, None, 0
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            for count, member in enumerate(archive, 1):
                name = member.name.rstrip("/")
                normalized = PurePosixPath(name)
                if (count > MAX_MEMBERS or not name or "\\" in name or normalized.is_absolute()
                        or ".." in normalized.parts or normalized.as_posix() != name
                        or name in names or member.mode & 0o6000
                        or not (member.isfile() or member.isdir())):
                    raise NodeUpdateError("unsafe_archive", "Node archive contains an unsafe or duplicate entry")
                names.add(name)
                if member.isfile():
                    files.add(name)
                total += member.size
                if member.size < 0 or member.size > MAX_MEMBER_BYTES or total > MAX_ARCHIVE_BYTES:
                    raise NodeUpdateError("archive_too_large", "Expanded Node archive exceeds its limits")
                if name in {".3mm-release.json", ".3mm-install-profile", "VERSION"}:
                    if not member.isfile() or member.size > 64 * 1024:
                        raise NodeUpdateError("invalid_archive", "Node release metadata is invalid")
                    value = archive.extractfile(member).read()
                    if name == ".3mm-release.json":
                        metadata = json.loads(value)
                    elif name == ".3mm-install-profile":
                        marker = value.strip()
                    else:
                        version = value.decode("ascii").strip()
    except (OSError, tarfile.TarError, ValueError) as exc:
        raise NodeUpdateError("invalid_archive", "Node update archive cannot be validated") from exc
    if (REQUIRED_FILES - files or marker != b"node" or not isinstance(metadata, dict)
            or metadata.get("profile") != "node" or metadata.get("architecture") != "armv6l"
            or metadata.get("python") != "3.13" or metadata.get("release_id") != request.release_id
            or metadata.get("version") != request.release_id.removeprefix("v") or version != metadata.get("version")
            or metadata.get("includes_working_tree") is not False or metadata.get("branch") != "main"
            or not isinstance(metadata.get("commit"), str) or not re.fullmatch("[0-9a-f]{40}", metadata["commit"])):
        raise NodeUpdateError("invalid_release", "Prepared archive is not the requested official Node release")
    return archive_path, metadata


class SubprocessNodeUpdateScheduler:
    def __init__(self, current_root=CURRENT_ROOT, runner=subprocess.run, *, enforce_permissions=True):
        self.current_root, self.runner = Path(current_root), runner
        self.enforce_permissions = enforce_permissions

    def schedule(self, operation_id):
        release = self.current_root.resolve(strict=True)
        trusted_path(release, directory=True, permissions=self.enforce_permissions)
        trusted_path(release / "deployment/apply_node_update.py", permissions=self.enforce_permissions)
        trusted_path(release / ".venv/bin", directory=True, permissions=self.enforce_permissions)
        trusted_path((release / ".venv/bin/python").resolve(strict=True), permissions=self.enforce_permissions)
        arguments = ["/usr/bin/systemd-run", "--unit=" + unit_name(operation_id),
            "--collect", "--property=Type=exec", "--property=KillMode=control-group",
            "--property=TimeoutStopSec=30s",
            "--property=UMask=0022",
            "--property=RuntimeMaxSec=45min", "--property=PrivateTmp=true", "--property=ProtectHome=true",
            "/usr/bin/env", "PYTHONPATH=" + str(release), str(release / ".venv/bin/python"),
            str(release / "deployment/apply_node_update.py"), "--operation-id", operation_id]
        result = self.runner(arguments, check=False, timeout=15,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode:
            raise NodeUpdateError("schedule_unknown", "Node update scheduling outcome is unresolved")

    def state(self, operation_id):
        try:
            result = self.runner(["/usr/bin/systemctl", "show", unit_name(operation_id),
                "--property=ActiveState", "--value"], check=False, timeout=5,
                capture_output=True, text=True)
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"


class NodeUpdateHelper:
    def __init__(self, store, *, service_uid, scheduler=None, validator=None, authorization_verifier=None):
        self.store, self.service_uid = store, service_uid
        self.scheduler = scheduler or SubprocessNodeUpdateScheduler()
        self.validator = validator or (lambda request: inspect_prepared_archive(request, store=store))
        from three_mm_runtime.node_update_trust import verify_node_update_authorization
        self.authorization_verifier = authorization_verifier or (
            lambda authorization: verify_node_update_authorization(authorization, state_root=store.root))

    def _reconcile(self, record):
        if (record["operation"].status in {"accepted", "running"}
                and self.scheduler.state(record["operation"].operation_id) not in {"active", "activating", "reloading"}):
            self.store.transition(record, "unknown", error_code="worker_unresolved")
        return record["operation"]

    def handle_request(self, payload, *, peer_uid):
        if peer_uid not in {0, self.service_uid}:
            return {"ok": False, "error": "forbidden_peer"}
        try:
            if not isinstance(payload, dict):
                raise NodeUpdateError("invalid_request", "Invalid request envelope")
            if payload == {"action": "support"}:
                from three_mm_runtime.node_update_trust import read_node_update_trust
                try:
                    trust = read_node_update_trust()
                except NodeUpdateError as exc:
                    if exc.code != "hub_trust_missing":
                        raise
                    trust = None
                support = NodeUpdateSupport(signed_apply_supported=True,
                    approval_key_id=trust.hub_key.key_id if trust else None,
                    trusted_device_id=trust.device_id if trust else None)
                return {"ok": True, "support": support.model_dump(mode="json")}
            if (payload.get("action") == "status"
                    and set(payload) in ({"action"}, {"action", "operation_id"})):
                with self.store.locked():
                    if "operation_id" in payload:
                        record = self.store.read(payload["operation_id"])
                        operation = self._reconcile(record) if record else None
                        return {"ok": True, "operation": operation.model_dump(mode="json") if operation else None}
                    records = self.store.records()
                    for record in records:
                        self._reconcile(record)
                    latest = max(records, key=lambda item: item["operation"].updated_at, default=None)
                    return {"ok": True, "operation": latest["operation"].model_dump(mode="json") if latest else None}
            if (
                set(payload) == {"action", "request"}
                and payload["action"] == "prepare"
            ):
                request = NodeUpdatePrepareRequest.model_validate_json(
                    json.dumps(payload["request"])
                )

                prepared = prepare_downloaded_archive(
                    request,
                    store=self.store,
                    service_uid=self.service_uid,
                )

                return {
                    "ok": True,
                    "prepared": prepared.model_dump(mode="json"),
                }
            if set(payload) != {"action", "request"} or payload["action"] != "apply":
                raise NodeUpdateError("invalid_request", "Unsupported Node update action")
            authorization = NodeUpdateAuthorization.model_validate_json(json.dumps(payload["request"]))
            request = authorization.request
            with self.store.locked():
                existing = self.store.read(request.operation_id)
                if existing:
                    if existing["digest"] != request_digest(authorization):
                        raise NodeUpdateError("identity_conflict", "Operation identity has different content")
                    operation = self._reconcile(existing)
                    return {"ok": True, "operation": operation.model_dump(mode="json")}
                records = self.store.records()
                for record in records:
                    if self._reconcile(record).status in ACTIVE_STATES:
                        raise NodeUpdateError("update_busy", "Another Node update needs completion or recovery")
                if len(records) >= MAX_OPERATIONS:
                    raise NodeUpdateError("history_full", "Root must reconcile/prune the bounded operation history")
                self.authorization_verifier(authorization)
                self.validator(request)
                operation = NodeUpdateOperation(operation_id=request.operation_id, device_id=request.device_id,
                    release_id=request.release_id, archive_sha256=request.archive_sha256,
                    status="accepted", updated_at=datetime.now(UTC))
                record = {"request": request, "authorization": authorization,
                          "operation": operation, "digest": request_digest(authorization)}
                self.store.write(record)
                try:
                    self.scheduler.schedule(request.operation_id)
                except Exception:
                    self.store.transition(record, "unknown", error_code="schedule_unknown")
                return {"ok": True, "operation": record["operation"].model_dump(mode="json")}
        except (NodeUpdateError, ValidationError, ValueError, OSError) as exc:
            return {"ok": False, "error": exc.code if isinstance(exc, NodeUpdateError) else "invalid_request"}


def peer_uid(connection):
    """Linux kernel credentials, not an identity supplied in JSON."""
    return struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]


def serve():
    import grp
    import pwd
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise SystemExit("Node update helper must run as root on Linux")
    service_uid = pwd.getpwnam("3mm").pw_uid
    service_gid = grp.getgrnam("3mm").gr_gid
    helper = NodeUpdateHelper(NodeUpdateStore(), service_uid=service_uid)
    trusted_path(SOCKET_PATH.parent, directory=True)
    if SOCKET_PATH.exists() or SOCKET_PATH.is_symlink():
        if not stat.S_ISSOCK(SOCKET_PATH.lstat().st_mode):
            raise NodeUpdateError("unsafe_path", "Existing helper path is not a socket")
        SOCKET_PATH.unlink()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(SOCKET_PATH))
        os.chown(SOCKET_PATH, 0, service_gid)
        os.chmod(SOCKET_PATH, 0o660)
        server.listen(4)
        while True:
            connection, _ = server.accept()
            with connection:
                connection.settimeout(5)
                try:
                    uid = peer_uid(connection)
                    if uid not in {0, service_uid}:
                        response = {"ok": False, "error": "forbidden_peer"}
                    else:
                        request = b""
                        while b"\n" not in request and len(request) <= MAX_REQUEST_BYTES:
                            chunk = connection.recv(1024)
                            if not chunk:
                                break
                            request += chunk
                        if len(request) > MAX_REQUEST_BYTES or b"\n" not in request:
                            raise ValueError("invalid framing")
                        response = helper.handle_request(json.loads(request.split(b"\n", 1)[0]), peer_uid=uid)
                except (OSError, ValueError, NodeUpdateError):
                    response = {"ok": False, "error": "invalid_request"}
                try:
                    connection.sendall(json.dumps(response, separators=(",", ":")).encode() + b"\n")
                except OSError:
                    pass


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    serve()


if __name__ == "__main__":
    main()
