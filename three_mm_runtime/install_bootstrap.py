"""Linux installation adapter for hosts without a Wi-Fi setup interface.

Only an absent first-boot journal may be initialized. Interrupted provisioning,
explicit recovery and existing roles are never silently reset.
"""

import argparse
from dataclasses import replace
from pathlib import Path
import socket
import sqlite3

from three_mm_protocol import AgentRole
from three_mm_provisioning.persistence import (
    FileProvisioningStore,
    ProvisioningSnapshot,
)
from three_mm_provisioning.models import ProvisioningState
from three_mm_provisioning.network_recovery import FileNetworkRecoveryPolicyStore
from three_mm_runtime.install_profile import InstallProfile, validate_profile_role


def has_wireless_interface(network_root: Path = Path("/sys/class/net")) -> bool:
    return any(
        (interface / "wireless").is_dir() for interface in network_root.iterdir()
    )


def prepare(
    profile: InstallProfile,
    *,
    data_dir: Path = Path("/var/lib/3mm/provisioning"),
    database: Path = Path("/var/lib/3mm/core/3mm.db"),
    policy_path: Path | None = None,
    network_root: Path = Path("/sys/class/net"),
    check_only: bool = False,
) -> None:
    store = FileProvisioningStore(data_dir)
    snapshot = store.load()
    validate_profile_role(profile, snapshot.role if snapshot else None)
    recovery = (data_dir / "network-recovery.json").exists()
    provisioned = (
        snapshot is not None and snapshot.state is ProvisioningState.PROVISIONED
    )
    if has_wireless_interface(network_root):
        if (recovery or not provisioned) and not (
            network_root / "wlan0/wireless"
        ).is_dir():
            raise RuntimeError(
                "Setup AP requires wlan0; configure this host explicitly before deployment"
            )
        return
    if recovery or (
        not provisioned and (snapshot is not None or profile is InstallProfile.NODE)
    ):
        raise RuntimeError(
            "Setup AP requires Wi-Fi; interrupted setup/recovery must be resolved explicitly"
        )
    administrator = None
    if not provisioned and database.is_file():
        with sqlite3.connect(
            database.resolve().as_uri() + "?mode=ro", uri=True
        ) as connection:
            administrator = connection.execute(
                "SELECT username FROM users WHERE role = 'admin' ORDER BY id LIMIT 1"
            ).fetchone()
        if administrator is None:
            raise RuntimeError(
                "A Core administrator is required before initializing a wired-only installation"
            )
    if check_only:
        return
    if not provisioned and administrator is None:
        raise RuntimeError(
            "Core must be migrated and bootstrapped before runtime initialization"
        )
    policy = FileNetworkRecoveryPolicyStore(
        policy_path
        or (
            data_dir / "network-recovery-policy.json"
            if profile is InstallProfile.NODE
            else database.parent / "network-recovery-policy.json"
        )
    )
    # Never overwrite a user's existing choice. A wired-only first install has
    # no AP recovery mechanism; absence of an NM-managed link is not network loss.
    if not policy.path.exists():
        policy.save(replace(policy.load(), automatic_setup_enabled=False))
    if not provisioned:
        store.save(
            ProvisioningSnapshot(
                state=ProvisioningState.PROVISIONED,
                role=AgentRole.STANDALONE,
                locale="en-US",
                device_name=socket.gethostname(),
                administrator_name=administrator[0] or "Administrator",
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", choices=[p.value for p in InstallProfile], required=True
    )
    parser.add_argument("--check-only", action="store_true")
    arguments = parser.parse_args()
    prepare(InstallProfile(arguments.profile), check_only=arguments.check_only)
