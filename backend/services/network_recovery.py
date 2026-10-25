"""Read and persist the administrator-controlled local-link recovery policy."""

from __future__ import annotations

import re
import socket
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.config import NetworkRecoverySettings
from three_mm_provisioning import (
    FileNetworkRecoveryMarker,
    FileProvisioningStore,
    FileNetworkRecoveryPolicyStore,
    NetworkInspectionError,
    NetworkManagerReadOnlyAdapter,
    NetworkRecoveryPolicy,
)
from three_mm_runtime.install_profile import NetworkBackend, read_network_backend
from three_mm_provisioning.models import NetworkMode
from three_mm_provisioning.persistence import ProvisioningStoreError

from three_mm_provisioning.network_capabilities import managed_interfaces
from three_mm_provisioning.recovery_access_point import read_status as read_ap_status

LOCAL_SETUP_URL = "http://127.0.0.1:8895/setup"


class NetworkRecoveryPolicyRequest(BaseModel):
    automatic_setup_enabled: bool = True

    model_config = ConfigDict(extra="forbid")


class NetworkRecoveryStatus(BaseModel):
    automatic_setup_enabled: bool
    automatic_setup_available: bool
    offline_after_seconds: int
    local_link_state: Literal["connected", "disconnected", "unknown"]
    wifi_connected: bool | None
    ethernet_connected: bool | None
    setup_active: bool
    setup_network: str | None
    setup_url: str
    device_hostname: str
    local_url: str
    access_point: dict


class AccessPointRequest(BaseModel):
    confirmation: Literal["START ACCESS POINT"]
    interface: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,14}$")
    duration_seconds: int = Field(default=300, ge=60, le=900, strict=True)
    model_config = ConfigDict(extra="forbid")


class AccessPointStopRequest(BaseModel):
    confirmation: Literal["STOP ACCESS POINT"]
    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    model_config = ConfigDict(extra="forbid")


class NetworkSetupRequest(BaseModel):
    confirmation: str

    model_config = ConfigDict(extra="forbid")


class NetworkSetupQueued(BaseModel):
    status: Literal["queued"] = "queued"
    setup_network: str | None
    setup_url: str
    access_code: str


def read_network_recovery_status(
    settings: NetworkRecoverySettings,
    *,
    inspector=None,
) -> NetworkRecoveryStatus:
    policy = FileNetworkRecoveryPolicyStore(settings.policy_file).load()
    wifi_connected: bool | None = None
    ethernet_connected: bool | None = None
    local_link_state: Literal["connected", "disconnected", "unknown"] = "unknown"
    adapter = inspector
    network_status = None
    try:
        if inspector is None and read_network_backend() is NetworkBackend.HOST:
            raise NetworkInspectionError("Host-managed link inspection is not available")
        adapter = inspector or NetworkManagerReadOnlyAdapter.from_system()
        network_status = adapter.inspect()
        wifi_connected = any(
            device.device_type == "wifi" and device.state.lower() == "connected"
            for device in network_status.devices
        )
        ethernet_connected = any(
            device.device_type == "ethernet" and device.state.lower() == "connected"
            for device in network_status.devices
        )
        local_link_state = (
            "connected" if wifi_connected or ethernet_connected else "disconnected"
        )
    except NetworkInspectionError:
        pass

    device_hostname = _device_hostname()
    try:
        snapshot = FileProvisioningStore(settings.marker_file.parent).load_runtime_snapshot()
    except (ProvisioningStoreError, ValueError, OSError):
        snapshot = None
    interfaces = managed_interfaces(adapter=adapter, status=network_status) if network_status is not None else []
    return NetworkRecoveryStatus(
        automatic_setup_enabled=policy.automatic_setup_enabled,
        automatic_setup_available=(read_network_backend() is NetworkBackend.NETWORK_MANAGER
                                   and snapshot is not None and snapshot.network_mode is NetworkMode.WIFI),
        offline_after_seconds=policy.offline_after_seconds,
        local_link_state=local_link_state,
        wifi_connected=wifi_connected,
        ethernet_connected=ethernet_connected,
        setup_active=FileNetworkRecoveryMarker(settings.marker_file).is_active(),
        setup_network=None,
        setup_url=f"http://{device_hostname}.local:8895/setup",
        device_hostname=device_hostname,
        local_url=f"http://{device_hostname}.local",
        access_point={**read_ap_status(), "interfaces": [item["name"] for item in interfaces if item["access_point"]]},
    )


def save_network_recovery_policy(
    settings: NetworkRecoverySettings,
    request: NetworkRecoveryPolicyRequest,
) -> NetworkRecoveryPolicy:
    store = FileNetworkRecoveryPolicyStore(settings.policy_file)
    policy = NetworkRecoveryPolicy(
        automatic_setup_enabled=request.automatic_setup_enabled,
        offline_after_seconds=settings.offline_after_seconds,
    )
    store.save(policy)
    return policy


def network_setup_details(settings: NetworkRecoverySettings) -> tuple[None, str]:
    return None, f"http://{_device_hostname()}.local:8895/setup"


def _device_hostname() -> str:
    hostname = socket.gethostname().strip().lower().split(".", 1)[0]
    if re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", hostname):
        return hostname
    return "3mm-device"
