"""Read and persist the administrator-controlled local-link recovery policy."""

from __future__ import annotations

import re
import socket
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.config import NetworkRecoverySettings
from three_mm_provisioning import (
    FileNetworkRecoveryMarker,
    FileNetworkRecoveryPolicyStore,
    NetworkInspectionError,
    NetworkManagerReadOnlyAdapter,
    NetworkRecoveryPolicy,
)
from three_mm_provisioning.setup_access_point import setup_ssid


class NetworkRecoveryPolicyRequest(BaseModel):
    automatic_setup_enabled: bool = True

    model_config = ConfigDict(extra="forbid")


class NetworkRecoveryStatus(BaseModel):
    automatic_setup_enabled: bool
    offline_after_seconds: int
    local_link_state: Literal["connected", "disconnected", "unknown"]
    wifi_connected: bool | None
    ethernet_connected: bool | None
    setup_active: bool
    setup_network: str
    setup_url: str
    device_hostname: str
    local_url: str


class NetworkSetupRequest(BaseModel):
    confirmation: str

    model_config = ConfigDict(extra="forbid")


class NetworkSetupQueued(BaseModel):
    status: Literal["queued"] = "queued"
    setup_network: str
    setup_url: str


def read_network_recovery_status(
    settings: NetworkRecoverySettings,
    *,
    inspector=None,
) -> NetworkRecoveryStatus:
    policy = FileNetworkRecoveryPolicyStore(settings.policy_file).load()
    wifi_connected: bool | None = None
    ethernet_connected: bool | None = None
    local_link_state: Literal["connected", "disconnected", "unknown"] = "unknown"
    try:
        network_status = (inspector or NetworkManagerReadOnlyAdapter.from_system()).inspect()
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
    return NetworkRecoveryStatus(
        automatic_setup_enabled=policy.automatic_setup_enabled,
        offline_after_seconds=policy.offline_after_seconds,
        local_link_state=local_link_state,
        wifi_connected=wifi_connected,
        ethernet_connected=ethernet_connected,
        setup_active=FileNetworkRecoveryMarker(settings.marker_file).is_active(),
        setup_network=_setup_network_name(settings),
        setup_url=settings.setup_url,
        device_hostname=device_hostname,
        local_url=f"http://{device_hostname}.local",
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


def network_setup_details(settings: NetworkRecoverySettings) -> tuple[str, str]:
    return _setup_network_name(settings), settings.setup_url


def _setup_network_name(settings: NetworkRecoverySettings) -> str:
    try:
        return setup_ssid(settings.machine_id_file)
    except OSError:
        return "3mm Setup"


def _device_hostname() -> str:
    hostname = socket.gethostname().strip().lower().split(".", 1)[0]
    if re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", hostname):
        return hostname
    return "3mm-device"
