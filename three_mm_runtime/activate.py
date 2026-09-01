"""Apply the systemd runtime plan derived from persisted provisioning state."""

from __future__ import annotations

import subprocess
from pathlib import Path

from three_mm_provisioning import FileNetworkRecoveryMarker, FileProvisioningStore
from three_mm_runtime.services import DeviceRuntimePlanner, RuntimeService

UNIT_NAMES = {
    RuntimeService.CORE: "3mm-core.service",
    RuntimeService.WEB: "3mm-web.service",
    RuntimeService.AGENT: "3mm-agent.service",
}
SETUP_UNITS = (
    "3mm-network-helper.service",
    "3mm-setup-ap.service",
    "3mm-setup.service",
)
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


def activate(data_dir: Path = Path("/var/lib/3mm/provisioning")) -> None:
    plan = DeviceRuntimePlanner(
        FileProvisioningStore(data_dir),
        FileNetworkRecoveryMarker(data_dir / "network-recovery.json"),
    ).resolve()
    application_units = tuple(UNIT_NAMES.values())
    if plan.includes(RuntimeService.SETUP):
        _systemctl("disable", "--now", *application_units)
        _systemctl("enable", "--now", *SETUP_UNITS)
        return
    if plan.includes(RuntimeService.CORE) and plan.includes(RuntimeService.AGENT):
        _bootstrap_local_agent(data_dir)
    selected = tuple(UNIT_NAMES[item] for item in plan.services)
    unselected = tuple(unit for unit in application_units if unit not in selected)
    _systemctl("disable", "--now", *SETUP_UNITS)
    if unselected:
        _systemctl("disable", "--now", *unselected)
    _systemctl("enable", "--now", *selected)


if __name__ == "__main__":
    activate()
