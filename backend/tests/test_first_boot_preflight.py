from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

from deployment.first_boot_preflight import (
    REQUIRED_COMMANDS,
    REQUIRED_RELEASE_FILES,
    _version_numbers,
    run_preflight,
)


def _complete_release(root: Path) -> None:
    for relative_path in REQUIRED_RELEASE_FILES:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test\n", encoding="utf-8")
    asset = root / "frontend" / "dist" / "assets" / "app.js"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text("export {}\n", encoding="utf-8")


def _lookup(command: str) -> str | None:
    if command in REQUIRED_COMMANDS:
        return f"/usr/bin/{command}"
    return None


def _runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    key = tuple(command)
    outputs = {
        ("node", "--version"): "v20.19.2\n",
        ("npm", "--version"): "9.2.0\n",
        ("systemctl", "is-active", "NetworkManager.service"): "active\n",
        (
            "nmcli",
            "-t",
            "-f",
            "DEVICE,TYPE,STATE",
            "device",
            "status",
        ): "eth0:ethernet:connected\nwlan0:wifi:connected\n",
        ("/usr/bin/python3", "-m", "venv", "--help"): "usage: venv\n",
    }
    return subprocess.CompletedProcess(command, 0, outputs.get(key, ""), "")


def test_version_parser_accepts_prefixed_versions() -> None:
    assert _version_numbers("v20.19.2") == (20, 19, 2)
    assert _version_numbers("npm 9") == (9,)
    assert _version_numbers("unknown") == ()


def test_baseline_host_and_complete_release_are_ready(tmp_path: Path) -> None:
    _complete_release(tmp_path)

    checks = run_preflight(
        release_root=tmp_path,
        command_lookup=_lookup,
        runner=_runner,
        system_name="Linux",
        machine="aarch64",
        python_version=(3, 13, 5),
        python_executable="/usr/bin/python3",
    )

    assert checks
    assert all(check.passed for check in checks)


def test_missing_wlan0_and_frontend_asset_are_reported(tmp_path: Path) -> None:
    _complete_release(tmp_path)
    (tmp_path / "frontend" / "dist" / "assets" / "app.js").unlink()

    def runner_without_wifi(
        command: Sequence[str],
    ) -> subprocess.CompletedProcess[str]:
        if tuple(command) == (
            "nmcli",
            "-t",
            "-f",
            "DEVICE,TYPE,STATE",
            "device",
            "status",
        ):
            return subprocess.CompletedProcess(
                command,
                0,
                "eth0:ethernet:connected\n",
                "",
            )
        return _runner(command)

    checks = run_preflight(
        release_root=tmp_path,
        command_lookup=_lookup,
        runner=runner_without_wifi,
        system_name="Linux",
        machine="aarch64",
        python_version=(3, 13, 5),
        python_executable="/usr/bin/python3",
    )
    failed_names = {check.name for check in checks if not check.passed}

    assert failed_names == {
        "network.wlan0",
        "release.frontend-javascript",
    }


def test_old_node_version_is_rejected() -> None:
    def old_node_runner(
        command: Sequence[str],
    ) -> subprocess.CompletedProcess[str]:
        if tuple(command) == ("node", "--version"):
            return subprocess.CompletedProcess(command, 0, "v18.20.0\n", "")
        return _runner(command)

    checks = run_preflight(
        command_lookup=_lookup,
        runner=old_node_runner,
        system_name="Linux",
        machine="armv7l",
        python_version=(3, 11, 0),
        python_executable="/usr/bin/python3",
    )

    assert (
        next(check for check in checks if check.name == "runtime.node").passed is False
    )
