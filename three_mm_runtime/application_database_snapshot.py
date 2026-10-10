"""SQLite preimages in the existing quiescent activation rollback directory.

The privileged lifecycle caller owns stop verification and its release lock.
This is not migration authority, a restore endpoint or hostile-native isolation.
No source database is created and no unvalidated snapshot becomes live data.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
import time
from pathlib import Path

from three_mm_application_sdk.relational_wire import canonical
from three_mm_runtime.application_relational_session import _decode

SNAPSHOT_TIMEOUT = 10
_SIDECARS = ("-wal", "-shm", "-journal")


def _directory(path):
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise ValueError("Application snapshot namespace is invalid")


def _regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Application database snapshot requires a single regular file")
    return info


def _sync(path):
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _sync_directory(path):
    if os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _exclusive(path, payload=b""):
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, 0o600)


def _digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _namespace(database):
    _directory(database.parent)
    if os.path.lexists(database):
        _regular(database)
    for suffix in _SIDECARS:
        sidecar = database.with_name(database.name + suffix)
        if os.path.lexists(sidecar):
            _regular(sidecar)
            if not os.path.lexists(database):
                raise ValueError("Application database has orphan sidecars")


def _snapshot_sidecars(snapshot):
    # Verified preimage is one closed backup, not a DB plus an unrecorded WAL
    # that could silently override its checksummed main bytes.
    if any(
        os.path.lexists(snapshot.with_name(snapshot.name + suffix))
        for suffix in _SIDECARS
    ):
        raise ValueError("Application database snapshot has unexpected sidecars")


def _backup(source, destination):
    """Only an existing source; bounded waits, no readonly immutable WAL fiction."""
    deadline = time.monotonic() + SNAPSHOT_TIMEOUT
    reader = sqlite3.connect(
        source.absolute().as_uri() + "?mode=ro", uri=True, timeout=0
    )
    writer = None
    try:
        reader.execute("PRAGMA query_only=ON")
        reader.execute("PRAGMA trusted_schema=OFF")
        reader.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        _exclusive(destination)
        writer = sqlite3.connect(destination, timeout=0)

        def progress(_status, _remaining, _total):
            if time.monotonic() >= deadline:
                raise TimeoutError("Application database snapshot deadline exceeded")

        reader.backup(writer, pages=128, progress=progress, sleep=0.01)
        # Validate copied bytes, without running application callbacks or repairs.
        writer.execute("PRAGMA query_only=ON")
        writer.execute("PRAGMA trusted_schema=OFF")
        writer.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        if writer.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("Application database snapshot is corrupt")
    finally:
        if writer is not None:
            writer.close()
        reader.close()
    _sync(destination)


def capture_database(database: Path, snapshot: Path) -> bool:
    """Capture a verified SQLite preimage or durable, explicit initial absence.

    Caller must have confirmed quiescence. A partial attempt is retained, not
    retried into or mistaken for a complete snapshot.
    """
    _directory(snapshot.parent)
    _namespace(database)
    manifest_path = snapshot.parent / "database.json"
    if os.path.lexists(manifest_path) or os.path.lexists(snapshot):
        raise ValueError("Application database snapshot already exists")
    present = os.path.lexists(database)
    if present:
        _backup(database, snapshot)
        _snapshot_sidecars(snapshot)
    _exclusive(
        manifest_path,
        canonical(
            {
                "version": 1,
                "present": present,
                "size_bytes": snapshot.stat().st_size if present else None,
                "sha256": _digest(snapshot) if present else None,
            }
        ),
    )
    _sync_directory(snapshot.parent)
    return present


def _preimage(snapshot, expected_present):
    if type(expected_present) is not bool:
        raise ValueError("Application database presence evidence is invalid")
    manifest_path = snapshot.parent / "database.json"
    if _regular(manifest_path).st_size > 1024:
        raise ValueError("Application database snapshot manifest is invalid")
    value = _decode(manifest_path.read_bytes(), limit=1024)
    if (
        type(value) is not dict
        or set(value) != {"version", "present", "size_bytes", "sha256"}
        or type(value["version"]) is not int
        or value["version"] != 1
        or type(value["present"]) is not bool
        or value["present"] != expected_present
    ):
        raise ValueError("Application database snapshot manifest is invalid")
    if expected_present:
        size = _regular(snapshot).st_size
        _snapshot_sidecars(snapshot)
        if (
            type(value["size_bytes"]) is not int
            or value["size_bytes"] != size
            or type(value["sha256"]) is not str
            or value["sha256"] != _digest(snapshot)
        ):
            raise ValueError("Application database snapshot is corrupt")
    elif (
        value["size_bytes"] is not None
        or value["sha256"] is not None
        or os.path.lexists(snapshot)
    ):
        raise ValueError("Application database absence evidence is invalid")


def validate_database_restore(database, snapshot, existed):
    """Check evidence before the enclosing DB/files rollback changes either."""
    _directory(snapshot.parent)
    _namespace(database)
    _preimage(snapshot, existed)
    candidates = [
        snapshot.parent / ("candidate-state.sqlite3" + suffix)
        for suffix in ("", *_SIDECARS)
    ]
    if any(
        os.path.lexists(path)
        for path in (snapshot.parent / "restored-state.sqlite3", *candidates)
    ):
        raise ValueError("Application database restore requires recovery review")


def restore_database(database, snapshot, existed, service_uid, service_gid):
    """Stage verified bytes, then detach candidate data as rollback evidence.

    No removal of live WAL, no following links and no new empty preimage. An
    interruption leaves the enclosing rollback marker and both staged/candidate
    evidence for explicit recovery. Normal activation must never retry it.
    """
    validate_database_restore(database, snapshot, existed)
    staged = snapshot.parent / "restored-state.sqlite3"
    candidates = [
        snapshot.parent / ("candidate-state.sqlite3" + suffix)
        for suffix in ("", *_SIDECARS)
    ]
    if existed:
        _backup(snapshot, staged)
        if service_uid is not None and service_gid is not None:
            os.chown(staged, service_uid, service_gid)
        _sync(staged)
    _sync_directory(snapshot.parent)
    for suffix, candidate in zip(("", *_SIDECARS), candidates):
        path = database.with_name(database.name + suffix)
        if os.path.lexists(path):
            os.replace(path, candidate)
            _sync_directory(database.parent)
            _sync_directory(snapshot.parent)
    if existed:
        os.replace(staged, database)
        _sync_directory(database.parent)
        _sync_directory(snapshot.parent)
