"""Lifecycle command for the open, setup-only access point."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from three_mm_provisioning import (
    FileNetworkRecoveryMarker,
    FileProvisioningStore,
    ProvisioningState,
)
from three_mm_provisioning.network_manager import NetworkManagerReadOnlyAdapter
from three_mm_provisioning.network_manager_mutation import (
    NetworkManagerMutationBoundary,
)
from three_mm_provisioning.wifi_scan_cache import write_wifi_scan_cache

CONNECTION_NAME = "3mm-setup"


def setup_ssid(machine_id_path: Path) -> str:
    suffix = machine_id_path.read_text(encoding="utf-8").strip()[-4:].upper()
    return f"3mm Setup {suffix}"


def start(data_dir: Path, interface: str, machine_id_path: Path) -> None:
    store = FileProvisioningStore(data_dir)
    if store.setup_pending():
        return  # The root helper reconciles the saved connection before any AP.
    snapshot = store.load()
    if (
        snapshot is not None
        and snapshot.state is ProvisioningState.PROVISIONED
    ):
        return
    from three_mm_provisioning.network_capabilities import setup_interface
    interface = setup_interface(interface)
    try:
        nearby_networks = NetworkManagerReadOnlyAdapter.from_system(
            timeout_seconds=15.0
        ).scan_wifi_networks(rescan=True, interface=interface)
        write_wifi_scan_cache(data_dir, nearby_networks)
    except Exception:
        # Scanning is best-effort; manual SSID entry must always remain available.
        pass
    boundary = NetworkManagerMutationBoundary()
    existing_uuid = boundary.connection_uuid(CONNECTION_NAME)
    if existing_uuid is not None:
        boundary.delete_connection(existing_uuid)
    boundary.create_temporary_open_setup_access_point(
        interface=interface,
        connection_name=CONNECTION_NAME,
        network_name=setup_ssid(machine_id_path),
        ipv4_address="10.42.0.1/24",
    )


def stop() -> None:
    boundary = NetworkManagerMutationBoundary()
    existing_uuid = boundary.connection_uuid(CONNECTION_NAME)
    if existing_uuid is not None:
        boundary.delete_connection(existing_uuid)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the 3mm setup access point")
    parser.add_argument("action", choices=("start", "stop"))
    parser.add_argument(
        "--data-dir", type=Path, default=Path("/var/lib/3mm/provisioning")
    )
    parser.add_argument("--interface", default=os.getenv("THREE_MM_SETUP_INTERFACE"))
    parser.add_argument("--machine-id", type=Path, default=Path("/etc/machine-id"))
    arguments = parser.parse_args()
    if arguments.action == "start":
        start(arguments.data_dir, arguments.interface, arguments.machine_id)
    else:
        stop()


if __name__ == "__main__":
    main()
