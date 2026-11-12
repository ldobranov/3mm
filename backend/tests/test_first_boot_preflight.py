from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

import pytest

from deployment import first_boot_preflight as preflight
from deployment.first_boot_preflight import (
    REQUIRED_COMMANDS,
    REQUIRED_RELEASE_FILES,
    _version_numbers,
    run_preflight,
)


@pytest.fixture(autouse=True)
def cgroup_controllers(tmp_path, monkeypatch):
    path = tmp_path / 'cgroup.controllers'
    path.write_bytes(b'cpu memory pids\n')
    monkeypatch.setattr(preflight, 'CGROUP_CONTROLLERS', path)
    return path


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


def test_host_managed_preflight_never_requires_or_probes_network_manager():
    def runner(command):
        assert "nmcli" not in command and "NetworkManager.service" not in command
        return _runner(command)

    checks = run_preflight(command_lookup=_lookup, runner=runner, system_name="Linux",
        machine="x86_64", python_version=(3, 13), python_executable="/usr/bin/python3")
    assert all(check.passed for check in checks)
    assert not any("network-manager" in check.name or "nmcli" in check.name for check in checks)


def test_armv6_hub_requires_the_tested_python_minor():
    for version, expected in (((3, 13, 5), True), ((3, 12, 3), False), ((3, 14, 0), False)):
        checks = run_preflight(command_lookup=_lookup, runner=_runner, system_name="Linux",
            machine="armv6l", python_version=version, python_executable="/usr/bin/python3")
        status = {check.name: check.passed for check in checks}
        assert status["host.architecture"] and status["runtime.python"] is expected


def test_selected_network_manager_requires_its_adapter_before_activation():
    checks = run_preflight(command_lookup=_lookup, runner=_runner, system_name="Linux",
        machine="x86_64", python_version=(3, 13), python_executable="/usr/bin/python3",
        network_backend="network-manager")
    assert not next(check for check in checks if check.name == "command.nmcli").passed


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


@pytest.mark.parametrize("missing", (
    "components/__init__.py", "components/public_web/__init__.py",
    "components/public_web/__main__.py", "components/public_web/server.py",
    "components/public_web/webhook_pilot.py",
    "packages/__init__.py", "packages/provisioning/__init__.py",
    "packages/provisioning/network_recovery.py", "packages/provisioning/network_helper.py",
    "packages/provisioning/setup_access_point.py",
))
def test_incomplete_relocated_package_release_is_not_ready(tmp_path, missing):
    _complete_release(tmp_path)
    (tmp_path / missing).unlink()
    checks = run_preflight(
        release_root=tmp_path, command_lookup=_lookup, runner=_runner,
        system_name="Linux", machine="aarch64", python_version=(3, 13, 5),
        python_executable="/usr/bin/python3",
    )
    failures = [check for check in checks if not check.passed]
    assert len(failures) == 1 and failures[0].name == "release.file." + missing


def test_wired_only_host_allowed_but_missing_frontend_asset_reported(tmp_path: Path) -> None:
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
        machine="x86_64",
        python_version=(3, 13, 5),
        python_executable="/usr/bin/python3",
    )
    failed_names = {check.name for check in checks if not check.passed}

    assert failed_names == {
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


@pytest.mark.parametrize(('controllers', 'level', 'detail'), [
    (b'cpu memory pids\n', 'PASS', 'individual service RAM limits were not verified'),
    (b'cpu memory_extra pids\n', 'WARN', 'configured service RAM limits are not enforced through cgroup v2'),
    (None, 'WARN', 'memory availability could not be verified'),
    (b'cpu memory\x00 pids\n', 'WARN', 'memory availability could not be verified'),
])
def test_cli_memory_advice_does_not_change_ready_result(cgroup_controllers, monkeypatch, capsys,
                                                     controllers, level, detail):
    if controllers is None:
        cgroup_controllers.unlink()
    else:
        cgroup_controllers.write_bytes(controllers)
    monkeypatch.setattr(preflight.sys, 'argv', ['first_boot_preflight.py'])
    monkeypatch.setattr(preflight, 'run_preflight', lambda **options: run_preflight(
        **options, command_lookup=_lookup, runner=_runner, system_name='Linux',
        machine='aarch64', python_version=(3, 13, 5), python_executable='/usr/bin/python3',
    ))
    assert preflight.main() == 0
    lines = capsys.readouterr().out.splitlines()
    assert any(line.startswith(f'{level} resources.cgroup-memory: ') and detail in line for line in lines)
    assert lines[-1] == 'result=ready failed=0'


def test_cli_memory_warning_does_not_hide_required_failure(cgroup_controllers, monkeypatch, capsys):
    cgroup_controllers.write_bytes(b'cpu pids\n')
    monkeypatch.setattr(preflight.sys, 'argv', ['first_boot_preflight.py'])
    monkeypatch.setattr(preflight, 'run_preflight', lambda **options: run_preflight(
        **options, command_lookup=lambda name: None if name == 'node' else _lookup(name),
        runner=_runner, system_name='Linux', machine='aarch64',
        python_version=(3, 13, 5), python_executable='/usr/bin/python3',
    ))
    assert preflight.main() == 1
    lines = capsys.readouterr().out.splitlines()
    assert any(line.startswith('WARN resources.cgroup-memory: ') for line in lines)
    assert 'FAIL command.node: missing' in lines
    assert lines[-1] == 'result=not-ready failed=1'
