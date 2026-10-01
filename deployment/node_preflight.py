"""Read-only Node feasibility report. Does not install or certify an artifact."""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import shutil
import sys
from pathlib import Path


NODE_COMMANDS = ("bash", "python3", "systemctl", "nmcli", "tar", "flock", "curl", "dnsmasq", "openssl")
NODE_IMPORTS = (
    "requests", "pydantic", "fastapi", "uvicorn", "gpiod",
    "agent.main", "setup_service.main", "three_mm_provisioning.network_helper",
    "three_mm_runtime.activate", "three_mm_runtime.network_recovery",
    "three_mm_runtime.node_recovery", "three_mm_runtime.node_update_helper", "three_mm_runtime.node_update_trust",
)


def inspect_node(*, machine=None, system=None, python_version=None,
                 lookup=shutil.which, importer=importlib.import_module):
    architecture = machine or platform.machine()
    operating_system = system or platform.system()
    version = python_version or sys.version_info[:3]
    checks = [
        {"name": "os", "passed": operating_system == "Linux"},
        {"name": "architecture_candidate", "passed": architecture in {"armv6l", "armv7l", "aarch64", "x86_64"}},
        # Agent uses datetime.UTC, introduced in Python 3.11.
        {"name": "python", "passed": tuple(version) >= (3, 11)},
    ]
    for command in NODE_COMMANDS:
        checks.append({"name": "command." + command, "passed": lookup(command) is not None})
    for module in NODE_IMPORTS:
        try:
            importer(module)
        except Exception as exc:
            checks.append({"name": "import." + module, "passed": False, "error_type": type(exc).__name__})
        else:
            checks.append({"name": "import." + module, "passed": True})
    return {"profile": "node", "architecture": architecture, "checks": checks,
            "runtime_dependencies_ready": all(check["passed"] for check in checks),
            "installer_ready": False,
            "remaining": ["Node immutable installer and rollback acceptance",
                          "Node service integration and target recovery acceptance",
                          "Target-device ARMv6 dependency and service acceptance"]}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    # Permit direct execution from an extracted checkout without installation.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    report = inspect_node()
    print(json.dumps(report, indent=2))
    return 0 if report["runtime_dependencies_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
