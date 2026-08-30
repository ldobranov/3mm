#!/usr/bin/env python3
"""Reset 3mm persistent application state and return to first-boot setup."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Protocol, Sequence

STATE_ROOT = Path("/var/lib/3mm")
INSTALL_ROOT = Path("/opt/3mm")
CURRENT_LINK = INSTALL_ROOT / "current"
APPLICATION_KEY_ROOT = Path("/etc/3mm/application-extensions")
MUTATION_LOCK = Path("/run/lock/3mm-release-mutation.lock")
RESET_CHILDREN = (
    "agent",
    "core",
    "deploy-backups",
    "provisioning",
    "update-helper",
    "application-extensions",
)
RUNTIME_SERVICES = (
    "3mm-agent.service",
    "3mm-core.service",
    "3mm-web.service",
    "3mm-setup.service",
    "3mm-setup-ap.service",
    "3mm-network-helper.service",
    "3mm-application-extension@*.service",
)


class FactoryResetError(RuntimeError):
    """The fixed factory-reset operation could not complete safely."""


class CommandRunner(Protocol):
    def run(self, arguments: Sequence[str]) -> None: ...


class SubprocessCommandRunner:
    def run(self, arguments: Sequence[str]) -> None:
        subprocess.run(
            list(arguments),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
        )


def validate_factory_paths(
    state_root: Path = STATE_ROOT,
    current_link: Path = CURRENT_LINK,
) -> Path:
    if state_root != STATE_ROOT or current_link != CURRENT_LINK:
        raise FactoryResetError("Factory reset paths are not the production paths")
    try:
        release = current_link.resolve(strict=True)
        release.relative_to(INSTALL_ROOT / "releases")
    except (OSError, ValueError) as exc:
        raise FactoryResetError("Current release is not an immutable 3mm release") from exc
    return release


def _remove_persistent_children(state_root: Path) -> None:
    for name in RESET_CHILDREN:
        target = state_root / name
        if target.is_symlink() or target.is_file():
            target.unlink(missing_ok=True)
        elif target.is_dir():
            shutil.rmtree(target)


def _remove_application_keys(key_root: Path = APPLICATION_KEY_ROOT) -> None:
    if key_root.is_symlink() or key_root.is_file():
        key_root.unlink(missing_ok=True)
    elif key_root.is_dir():
        shutil.rmtree(key_root)


def _prepare_state_directories(
    state_root: Path, uid: int, gid: int, application_gid: int
) -> None:
    directories = {
        state_root: 0o750,
        state_root / "agent": 0o700,
        state_root / "core": 0o750,
        state_root / "core" / "uploads": 0o750,
        state_root / "core" / "uploads" / "modules": 0o750,
        state_root / "core" / "extensions" / "backend": 0o750,
        state_root / "core" / "extensions" / "frontend": 0o750,
        state_root / "core" / "extensions" / "compiled": 0o750,
        state_root / "core" / "update-staging": 0o700,
        state_root / "provisioning": 0o750,
    }
    for path, mode in directories.items():
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, uid, gid)
        os.chmod(path, mode)
    helper_state = state_root / "update-helper"
    helper_state.mkdir(parents=True, exist_ok=True)
    os.chown(helper_state, 0, gid)
    os.chmod(helper_state, 0o750)
    application_state = state_root / "application-extensions"
    application_state.mkdir(parents=True, exist_ok=True)
    os.chown(application_state, 0, application_gid)
    os.chmod(application_state, 0o750)
    APPLICATION_KEY_ROOT.mkdir(parents=True, exist_ok=True)
    os.chown(APPLICATION_KEY_ROOT, 0, application_gid)
    os.chmod(APPLICATION_KEY_ROOT, 0o750)


def perform_factory_reset(
    *,
    release: Path,
    runner: CommandRunner | None = None,
    state_root: Path = STATE_ROOT,
) -> None:
    command_runner = runner or SubprocessCommandRunner()
    import grp
    import pwd

    uid = pwd.getpwnam("3mm").pw_uid
    gid = grp.getgrnam("3mm").gr_gid
    application_gid = grp.getgrnam("3mm-app").gr_gid
    command_runner.run(("/usr/bin/systemctl", "stop", *RUNTIME_SERVICES))
    _remove_persistent_children(state_root)
    _remove_application_keys()
    _prepare_state_directories(state_root, uid, gid, application_gid)

    environment = (
        "DATABASE_URL=sqlite:////var/lib/3mm/core/3mm.db",
        "UPLOADS_DIR=/var/lib/3mm/core/uploads",
        "BACKEND_EXTENSIONS_DIR=/var/lib/3mm/core/extensions/backend",
        "FRONTEND_EXTENSIONS_DIR=/var/lib/3mm/core/extensions/frontend",
        "COMPILED_UI_ARTIFACTS_DIR=/var/lib/3mm/core/extensions/compiled",
        f"PYTHONPATH={release}",
    )
    python = release / ".venv" / "bin" / "python"
    command_runner.run(
        (
            "/usr/sbin/runuser",
            "-u",
            "3mm",
            "--",
            "/usr/bin/env",
            *environment,
            str(python),
            str(release / "deployment" / "migrate_database.py"),
        )
    )
    command_runner.run(
        (
            "/usr/sbin/runuser",
            "-u",
            "3mm",
            "--",
            "/usr/bin/env",
            environment[0],
            f"PYTHONPATH={release}",
            str(python),
            "-m",
            "backend.scripts.bootstrap_admin",
            "--create-development-default-if-empty",
        )
    )
    command_runner.run(
        (
            "/usr/bin/env",
            f"PYTHONPATH={release}",
            str(python),
            "-m",
            "three_mm_runtime.activate",
        )
    )


def main() -> None:
    import fcntl

    if getattr(os, "geteuid", lambda: 1)() != 0:
        raise SystemExit("Factory reset must run as root")
    release = validate_factory_paths()
    MUTATION_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with MUTATION_LOCK.open("w", encoding="ascii") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("Another 3mm mutation is already running") from exc
        perform_factory_reset(release=release)


if __name__ == "__main__":
    main()
