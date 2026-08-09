"""Deterministic network adapter for laptop development and tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from three_mm_provisioning.models import NetworkCredentials
from three_mm_provisioning.network import NetworkAdapterError


@dataclass(slots=True)
class MockNetworkAdapter:
    connectivity_succeeds: bool = True
    fail_operation: str | None = None
    setup_active: bool = False
    configuration_staged: bool = False
    configuration_committed: bool = False
    calls: list[str] = field(default_factory=list)

    def enter_setup_mode(self) -> None:
        self._record("enter_setup_mode")
        self.setup_active = True

    def stage_configuration(self, credentials: NetworkCredentials) -> None:
        self._record("stage_configuration")
        self.configuration_staged = True

    def activate_staged(self) -> None:
        self._record("activate_staged")

    def verify_connectivity(self) -> bool:
        self._record("verify_connectivity")
        return self.connectivity_succeeds

    def commit(self) -> None:
        self._record("commit")
        self.configuration_staged = False
        self.configuration_committed = True

    def rollback(self) -> None:
        self.calls.append("rollback")
        self.configuration_staged = False
        self.configuration_committed = False

    def leave_setup_mode(self) -> None:
        self._record("leave_setup_mode")
        self.setup_active = False

    def _record(self, operation: str) -> None:
        self.calls.append(operation)
        if self.fail_operation == operation:
            raise NetworkAdapterError(f"mock failure during {operation}")
