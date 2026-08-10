"""Persistent NetworkManager adapter used by production provisioning."""

from __future__ import annotations

from uuid import uuid4

from three_mm_provisioning.models import NetworkCredentials
from three_mm_provisioning.network import NetworkAdapterError
from three_mm_provisioning.network_manager_mutation import (
    NetworkManagerMutationBoundary,
)


class PersistentNetworkManagerAdapter:
    """Atomically replace the managed Wi-Fi profile after verified activation."""

    def __init__(
        self,
        boundary: NetworkManagerMutationBoundary | None = None,
        interface: str = "wlan0",
        stable_connection_name: str = "3mm-wifi",
    ) -> None:
        self._boundary = boundary or NetworkManagerMutationBoundary()
        self._interface = interface
        self._stable_connection_name = stable_connection_name
        self._staged_connection_name = f"3mm-wifi-staged-{uuid4().hex[:8]}"
        self._credentials: NetworkCredentials | None = None
        self._previous_uuid: str | None = None
        self._staged_uuid: str | None = None
        self._rollback_unit = "3mm-network-client-rollback"

    def enter_setup_mode(self) -> None:
        return None

    def stage_configuration(self, credentials: NetworkCredentials) -> None:
        self._credentials = credentials

    def activate_staged(self) -> None:
        if self._credentials is None:
            raise NetworkAdapterError("No Wi-Fi configuration was staged")
        setup_uuid = self._boundary.active_connection_uuid(self._interface)
        self._previous_uuid = self._boundary.connection_uuid(
            self._stable_connection_name
        )
        self._boundary.schedule_rollback(
            setup_uuid,
            delay_seconds=120,
            unit_name=self._rollback_unit,
        )
        self._boundary.connect_persistent_wifi(
            interface=self._interface,
            connection_name=self._staged_connection_name,
            network_name=self._credentials.network_name,
            passphrase=self._credentials.passphrase,
        )
        self._staged_uuid = self._boundary.connection_uuid(
            self._staged_connection_name
        )
        if self._staged_uuid is None:
            raise NetworkAdapterError("Staged Wi-Fi profile is unavailable")

    def verify_connectivity(self) -> bool:
        return (
            self._staged_uuid is not None
            and self._boundary.active_connection_uuid(self._interface)
            == self._staged_uuid
        )

    def commit(self) -> None:
        if self._staged_uuid is None:
            raise NetworkAdapterError("No active Wi-Fi profile can be committed")
        self._boundary.rename_connection(
            self._staged_uuid,
            self._stable_connection_name,
        )
        if self._previous_uuid and self._previous_uuid != self._staged_uuid:
            self._boundary.delete_connection(self._previous_uuid)
        self._boundary.cancel_rollback(self._rollback_unit)
        self._credentials = None

    def rollback(self) -> None:
        staged_uuid = self._staged_uuid or self._boundary.connection_uuid(
            self._staged_connection_name
        )
        if staged_uuid is not None:
            try:
                self._boundary.delete_connection(staged_uuid)
            except NetworkAdapterError:
                pass
        self._credentials = None
        self._staged_uuid = None

    def leave_setup_mode(self) -> None:
        return None
