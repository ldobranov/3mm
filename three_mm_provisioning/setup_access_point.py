"""Lifecycle command for the open, setup-only access point."""

from __future__ import annotations

import argparse
from pathlib import Path

from three_mm_provisioning import (
    FileNetworkRecoveryMarker,
    FileProvisioningStore,
    ProvisioningState,
)
from three_mm_provisioning.network_manager_mutation import (
    NetworkManagerMutationBoundary,
)

CONNECTION_NAME = "3mm-setup"


def setup_ssid(machine_id_path: Path) -> str:
    suffix = machine_id_path.read_text(encoding="utf-8").strip()[-4:].upper()
    return f"3mm Setup {suffix}"


def start(data_dir: Path, interface: str, machine_id_path: Path) -> None:
    snapshot = FileProvisioningStore(data_dir).load()
    recovery_requested = FileNetworkRecoveryMarker(
        data_dir / "network-recovery.json"
    ).is_active()
    if (
        snapshot is not None
        and snapshot.state is ProvisioningState.PROVISIONED
        and not recovery_requested
    ):
        return
    boundary = NetworkManagerMutationBoundary()
    existing_uuid = boundary.connection_uuid(CONNECTION_NAME)
    if existing_uuid is not None:
        boundary.delete_connection(existing_uuid)
    boundary.create_temporary_open_setup_access_point(
        interface=interface,
        connection_name=CONNECTION_NAME,
        network_name=setup_ssid(machine_id_path),
    )


def stop() -> None:
    boundary = NetworkManagerMutationBoundary()
    existing_uuid = boundary.connection_uuid(CONNECTION_NAME)
    if existing_uuid is not None:
        boundary.delete_connection(existing_uuid)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the 3mm setup access point")
    parser.add_argument("action", choices=("start", "stop"))
    parser.add_argument("--data-dir", type=Path, default=Path("/var/lib/3mm/provisioning"))
    parser.add_argument("--interface", default="wlan0")
    parser.add_argument("--machine-id", type=Path, default=Path("/etc/machine-id"))
    arguments = parser.parse_args()
    if arguments.action == "start":
        start(arguments.data_dir, arguments.interface, arguments.machine_id)
    else:
        stop()


if __name__ == "__main__":
    main()
