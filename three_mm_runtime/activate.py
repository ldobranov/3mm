"""Apply the systemd runtime plan derived from persisted provisioning state."""

from __future__ import annotations

import subprocess
from pathlib import Path
import argparse
import os

from three_mm_provisioning import FileNetworkRecoveryMarker, FileProvisioningStore
from three_mm_runtime.services import DeviceRuntimePlanner, RuntimeService, SetupAccess
from three_mm_runtime.install_profile import InstallProfile, read_install_profile, validate_profile_role, read_network_backend

UNIT_NAMES = {
    RuntimeService.CORE: "3mm-core.service",
    RuntimeService.WEB: "3mm-web.service",
    RuntimeService.AGENT: "3mm-agent.service",
}
PUBLIC_WEB_SOCKET_UNIT = "3mm-public-web.socket"
PLATFORM_RUNTIME_UNIT = "3mm-platform-runtime.service"
CONNECTOR_WORKER_UNIT = "3mm-connector-worker.service"

SETUP_UNITS = (
    "3mm-network-helper.service",
    "3mm-setup-ap.service",
    "3mm-setup.service",
)
LOCAL_SETUP_UNIT = "3mm-setup-local.service"
ALL_SETUP_UNITS = (*SETUP_UNITS, LOCAL_SETUP_UNIT)
RELEASE_ROOT = Path("/opt/3mm/current")
AGENT_DATA_DIR = Path("/var/lib/3mm/agent")
CORE_DATABASE = Path("/var/lib/3mm/core/3mm.db")


def _systemctl(*arguments: str) -> None:
    subprocess.run(
        ("/usr/bin/systemctl", *arguments),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _require_setup_interface() -> None:
    from three_mm_provisioning.network_capabilities import setup_interface
    setup_interface(os.getenv("THREE_MM_SETUP_INTERFACE"))


def _bootstrap_local_agent(
    provisioning_data_dir: Path,
    release_root: Path = RELEASE_ROOT,
) -> None:
    python = release_root / ".venv/bin/python"
    subprocess.run(
        (
            "/usr/sbin/runuser",
            "-u",
            "3mm",
            "--",
            "/usr/bin/env",
            f"DATABASE_URL=sqlite:///{CORE_DATABASE.as_posix()}",
            f"PYTHONPATH={release_root}",
            str(python),
            str(release_root / "deployment/bootstrap-local-agent.py"),
            "--automatic",
            "--agent-data-dir",
            str(AGENT_DATA_DIR),
            "--provisioning-data-dir",
            str(provisioning_data_dir),
        ),
        check=True,
        timeout=60,
    )


def _activate(data_dir: Path, *, bootstrap_agent: bool = True) -> None:
    plan = DeviceRuntimePlanner(
        FileProvisioningStore(data_dir),
        FileNetworkRecoveryMarker(data_dir / "network-recovery.json"),
        network_backend=read_network_backend(),
    ).resolve()
    profile = read_install_profile(RELEASE_ROOT)
    validate_profile_role(profile, plan.role)
    application_units = (
        (UNIT_NAMES[RuntimeService.AGENT],)
        if profile is InstallProfile.NODE
        else tuple(UNIT_NAMES.values()) + (PUBLIC_WEB_SOCKET_UNIT, PLATFORM_RUNTIME_UNIT, CONNECTOR_WORKER_UNIT)
    )
    if plan.setup_access is SetupAccess.ACCESS_POINT:
        # Check before stopping a working Core/Agent. AP startup is a Linux
        # adapter concern, not a generic Device/Node Platform requirement.
        try:
            _require_setup_interface()
        except Exception:
            from dataclasses import replace
            plan = replace(plan, setup_access=SetupAccess.LOCAL)
        else:
            _systemctl("disable", "--now", *application_units)
            _systemctl("disable", "--now", LOCAL_SETUP_UNIT)
            _systemctl("enable", "--now", *SETUP_UNITS)
            return
    if (bootstrap_agent and plan.includes(RuntimeService.CORE) and plan.includes(RuntimeService.AGENT)
            and not plan.includes(RuntimeService.SETUP)):
        _bootstrap_local_agent(data_dir)
    selected = tuple(UNIT_NAMES[item] for item in plan.services if item is not RuntimeService.SETUP)
    if profile is InstallProfile.FULL and plan.includes(RuntimeService.CORE):
        selected += (PUBLIC_WEB_SOCKET_UNIT, PLATFORM_RUNTIME_UNIT, CONNECTOR_WORKER_UNIT)
    unselected = tuple(unit for unit in application_units if unit not in selected)
    _systemctl("disable", "--now", *(SETUP_UNITS if plan.includes(RuntimeService.SETUP) else ALL_SETUP_UNITS))
    if unselected:
        _systemctl("disable", "--now", *unselected)
    if selected:
        _systemctl("enable", "--now", *selected)
    if plan.setup_access is SetupAccess.LOCAL:
        _systemctl("enable", "--now", "3mm-network-helper.service", LOCAL_SETUP_UNIT)


def _wait_setup_ready(data_dir: Path) -> None:
    import time
    from deployment.service_component import _http_identity

    plan = DeviceRuntimePlanner(FileProvisioningStore(data_dir)).resolve()
    deadline = time.monotonic() + 90
    while True:
        try:
            if plan.includes(RuntimeService.CORE):
                if _http_identity('http://127.0.0.1:8887/health', timeout=min(1, max(.01, deadline-time.monotonic()))).get('status') != 'ok':
                    raise ValueError('Core is not ready')
            if plan.includes(RuntimeService.AGENT):
                if _http_identity('http://127.0.0.1:8890/api/v1/agent/hello', timeout=min(1, max(.01, deadline-time.monotonic()))).get('role') != plan.role.value:
                    raise ValueError('Agent role is not ready')
            return
        except (OSError, ValueError):
            if time.monotonic() >= deadline:
                raise RuntimeError('Setup runtime readiness deadline exceeded') from None
            time.sleep(.2)


def activate(data_dir: Path = Path('/var/lib/3mm/provisioning'), *, bootstrap_agent: bool = True) -> None:
    from three_mm_provisioning.setup_journal import SetupActivationJournal

    journal = SetupActivationJournal(data_dir)
    attempt = journal.load()
    _activate(data_dir, bootstrap_agent=bootstrap_agent)
    if attempt is not None and attempt['committed']:
        _wait_setup_ready(data_dir)
        check_active(data_dir)
        with journal.locked():
            if journal.load() != attempt:
                raise RuntimeError('Setup transaction changed during activation')
            journal.clear()


def check_active(data_dir: Path = Path("/var/lib/3mm/provisioning")) -> None:
    plan = DeviceRuntimePlanner(
        FileProvisioningStore(data_dir),
        FileNetworkRecoveryMarker(data_dir / "network-recovery.json"),
        network_backend=read_network_backend(),
    ).resolve()
    units = tuple(UNIT_NAMES[s] for s in plan.services if s is not RuntimeService.SETUP)
    if plan.setup_access is SetupAccess.ACCESS_POINT:
        try:
            _require_setup_interface()
        except Exception:
            units += ("3mm-network-helper.service", LOCAL_SETUP_UNIT)
        else:
            units += SETUP_UNITS
    elif plan.setup_access is SetupAccess.LOCAL:
        units += ("3mm-network-helper.service", LOCAL_SETUP_UNIT)
    if plan.includes(RuntimeService.CORE):
        units += (PUBLIC_WEB_SOCKET_UNIT, PLATFORM_RUNTIME_UNIT, CONNECTOR_WORKER_UNIT)
    for unit in units:
        _systemctl("is-active", "--quiet", unit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-active", action="store_true")
    parser.add_argument("--no-bootstrap-agent", action="store_true")
    arguments = parser.parse_args()
    check_active() if arguments.check_active else activate(bootstrap_agent=not arguments.no_bootstrap_agent)
