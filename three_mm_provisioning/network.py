"""Network boundary used by the provisioning domain."""

from __future__ import annotations

from typing import Protocol

from three_mm_provisioning.models import NetworkCredentials


class NetworkAdapterError(RuntimeError):
    """A recoverable failure reported by a platform network adapter."""


class NetworkAdapter(Protocol):
    def enter_setup_mode(self) -> None: ...

    def stage_configuration(self, credentials: NetworkCredentials) -> None: ...

    def activate_staged(self) -> None: ...

    def verify_connectivity(self) -> bool: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def leave_setup_mode(self) -> None: ...
