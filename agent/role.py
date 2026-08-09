"""Resolve the Agent role from completed provisioning state."""

from __future__ import annotations

from three_mm_protocol import AgentRole
from three_mm_provisioning import ProvisioningState, ProvisioningStore


class AgentRoleResolver:
    def __init__(self, store: ProvisioningStore) -> None:
        self._store = store

    def resolve(self, fallback: AgentRole) -> AgentRole:
        snapshot = self._store.load()
        if snapshot is None or snapshot.state is not ProvisioningState.PROVISIONED:
            return fallback
        if snapshot.role is None:
            raise RuntimeError("Provisioned state does not contain an Agent role")
        return snapshot.role
