"""Resolve the services required by a provisioned device role."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from three_mm_protocol import AgentRole
from three_mm_provisioning import ProvisioningState, ProvisioningStore


class RuntimeService(str, Enum):
    SETUP = "setup"
    CORE = "core"
    WEB = "web"
    AGENT = "agent"


@dataclass(frozen=True, slots=True)
class RuntimePlan:
    role: AgentRole | None
    services: tuple[RuntimeService, ...]

    def includes(self, service: RuntimeService) -> bool:
        return service in self.services


class DeviceRuntimePlanner:
    """Build a fail-closed service plan from the provisioning journal."""

    def __init__(self, store: ProvisioningStore) -> None:
        self._store = store

    def resolve(self) -> RuntimePlan:
        snapshot = self._store.load()
        if snapshot is None or snapshot.state is not ProvisioningState.PROVISIONED:
            return RuntimePlan(role=None, services=(RuntimeService.SETUP,))
        if snapshot.role is None:
            raise RuntimeError("Provisioned state does not contain a device role")
        return plan_for_role(snapshot.role)


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
