"""Private SDK-file preimages for quiescent, reviewed-native activation rollback.

The lifecycle helper owns the enclosing rollback directory and release lock.
This is not hostile-code isolation or an automatic interrupted-operation replay.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from three_mm_application_sdk.files import (
    ApplicationFileLimits,
    ApplicationFileStorage,
    ApplicationFileStorageError,
    DIGEST,
)


# Accept every SDK-supported quota, not only the default host helper limits.
LIMITS = ApplicationFileLimits(16 * 1024 * 1024, 64 * 1024 * 1024, 1024)
MANIFEST_LIMIT = 256 * 1024


def _write_file(path: Path, content: bytes) -> None:
    # Only called beneath the newly created, helper-owned 0700 rollback directory.
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def capture_private_files(data_root: Path, rollback_root: Path) -> None:
    """Capture a bounded, validated namespace without creating source files."""
    storage = ApplicationFileStorage(data_root, mode="read", limits=LIMITS)
    manifest = {"schema_version": 1, "present": False, "files": []}
    with storage._locked(write=False) as directory:
        if directory is not None:
            manifest["present"] = True
            destination = rollback_root / "sdk-files"
            destination.mkdir(mode=0o700)
            _write_file(destination / ".lock", b"")
            for file_id, size in storage._entries(directory):
                entry = storage._read(directory, file_id)
                if entry is None or len(entry.content) != size:
                    raise ApplicationFileStorageError("Private file snapshot changed")
                _write_file(destination / storage._identity(file_id), entry.content)
                manifest["files"].append(
                    {"file_id": file_id, "size_bytes": size, "sha256": entry.sha256}
                )
            _sync_directory(destination)
    _write_file(
        rollback_root / "files.json",
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    )
    _sync_directory(rollback_root)


def _manifest(rollback_root: Path) -> dict:
    fd = os.open(
        rollback_root / "files.json",
        os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
    )
    with os.fdopen(fd, "rb") as stream:
        info = ApplicationFileStorage._regular(stream.fileno())
        if info.st_size > MANIFEST_LIMIT:
            raise ApplicationFileStorageError("Private file snapshot is invalid")
        content = stream.read(MANIFEST_LIMIT + 1)
    try:
        manifest = json.loads(content)
        if (
            len(content) != info.st_size
            or type(manifest) is not dict
            or set(manifest) != {"schema_version", "present", "files"}
            or type(manifest["schema_version"]) is not int
            or manifest["schema_version"] != 1
            or type(manifest["present"]) is not bool
            or type(manifest["files"]) is not list
            or len(manifest["files"]) > LIMITS.max_files
            or (not manifest["present"] and manifest["files"])
        ):
            raise ValueError()
        identities = []
        total = 0
        for item in manifest["files"]:
            if type(item) is not dict or set(item) != {
                "file_id",
                "size_bytes",
                "sha256",
            }:
                raise ValueError()
            ApplicationFileStorage._identity(item["file_id"])
            if (
                type(item["size_bytes"]) is not int
                or not 0 <= item["size_bytes"] <= LIMITS.max_file_bytes
                or not isinstance(item["sha256"], str)
                or not DIGEST.fullmatch(item["sha256"])
            ):
                raise ValueError()
            identities.append(item["file_id"])
            total += item["size_bytes"]
        if identities != sorted(set(identities)) or total > LIMITS.max_total_bytes:
            raise ValueError()
    except (ValueError, TypeError, KeyError) as exc:
        raise ApplicationFileStorageError("Private file snapshot is invalid") from exc
    return manifest


def restore_private_files(
    data_root: Path,
    rollback_root: Path,
    service_uid: int | None,
    service_gid: int | None,
) -> None:
    """Validate and stage before switching; keep preimage/candidate on any failure.

    The service MUST be confirmed stopped. No recursive copy of unvalidated data,
    no arbitrary data-root deletion and no in-place replay of a partial restore.
    """
    storage = ApplicationFileStorage(rollback_root, mode="read", limits=LIMITS)
    storage._supported()
    manifest = _manifest(rollback_root)
    stage = rollback_root / "restored-sdk-files"
    with storage._locked(write=False) as directory:
        if manifest["present"] != (directory is not None):
            raise ApplicationFileStorageError("Private file snapshot is incomplete")
        if directory is not None:
            expected = [
                (item["file_id"], item["size_bytes"]) for item in manifest["files"]
            ]
            if storage._entries(directory) != expected:
                raise ApplicationFileStorageError("Private file snapshot is incomplete")
            stage.mkdir(
                mode=0o700
            )  # Existing stage means uncertain recovery, not retry.
            _write_file(stage / ".lock", b"")
            for item in manifest["files"]:
                entry = storage._read(directory, item["file_id"])
                if (
                    entry is None
                    or len(entry.content) != item["size_bytes"]
                    or hashlib.sha256(entry.content).hexdigest() != item["sha256"]
                ):
                    raise ApplicationFileStorageError(
                        "Private file snapshot is corrupt"
                    )
                _write_file(stage / storage._identity(entry.file_id), entry.content)
            if service_uid is not None and service_gid is not None:
                for path in stage.iterdir():
                    os.chown(path, service_uid, service_gid, follow_symlinks=False)
                os.chown(stage, service_uid, service_gid, follow_symlinks=False)
            _sync_directory(stage)

    # Descriptor-relative rename detaches the candidate as opaque evidence,
    # including a candidate-created symlink, without following its target.
    data_fd = ApplicationFileStorage(data_root)._open_data()
    rollback_fd = None
    try:
        rollback_fd = storage._open_data()
        try:
            os.stat("candidate-sdk-files", dir_fd=rollback_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ApplicationFileStorageError(
                "Private file restore requires recovery review"
            )
        try:
            os.rename(
                "sdk-files",
                "candidate-sdk-files",
                src_dir_fd=data_fd,
                dst_dir_fd=rollback_fd,
            )
        except FileNotFoundError:
            pass
        os.fsync(data_fd)
        os.fsync(rollback_fd)
        if manifest["present"]:
            os.rename(
                "restored-sdk-files",
                "sdk-files",
                src_dir_fd=rollback_fd,
                dst_dir_fd=data_fd,
            )
            os.fsync(data_fd)
            os.fsync(rollback_fd)
    finally:
        if rollback_fd is not None:
            os.close(rollback_fd)
        os.close(data_fd)
