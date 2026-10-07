"""Target-owned full-release deployment requirements (stdlib only).

This is a data contract, not a command language. Privileged callers may execute
only the fixed immutable installer entrypoint after verifying the whole artifact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import AbstractSet

CONTRACT_PATH = "deployment/deployment-contract.json"
INSTALLER_PATH = "deployment/install-systemd.sh"
MAX_CONTRACT_BYTES = 64 * 1024
MAX_INSTALLER_BYTES = 512 * 1024
# Stable legacy minimum, not the installed release's newest services/users.
LEGACY_REQUIRED_FILES = frozenset(
    {
        ".3mm-release.json",
        "backend/requirements.txt",
        "backend/services/update_staging.py",
        "deployment/apply_staged_update.py",
        INSTALLER_PATH,
        "deployment/migrate_database.py",
        "deployment/release-dependencies.json",
        "deployment/update-dependency-allowlist.json",
        "deployment/systemd/3mm-agent.service",
        "deployment/systemd/3mm-core.service",
        "deployment/systemd/3mm-update-helper.service",
        "deployment/systemd/3mm-web.service",
        "frontend/dist/index.html",
        "three_mm_runtime/update_helper.py",
    }
)


class DeploymentContractError(ValueError):
    """The target requires a deployment contract this updater cannot safely use."""


@dataclass(frozen=True)
class DeploymentContract:
    schema_version: int
    required_files: frozenset[str]
    installer: str = INSTALLER_PATH


def validate_deployment_contract(
    data: bytes | None,
    regular_files: AbstractSet[str],
) -> DeploymentContract:
    if data is None:
        contract = DeploymentContract(1, LEGACY_REQUIRED_FILES)
    else:
        if len(data) > MAX_CONTRACT_BYTES:
            raise DeploymentContractError("Target deployment contract is too large")
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeploymentContractError(
                "Target deployment contract is invalid"
            ) from exc
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version",
            "profile",
            "installer",
            "installer_api",
            "required_files",
        }:
            raise DeploymentContractError(
                "Target deployment contract has unsupported fields"
            )
        if (
            payload["schema_version"] != 2
            or payload["profile"] != "full"
            or payload["installer"] != INSTALLER_PATH
            or payload["installer_api"] != "immutable-full-v1"
        ):
            raise DeploymentContractError("Target deployment contract is unsupported")
        required = payload["required_files"]
        if (
            not isinstance(required, list)
            or not 1 <= len(required) <= 1000
            or any(
                not isinstance(name, str)
                or not name
                or len(name) > 512
                or "\\" in name
                or PurePosixPath(name).is_absolute()
                or ".." in PurePosixPath(name).parts
                or PurePosixPath(name).as_posix() != name
                for name in required
            )
            or required != sorted(set(required))
            or not LEGACY_REQUIRED_FILES <= set(required)
        ):
            raise DeploymentContractError(
                "Target deployment required files are invalid"
            )
        contract = DeploymentContract(2, frozenset(required))
    missing = sorted(contract.required_files - regular_files)
    if missing:
        raise DeploymentContractError(
            f"Update archive is incomplete: {', '.join(missing)}"
        )
    return contract
