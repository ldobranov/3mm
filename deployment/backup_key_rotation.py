#!/usr/bin/env python3
"""Guarded rotation of the device backup encryption key (M15).

The backup key at ``/etc/3mm/backup.key`` encrypts every local archive. Rotating
it silently would make all existing archives unreadable, so this helper refuses
to rotate while encrypted archives still exist unless the operator explicitly
acknowledges that those archives become orphaned.

It never deletes archives, never touches the database and never runs as part of
an unrelated operation. The new key is written atomically with mode 0600.
"""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

BACKUP_ROOT = Path("/var/lib/3mm/backups")
KEY_FILE = Path("/etc/3mm/backup.key")
# Shared with create_backup/restore_backup/update apply. Rotation must never run
# concurrently with a backup or restore, or a new archive could be written with
# the old key while the new key is already published.
MUTATION_LOCK = Path("/run/lock/3mm-release-mutation.lock")
ARCHIVE_SUFFIX = ".3mmbak"
KEY_BYTES = 32


class BackupKeyRotationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RotationPlan:
    key_file: Path
    archive_count: int
    can_rotate: bool
    reason: str


def _archives(backup_root: Path) -> list[Path]:
    if not backup_root.exists():
        return []
    if backup_root.is_symlink() or not backup_root.is_dir():
        raise BackupKeyRotationError("Backup root is not a regular directory")
    return sorted(
        path
        for path in backup_root.glob(f"*{ARCHIVE_SUFFIX}")
        if path.is_file() and not path.is_symlink()
    )


def plan_rotation(
    backup_root: Path,
    key_file: Path,
    *,
    acknowledge_orphaned_archives: bool,
) -> RotationPlan:
    """Decide whether rotation is safe without changing anything."""
    archives = _archives(backup_root)
    if archives and not acknowledge_orphaned_archives:
        return RotationPlan(
            key_file=key_file,
            archive_count=len(archives),
            can_rotate=False,
            reason=(
                "Existing encrypted archives would become unreadable; "
                "re-export or remove them, or pass the explicit acknowledgement"
            ),
        )
    return RotationPlan(
        key_file=key_file,
        archive_count=len(archives),
        can_rotate=True,
        reason="Rotation is safe",
    )


def rotate_key(
    backup_root: Path,
    key_file: Path,
    *,
    acknowledge_orphaned_archives: bool,
) -> RotationPlan:
    """Atomically replace the backup key after the safety plan allows it."""
    plan = plan_rotation(
        backup_root,
        key_file,
        acknowledge_orphaned_archives=acknowledge_orphaned_archives,
    )
    if not plan.can_rotate:
        raise BackupKeyRotationError(plan.reason)
    key_file.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    temporary = key_file.with_name(key_file.name + ".new")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(os.urandom(KEY_BYTES))
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, key_file)
    finally:
        temporary.unlink(missing_ok=True)
    return plan


@contextmanager
def exclusive_mutation_lock(lock_file: Path):
    """Serialize rotation with backup/restore/update via the shared lock."""
    try:
        import fcntl
    except ImportError as exc:  # pragma: no cover - Linux deployment guard
        raise BackupKeyRotationError(
            "Backup key rotation locking requires Linux fcntl"
        ) from exc
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = lock_file.open("w", encoding="ascii")
    except OSError as exc:
        raise BackupKeyRotationError(
            f"Cannot open the shared mutation lock: {lock_file}"
        ) from exc
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BackupKeyRotationError(
                "Another 3mm mutation (backup/restore/update) is already running"
            ) from exc
        yield
    finally:
        handle.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-root", type=Path, default=BACKUP_ROOT)
    parser.add_argument("--key-file", type=Path, default=KEY_FILE)
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=MUTATION_LOCK,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--acknowledge-orphaned-archives",
        action="store_true",
        help="required when existing encrypted archives would become unreadable",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the rotation; omission is a dry run",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if not args.apply:
            plan = plan_rotation(
                args.backup_root,
                args.key_file,
                acknowledge_orphaned_archives=args.acknowledge_orphaned_archives,
            )
            print(
                f"mode=dry-run can_rotate={plan.can_rotate} "
                f"archives={plan.archive_count}"
            )
            print(plan.reason)
            return 0
        if not (hasattr(os, "geteuid") and os.geteuid() == 0):
            raise BackupKeyRotationError("Backup key rotation requires root")
        with exclusive_mutation_lock(args.lock_file):
            plan = rotate_key(
                args.backup_root,
                args.key_file,
                acknowledge_orphaned_archives=args.acknowledge_orphaned_archives,
            )
    except (OSError, BackupKeyRotationError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"Backup key rotated; {plan.archive_count} archive(s) now orphaned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
