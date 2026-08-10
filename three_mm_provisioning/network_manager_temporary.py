"""Temporary real Wi-Fi adapter used by controlled provisioning trials."""

from __future__ import annotations

from three_mm_provisioning.models import NetworkCredentials
from three_mm_provisioning.network import NetworkAdapterError
from three_mm_provisioning.network_manager_mutation import (
    NetworkManagerMutationBoundary,
)


class TemporaryNetworkManagerAdapter:
    """Apply one non-persistent client profile with timed AP recovery."""

    def __init__(
        self,
        boundary: NetworkManagerMutationBoundary | None = None,
        interface: str = "wlan0",
    ) -> None:
        self._boundary = boundary or NetworkManagerMutationBoundary()
        self._interface = interface
        self._credentials: NetworkCredentials | None = None
        self._connected = False
        self._rollback_unit = "3mm-network-client-rollback"

    def enter_setup_mode(self) -> None:
        return None

    def stage_configuration(self, credentials: NetworkCredentials) -> None:
        self._credentials = credentials

    def activate_staged(self) -> None:
        if self._credentials is None:
            raise NetworkAdapterError("No Wi-Fi configuration was staged")
        setup_uuid = self._boundary.active_connection_uuid(self._interface)
        self._boundary.schedule_rollback(
            setup_uuid,
            delay_seconds=120,
            unit_name=self._rollback_unit,
        )
        self._boundary.connect_temporary_wifi(
            interface=self._interface,
            connection_name="3mm-target-smoke",
            network_name=self._credentials.network_name,
            passphrase=self._credentials.passphrase,
        )
        self._connected = True

    def verify_connectivity(self) -> bool:
        return self._connected

    def commit(self) -> None:
        self._boundary.cancel_rollback(self._rollback_unit)
        self._credentials = None

    def rollback(self) -> None:
        self._credentials = None
        self._connected = False

    def leave_setup_mode(self) -> None:
        return None
