"""Recoverable headless provisioning state machine."""

from __future__ import annotations

from three_mm_protocol import AgentRole
from three_mm_provisioning.models import (
    ProvisioningRequest,
    ProvisioningResult,
    ProvisioningState,
)
from three_mm_provisioning.network import NetworkAdapter, NetworkAdapterError


class ProvisioningStateMachine:
    def __init__(self, network: NetworkAdapter) -> None:
        self._network = network
        self._state = ProvisioningState.UNPROVISIONED
        self._role: AgentRole | None = None
        self._history = [self._state]

    @property
    def state(self) -> ProvisioningState:
        return self._state

    @property
    def history(self) -> tuple[ProvisioningState, ...]:
        return tuple(self._history)

    @property
    def role(self) -> AgentRole | None:
        return self._role

    def start_setup(self) -> ProvisioningResult:
        if self._state is not ProvisioningState.UNPROVISIONED:
            raise RuntimeError("Setup can only start on an unprovisioned device")
        self._network.enter_setup_mode()
        self._transition(ProvisioningState.SETUP)
        return self._result()

    def restore_provisioned(self, role: AgentRole) -> ProvisioningResult:
        if self._state is not ProvisioningState.UNPROVISIONED:
            raise RuntimeError("Provisioned state can only be restored at startup")
        self._role = role
        self._transition(ProvisioningState.PROVISIONED)
        return self._result()

    def recover_setup(self) -> ProvisioningResult:
        self._network.rollback()
        self._network.enter_setup_mode()
        self._role = None
        self._transition(ProvisioningState.SETUP)
        return self._result(recovery_required=True)

    def provision(self, request: ProvisioningRequest) -> ProvisioningResult:
        if self._state is not ProvisioningState.SETUP:
            raise RuntimeError("Provisioning requires setup mode")

        try:
            self._transition(ProvisioningState.APPLYING_NETWORK)
            self._network.stage_configuration(request.network)
            self._network.activate_staged()
            self._transition(ProvisioningState.VERIFYING_NETWORK)
            if not self._network.verify_connectivity():
                raise NetworkAdapterError("connectivity verification failed")
            self._network.commit()
            self._network.leave_setup_mode()
        except NetworkAdapterError:
            self._network.rollback()
            self._network.enter_setup_mode()
            self._transition(ProvisioningState.SETUP)
            return self._result(
                recovery_required=True,
                error_code="network_configuration_failed",
            )

        self._role = request.role
        self._transition(ProvisioningState.PROVISIONED)
        return self._result()

    def _transition(self, state: ProvisioningState) -> None:
        self._state = state
        self._history.append(state)

    def _result(
        self,
        *,
        recovery_required: bool = False,
        error_code: str | None = None,
    ) -> ProvisioningResult:
        return ProvisioningResult(
            state=self._state,
            role=self._role,
            recovery_required=recovery_required,
            error_code=error_code,
        )
