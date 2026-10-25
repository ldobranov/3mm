"""Resolve the services required by a provisioned device role."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from three_mm_protocol import AgentRole
from three_mm_runtime.install_profile import NetworkBackend
from three_mm_provisioning import (
    FileNetworkRecoveryMarker,
    ProvisioningState,
    ProvisioningStore,
)


class RuntimeService(str, Enum):
    SETUP = "setup"
    CORE = "core"
    WEB = "web"
    AGENT = "agent"


class SetupAccess(str, Enum):
    LOCAL = "local"
    ACCESS_POINT = "access_point"


@dataclass(frozen=True, slots=True)
class RuntimePlan:
    role: AgentRole | None
    services: tuple[RuntimeService, ...]
    setup_access: SetupAccess | None = None

    def includes(self, service: RuntimeService) -> bool:
        return service in self.services


class DeviceRuntimePlanner:
    """Build a fail-closed service plan from the provisioning journal."""

    def __init__(
        self,
        store: ProvisioningStore,
        recovery_marker: FileNetworkRecoveryMarker | None = None,
        network_backend: NetworkBackend = NetworkBackend.HOST,
    ) -> None:
        self._store = store
        self._recovery_marker = recovery_marker
        self._network_backend = NetworkBackend(network_backend)

    def resolve(self) -> RuntimePlan:
        recovery = self._recovery_marker is not None and self._recovery_marker.is_active()
        snapshot = getattr(self._store, "load_runtime_snapshot", self._store.load)()
        pending = getattr(self._store, "setup_pending", lambda: False)()
        if snapshot is None or snapshot.state is not ProvisioningState.PROVISIONED:
            access = (SetupAccess.ACCESS_POINT if self._network_backend is NetworkBackend.NETWORK_MANAGER and not pending
                      else SetupAccess.LOCAL)
            return RuntimePlan(role=None, services=(RuntimeService.SETUP,), setup_access=access)
        if snapshot.role is None:
            raise RuntimeError("Provisioned state does not contain a device role")
        plan = plan_for_role(snapshot.role)
        if recovery:
            # Link recovery is additional local administration, not a new role
            # or permission to replace healthy workloads with an open setup AP.
            return RuntimePlan(role=plan.role, services=(*plan.services, RuntimeService.SETUP),
                               setup_access=SetupAccess.LOCAL)
        return plan


def plan_for_role(role: AgentRole) -> RuntimePlan:
    services: tuple[RuntimeService, ...]
    if role is AgentRole.NODE:
        services = (RuntimeService.AGENT,)
    elif role in {AgentRole.HUB, AgentRole.STANDALONE}:
        services = (
            RuntimeService.CORE,
            RuntimeService.WEB,
            RuntimeService.AGENT,
        )
    else:
        raise ValueError(f"Unsupported device role: {role!r}")
    return RuntimePlan(role=role, services=services)
