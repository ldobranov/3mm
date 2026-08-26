#!/usr/bin/env python3
"""Plan or apply bounded cleanup of immutable 3mm application releases."""

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


class RetentionSafetyError(RuntimeError):
    """Raised when release cleanup cannot prove that a mutation is safe."""


@dataclass(frozen=True)
class ReleaseInfo:
    name: str
    path: Path
    modified_ns: int
    size_bytes: int


@dataclass(frozen=True)
class RetentionPlan:
    releases_root: Path
    current_release: str
    rollback_release: str | None
    keep_history: int
    protected: tuple[tuple[ReleaseInfo, str], ...]
    delete_candidates: tuple[ReleaseInfo, ...]

    @property
    def reclaimable_bytes(self) -> int:
        return sum(release.size_bytes for release in self.delete_candidates)

    @property
    def can_apply(self) -> bool:
        return self.rollback_release is not None


def create_retention_plan(
    releases: Iterable[ReleaseInfo],
    *,
    current_release: str,
    rollback_release: str | None,
    keep_history: int,
) -> RetentionPlan:
    """Create a deterministic plan without touching the filesystem."""
    if keep_history < 0:
        raise ValueError("keep_history must not be negative")

    release_list = tuple(releases)
    by_name = {release.name: release for release in release_list}
    if len(by_name) != len(release_list):
        raise RetentionSafetyError("Duplicate release names were discovered")
    if current_release not in by_name:
        raise RetentionSafetyError(
            "The active release is not present below the releases root"
        )
    if rollback_release is not None and rollback_release not in by_name:
        raise RetentionSafetyError(
            "The rollback release is not present below the releases root"
        )
    if rollback_release == current_release:
        raise RetentionSafetyError(
            "The rollback release must differ from the active release"
        )

    reasons = {current_release: "active"}
    if rollback_release is not None:
        reasons[rollback_release] = "rollback"

    newest_first = sorted(
        release_list,
        key=lambda release: (release.modified_ns, release.name),
        reverse=True,
    )
    history_kept = 0
    for release in newest_first:
        if release.name in reasons:
            continue
        if history_kept >= keep_history:
            break
        reasons[release.name] = "recent-history"
        history_kept += 1

    protected = tuple(
        (release, reasons[release.name])
        for release in newest_first
        if release.name in reasons
    )
    delete_candidates = tuple(
        sorted(
            (release for release in release_list if release.name not in reasons),
            key=lambda release: (release.modified_ns, release.name),
        )
    )
    return RetentionPlan(
        releases_root=(
            next(iter(release_list)).path.parent if release_list else Path(".")
        ),
        current_release=current_release,
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
    """Use the platform's optimized disk walker, with a stdlib fallback."""
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


def _resolve_release_link(
    link: Path,
    releases_root: Path,
    *,
    required: bool,
) -> str | None:
    if not link.is_symlink():
        if link.exists() or required:
            raise RetentionSafetyError(f"Expected a release symlink at {link}")
        return None
    try:
        target = link.resolve(strict=True)
    except FileNotFoundError as exc:
        raise RetentionSafetyError(f"Release symlink is broken: {link}") from exc
    if target.parent != releases_root or not target.is_dir():
        raise RetentionSafetyError(
            f"Release symlink escapes the immutable releases root: {link} -> {target}"
        )
    return target.name


def inspect_releases(
    install_root: Path,
    *,
    keep_history: int,
) -> RetentionPlan:
    resolved_install_root = install_root.resolve(strict=True)
    if resolved_install_root == Path(resolved_install_root.anchor):
        raise RetentionSafetyError(
            "The filesystem root cannot be used as the install root"
        )
    releases_root = (resolved_install_root / "releases").resolve(strict=True)
    if releases_root.parent != resolved_install_root or not releases_root.is_dir():
        raise RetentionSafetyError("The releases directory is outside the install root")

    current_release = _resolve_release_link(
        resolved_install_root / "current", releases_root, required=True
    )
    rollback_release = _resolve_release_link(
        resolved_install_root / "previous", releases_root, required=False
    )
    assert current_release is not None

    release_paths: list[Path] = []
    for path in releases_root.iterdir():
        if path.is_symlink():
            raise RetentionSafetyError(
                f"Unexpected symlink below releases root: {path}"
            )
        if not path.is_dir():
            continue
        release_paths.append(path)

    sizes = _directory_sizes(release_paths)
    releases: list[ReleaseInfo] = []
    for path in release_paths:
        path_stat = path.stat(follow_symlinks=False)
        releases.append(
            ReleaseInfo(
                name=path.name,
                path=path,
                modified_ns=path_stat.st_mtime_ns,
                size_bytes=sizes[path],
            )
        )

    plan = create_retention_plan(
        releases,
        current_release=current_release,
        rollback_release=rollback_release,
        keep_history=keep_history,
    )
    return RetentionPlan(
        releases_root=releases_root,
        current_release=plan.current_release,
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


def print_plan(plan: RetentionPlan, *, apply: bool) -> None:
    mode = "apply" if apply else "dry-run"
    print(f"mode={mode}")
    print(f"releases_root={plan.releases_root}")
    print(f"active={plan.current_release}")
    print(f"rollback={plan.rollback_release or 'missing'}")
    print(f"keep_history={plan.keep_history}")
    print(f"protected={len(plan.protected)}")
    print(f"delete_candidates={len(plan.delete_candidates)}")
    print(f"reclaimable={_human_size(plan.reclaimable_bytes)}")
    for release, reason in plan.protected:
        print(f"KEEP {reason:14} {release.name} {_human_size(release.size_bytes)}")
    for release in plan.delete_candidates:
        print(f"DELETE candidate      {release.name} {_human_size(release.size_bytes)}")


def _running_as_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


@contextmanager
def exclusive_release_lock(lock_file: Path):
    """Prevent cleanup from racing an immutable release deployment."""
    try:
        import fcntl
    except ImportError as exc:  # pragma: no cover - Linux deployment guard
        raise RetentionSafetyError(
            "Release mutation locking requires Linux fcntl"
        ) from exc

    try:
        handle = lock_file.open("a+")
    except OSError as exc:
        raise RetentionSafetyError(
            f"Cannot open release mutation lock: {lock_file}"
        ) from exc
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RetentionSafetyError(
                "A deployment or release cleanup is already running"
            ) from exc
        yield
    finally:
        handle.close()


def apply_retention(plan: RetentionPlan, *, install_root: Path) -> int:
    if not _running_as_root():
        raise RetentionSafetyError("Applying release retention requires root")
    if not plan.can_apply:
        raise RetentionSafetyError(
            "No explicit rollback release exists; run one successful deployment first"
        )

    current_release = _resolve_release_link(
        install_root / "current", plan.releases_root, required=True
    )
    rollback_release = _resolve_release_link(
        install_root / "previous", plan.releases_root, required=True
    )
    if (
        current_release != plan.current_release
        or rollback_release != plan.rollback_release
    ):
        raise RetentionSafetyError(
            "Release links changed after the retention plan was created"
        )

    protected_names = {release.name for release, _reason in plan.protected}
    deleted = 0
    for release in plan.delete_candidates:
        path = release.path
        if (
            path.parent != plan.releases_root
            or path.name in protected_names
            or path.is_symlink()
        ):
            raise RetentionSafetyError(f"Refusing unsafe release path: {path}")
        try:
            path_stat = path.stat(follow_symlinks=False)
        except FileNotFoundError as exc:
            raise RetentionSafetyError(
                f"Release disappeared before cleanup: {path}"
            ) from exc
        if not stat.S_ISDIR(path_stat.st_mode):
            raise RetentionSafetyError(f"Release candidate is not a directory: {path}")
        shutil.rmtree(path)
        deleted += 1
        print(f"DELETED {release.name}")
    return deleted


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-root", type=Path, default=Path("/opt/3mm"))
    parser.add_argument(
        "--keep-history",
        type=int,
        default=3,
        help="additional recent releases to retain besides active and rollback",
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
        if not args.apply:
            plan = inspect_releases(args.install_root, keep_history=args.keep_history)
            print_plan(plan, apply=False)
            if not plan.can_apply:
                print(
                    "NOTICE: apply is blocked until an explicit rollback release exists"
                )
            return 0
        if not _running_as_root():
            raise RetentionSafetyError("Applying release retention requires root")
        with exclusive_release_lock(args.lock_file):
            plan = inspect_releases(args.install_root, keep_history=args.keep_history)
            print_plan(plan, apply=True)
            deleted = apply_retention(
                plan, install_root=args.install_root.resolve(strict=True)
            )
    except (OSError, RetentionSafetyError, ValueError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"Release retention completed: {deleted} release(s) deleted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
