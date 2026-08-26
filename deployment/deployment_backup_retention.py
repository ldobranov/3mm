#!/usr/bin/env python3
"""Plan or apply bounded cleanup of 3mm deployment state backups."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class BackupRetentionSafetyError(RuntimeError):
    """Raised when backup cleanup cannot prove that a mutation is safe."""


@dataclass(frozen=True)
class BackupInfo:
    name: str
    path: Path
    modified_ns: int
    size_bytes: int


@dataclass(frozen=True)
class BackupRetentionPlan:
    backups_root: Path
    active_release: str
    rollback_release: str
    keep_history: int
    protected: tuple[tuple[BackupInfo, str], ...]
    delete_candidates: tuple[BackupInfo, ...]

    @property
    def reclaimable_bytes(self) -> int:
        return sum(backup.size_bytes for backup in self.delete_candidates)


def create_backup_retention_plan(
    backups: Iterable[BackupInfo],
    *,
    active_release: str,
    rollback_release: str,
    keep_history: int,
) -> BackupRetentionPlan:
    """Create a deterministic plan without touching the filesystem."""
    if keep_history < 0:
        raise ValueError("keep_history must not be negative")

    backup_list = tuple(backups)
    by_name = {backup.name: backup for backup in backup_list}
    if len(by_name) != len(backup_list):
        raise BackupRetentionSafetyError("Duplicate backup names were discovered")
    if active_release not in by_name:
        raise BackupRetentionSafetyError(
            "The active release has no deployment backup; cleanup is blocked"
        )
    if rollback_release not in by_name:
        raise BackupRetentionSafetyError(
            "The rollback release has no deployment backup; cleanup is blocked"
        )
    if rollback_release == active_release:
        raise BackupRetentionSafetyError(
            "The rollback release must differ from the active release"
        )

    reasons = {
        active_release: "active-rollback",
        rollback_release: "rollback-release",
    }
    newest_first = sorted(
        backup_list,
        key=lambda backup: (backup.modified_ns, backup.name),
        reverse=True,
    )
    history_kept = 0
    for backup in newest_first:
        if backup.name in reasons:
            continue
        if history_kept >= keep_history:
            break
        reasons[backup.name] = "recent-recovery"
        history_kept += 1

    protected = tuple(
        (backup, reasons[backup.name])
        for backup in newest_first
        if backup.name in reasons
    )
    delete_candidates = tuple(
        sorted(
            (backup for backup in backup_list if backup.name not in reasons),
            key=lambda backup: (backup.modified_ns, backup.name),
        )
    )
    root = next(iter(backup_list)).path.parent if backup_list else Path(".")
    return BackupRetentionPlan(
        backups_root=root,
        active_release=active_release,
        rollback_release=rollback_release,
        keep_history=keep_history,
        protected=protected,
        delete_candidates=delete_candidates,
    )


def _directory_size(path: Path) -> int:
    total = 0
    for directory, child_directories, files in os.walk(path, followlinks=False):
        directory_path = Path(directory)
        child_directories[:] = [
            name
            for name in child_directories
            if not (directory_path / name).is_symlink()
        ]
        for name in files:
            try:
                total += (directory_path / name).stat(follow_symlinks=False).st_size
            except FileNotFoundError:
                continue
    return total


def _directory_sizes(paths: list[Path]) -> dict[Path, int]:
    if not paths:
        return {}
    try:
        result = subprocess.run(
            ["du", "-sb", "--", *(str(path) for path in paths)],
            check=True,
            capture_output=True,
            text=True,
        )
        sizes: dict[Path, int] = {}
        for line in result.stdout.splitlines():
            size, reported_path = line.split("\t", 1)
            sizes[Path(reported_path)] = int(size)
        if set(sizes) == set(paths):
            return sizes
    except (FileNotFoundError, OSError, subprocess.SubprocessError, ValueError):
        pass
    return {path: _directory_size(path) for path in paths}


def _release_link_name(install_root: Path, link_name: str) -> str:
    resolved_install_root = install_root.resolve(strict=True)
    if resolved_install_root == Path(resolved_install_root.anchor):
        raise BackupRetentionSafetyError(
            "The filesystem root cannot be the install root"
        )
    releases_root = (resolved_install_root / "releases").resolve(strict=True)
    release_link = resolved_install_root / link_name
    if not release_link.is_symlink():
        raise BackupRetentionSafetyError(
            f"The {link_name} release link is missing or unsafe"
        )
    try:
        release = release_link.resolve(strict=True)
    except FileNotFoundError as exc:
        raise BackupRetentionSafetyError(
            f"The {link_name} release link is broken"
        ) from exc
    if release.parent != releases_root or not release.is_dir():
        raise BackupRetentionSafetyError(
            f"The {link_name} release escapes the releases root"
        )
    return release.name


def inspect_backups(
    install_root: Path,
    state_root: Path,
    *,
    keep_history: int,
) -> BackupRetentionPlan:
    active_release = _release_link_name(install_root, "current")
    rollback_release = _release_link_name(install_root, "previous")
    resolved_state_root = state_root.resolve(strict=True)
    if resolved_state_root == Path(resolved_state_root.anchor):
        raise BackupRetentionSafetyError("The filesystem root cannot be the state root")
    backups_root = (resolved_state_root / "deploy-backups").resolve(strict=True)
    if backups_root.parent != resolved_state_root or not backups_root.is_dir():
        raise BackupRetentionSafetyError("Deployment backups escape the state root")

    backup_paths: list[Path] = []
    for path in backups_root.iterdir():
        if path.is_symlink():
            raise BackupRetentionSafetyError(
                f"Unexpected symlink below backups root: {path}"
            )
        if path.is_dir():
            backup_paths.append(path)

    sizes = _directory_sizes(backup_paths)
    backups = [
        BackupInfo(
            name=path.name,
            path=path,
            modified_ns=path.stat(follow_symlinks=False).st_mtime_ns,
            size_bytes=sizes[path],
        )
        for path in backup_paths
    ]
    plan = create_backup_retention_plan(
        backups,
        active_release=active_release,
        rollback_release=rollback_release,
        keep_history=keep_history,
    )
    return BackupRetentionPlan(
        backups_root=backups_root,
        active_release=plan.active_release,
        rollback_release=plan.rollback_release,
        keep_history=plan.keep_history,
        protected=plan.protected,
        delete_candidates=plan.delete_candidates,
    )


def _human_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def print_plan(plan: BackupRetentionPlan, *, apply: bool) -> None:
    print(f"mode={'apply' if apply else 'dry-run'}")
    print(f"backups_root={plan.backups_root}")
    print(f"active_release={plan.active_release}")
    print(f"rollback_release={plan.rollback_release}")
    print(f"keep_history={plan.keep_history}")
    print(f"protected={len(plan.protected)}")
    print(f"delete_candidates={len(plan.delete_candidates)}")
    print(f"reclaimable={_human_size(plan.reclaimable_bytes)}")
    for backup, reason in plan.protected:
        print(f"KEEP {reason:15} {backup.name} {_human_size(backup.size_bytes)}")
    for backup in plan.delete_candidates:
        print(f"DELETE candidate       {backup.name} {_human_size(backup.size_bytes)}")


def _running_as_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


@contextmanager
def exclusive_release_lock(lock_file: Path):
    try:
        import fcntl
    except ImportError as exc:  # pragma: no cover - Linux deployment guard
        raise BackupRetentionSafetyError(
            "Backup mutation locking requires Linux fcntl"
        ) from exc
    try:
        handle = lock_file.open("a+")
    except OSError as exc:
        raise BackupRetentionSafetyError(
            f"Cannot open deployment lock: {lock_file}"
        ) from exc
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BackupRetentionSafetyError(
                "A deployment or retention operation is already running"
            ) from exc
        yield
    finally:
        handle.close()


def apply_backup_retention(
    plan: BackupRetentionPlan,
    *,
    install_root: Path,
) -> int:
    if not _running_as_root():
        raise BackupRetentionSafetyError("Applying backup retention requires root")
    if _release_link_name(install_root, "current") != plan.active_release:
        raise BackupRetentionSafetyError("The active release changed after planning")
    if _release_link_name(install_root, "previous") != plan.rollback_release:
        raise BackupRetentionSafetyError("The rollback release changed after planning")

    protected_names = {backup.name for backup, _reason in plan.protected}
    deleted = 0
    for backup in plan.delete_candidates:
        path = backup.path
        if (
            path.parent != plan.backups_root
            or path.name in protected_names
            or path.is_symlink()
        ):
            raise BackupRetentionSafetyError(f"Refusing unsafe backup path: {path}")
        try:
            path_stat = path.stat(follow_symlinks=False)
        except FileNotFoundError as exc:
            raise BackupRetentionSafetyError(
                f"Backup disappeared before cleanup: {path}"
            ) from exc
        if not stat.S_ISDIR(path_stat.st_mode):
            raise BackupRetentionSafetyError(
                f"Backup candidate is not a directory: {path}"
            )
        shutil.rmtree(path)
        deleted += 1
        print(f"DELETED {backup.name}")
    return deleted


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-root", type=Path, default=Path("/opt/3mm"))
    parser.add_argument("--state-root", type=Path, default=Path("/var/lib/3mm"))
    parser.add_argument(
        "--keep-history",
        type=int,
        default=3,
        help="recent recovery points to retain besides the active rollback backup",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete the displayed candidates; omission is always a dry-run",
    )
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=Path("/run/lock/3mm-release-mutation.lock"),
        help=argparse.SUPPRESS,
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if not _running_as_root():
            raise BackupRetentionSafetyError(
                "Deployment backup inspection requires root"
            )
        if not args.apply:
            plan = inspect_backups(
                args.install_root, args.state_root, keep_history=args.keep_history
            )
            print_plan(plan, apply=False)
            return 0
        with exclusive_release_lock(args.lock_file):
            plan = inspect_backups(
                args.install_root, args.state_root, keep_history=args.keep_history
            )
            print_plan(plan, apply=True)
            deleted = apply_backup_retention(plan, install_root=args.install_root)
    except (OSError, BackupRetentionSafetyError, ValueError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"Deployment backup retention completed: {deleted} backup(s) deleted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
