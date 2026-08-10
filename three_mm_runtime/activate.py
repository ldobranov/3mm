"""Apply the systemd runtime plan derived from persisted provisioning state."""

from __future__ import annotations

import subprocess
from pathlib import Path

from three_mm_provisioning import FileProvisioningStore
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


def _systemctl(*arguments: str) -> None:
    subprocess.run(
        ("/usr/bin/systemctl", *arguments),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def activate(data_dir: Path = Path("/var/lib/3mm/provisioning")) -> None:
    plan = DeviceRuntimePlanner(FileProvisioningStore(data_dir)).resolve()
    application_units = tuple(UNIT_NAMES.values())
    if plan.includes(RuntimeService.SETUP):
        _systemctl("disable", "--now", *application_units)
        _systemctl("enable", "--now", *SETUP_UNITS)
        return
    selected = tuple(UNIT_NAMES[item] for item in plan.services)
    unselected = tuple(unit for unit in application_units if unit not in selected)
    _systemctl("disable", "--now", *SETUP_UNITS)
    if unselected:
        _systemctl("disable", "--now", *unselected)
    _systemctl("enable", "--now", *selected)


if __name__ == "__main__":
    activate()
