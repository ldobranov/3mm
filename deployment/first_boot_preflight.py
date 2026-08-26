#!/usr/bin/env python3
"""Read-only host and release checks for a first 3mm Raspberry deployment."""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


MINIMUM_PYTHON = (3, 10)
MINIMUM_NODE_MAJOR = 20
SUPPORTED_RASPBERRY_ARCHITECTURES = frozenset({"aarch64", "armv7l"})
REQUIRED_COMMANDS = (
    "bash",
    "flock",
    "nmcli",
    "node",
    "npm",
    "python3",
    "systemctl",
    "tar",
)
REQUIRED_RELEASE_FILES = (
    "backend/requirements.txt",
    "deployment/install-systemd.sh",
    "deployment/migrate_database.py",
    "deployment/systemd/3mm-agent.service",
    "deployment/systemd/3mm-core.service",
    "deployment/systemd/3mm-network-helper.service",
    "deployment/systemd/3mm-setup-ap.service",
    "deployment/systemd/3mm-setup.service",
    "deployment/systemd/3mm-web.service",
    "frontend/compiler/package.json",
    "frontend/dist/index.html",
)


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    name: str
    passed: bool
    detail: str


CommandLookup = Callable[[str], str | None]
CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )


def _version_numbers(value: str) -> tuple[int, ...]:
    match = re.search(r"(\d+(?:\.\d+)+|\d+)", value)
    if match is None:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def _command_output(command: Sequence[str], runner: CommandRunner) -> tuple[bool, str]:
    try:
        result = runner(command)
    except OSError as exc:
        return False, str(exc)
    output = (result.stdout or result.stderr).strip()
    return result.returncode == 0, output


def inspect_host(
    *,
    command_lookup: CommandLookup = shutil.which,
    runner: CommandRunner = _run,
    system_name: str | None = None,
    machine: str | None = None,
    python_version: tuple[int, ...] | None = None,
    python_executable: str | None = None,
) -> list[PreflightCheck]:
    """Inspect the host without changing packages, services or networking."""
    checks: list[PreflightCheck] = []
    resolved_system = system_name or platform.system()
    resolved_machine = (machine or platform.machine()).lower()
    resolved_python = python_version or tuple(sys.version_info[:3])
    resolved_executable = python_executable or sys.executable

    checks.append(
        PreflightCheck(
            "host.os",
            resolved_system == "Linux",
            resolved_system,
        )
    )
    checks.append(
        PreflightCheck(
            "host.architecture",
            resolved_machine in SUPPORTED_RASPBERRY_ARCHITECTURES,
            resolved_machine,
        )
    )
    checks.append(
        PreflightCheck(
            "runtime.python",
            resolved_python >= MINIMUM_PYTHON,
            ".".join(str(part) for part in resolved_python),
        )
    )

    commands: dict[str, str | None] = {}
    for command in REQUIRED_COMMANDS:
        commands[command] = command_lookup(command)
        checks.append(
            PreflightCheck(
                f"command.{command}",
                commands[command] is not None,
                commands[command] or "missing",
            )
        )

    venv_ok, venv_output = _command_output(
        [resolved_executable, "-m", "venv", "--help"], runner
    )
    checks.append(
        PreflightCheck(
            "runtime.venv",
            venv_ok,
            "available" if venv_ok else (venv_output or "unavailable"),
        )
    )

    if commands["node"] is not None:
        node_ok, node_output = _command_output(["node", "--version"], runner)
        node_version = _version_numbers(node_output)
        supported_node = (
            node_ok and bool(node_version) and node_version[0] >= MINIMUM_NODE_MAJOR
        )
        checks.append(
            PreflightCheck(
                "runtime.node",
                supported_node,
                node_output or "version unavailable",
            )
        )

    if commands["npm"] is not None:
        npm_ok, npm_output = _command_output(["npm", "--version"], runner)
        checks.append(
            PreflightCheck(
                "runtime.npm",
                npm_ok and bool(_version_numbers(npm_output)),
                npm_output or "version unavailable",
            )
        )

    if commands["systemctl"] is not None:
        manager_ok, manager_output = _command_output(
            ["systemctl", "is-active", "NetworkManager.service"], runner
        )
        checks.append(
            PreflightCheck(
                "network.network-manager",
                manager_ok and manager_output == "active",
                manager_output or "inactive",
            )
        )

    if commands["nmcli"] is not None:
        wifi_ok, wifi_output = _command_output(
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"],
            runner,
        )
        wlan0_state = next(
            (
                line.split(":", 2)[2]
                for line in wifi_output.splitlines()
                if line.startswith("wlan0:wifi:")
            ),
            None,
        )
        checks.append(
            PreflightCheck(
                "network.wlan0",
                wifi_ok and wlan0_state is not None,
                wlan0_state or "wlan0 Wi-Fi interface missing",
            )
        )

    return checks


def inspect_release(release_root: Path) -> list[PreflightCheck]:
    """Check the files needed by the immutable installer without modifying them."""
    root = release_root.resolve()
    if not root.is_dir():
        return [PreflightCheck("release.root", False, f"missing directory: {root}")]

    checks = [PreflightCheck("release.root", True, str(root))]
    for relative_path in REQUIRED_RELEASE_FILES:
        present = (root / relative_path).is_file()
        checks.append(
            PreflightCheck(
                f"release.file.{relative_path}",
                present,
                "present" if present else "missing",
            )
        )

    assets_root = root / "frontend" / "dist" / "assets"
    javascript_assets = tuple(assets_root.glob("*.js")) if assets_root.is_dir() else ()
    checks.append(
        PreflightCheck(
            "release.frontend-javascript",
            bool(javascript_assets),
            f"{len(javascript_assets)} JavaScript asset(s)",
        )
    )
    return checks


def run_preflight(
    *,
    release_root: Path | None = None,
    command_lookup: CommandLookup = shutil.which,
    runner: CommandRunner = _run,
    system_name: str | None = None,
    machine: str | None = None,
    python_version: tuple[int, ...] | None = None,
    python_executable: str | None = None,
) -> list[PreflightCheck]:
    checks = inspect_host(
        command_lookup=command_lookup,
        runner=runner,
        system_name=system_name,
        machine=machine,
        python_version=python_version,
        python_executable=python_executable,
    )
    if release_root is not None:
        checks.extend(inspect_release(release_root))
    return checks


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-root",
        type=Path,
        help="also validate an extracted 3mm release, for example /opt/3mm/current",
    )
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    checks = run_preflight(release_root=arguments.release_root)
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"{status} {check.name}: {check.detail}")
    failed = sum(not check.passed for check in checks)
    print(f"result={'ready' if failed == 0 else 'not-ready'} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
