from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    MemoryProvisioningStore,
    NetworkCredentials,
    ProvisioningRequest,
    ProvisioningSnapshot,
    FileNetworkRecoveryMarker,
)
from three_mm_runtime import DeviceRuntimePlanner, RuntimeService
from three_mm_runtime.services import SetupAccess
from three_mm_runtime.install_profile import NetworkBackend
import pytest


def _provisioned(role: AgentRole) -> ProvisioningSnapshot:
    return ProvisioningSnapshot.provisioned(
        ProvisioningRequest(
            network=NetworkCredentials("test-network", "not-persisted"),
            locale="en-GB",
            device_name="test-device",
            administrator_name="admin",
            role=role,
        )
    )


def test_unprovisioned_device_runs_only_setup() -> None:
    plan = DeviceRuntimePlanner(MemoryProvisioningStore()).resolve()

    assert plan.role is None
    assert plan.services == (RuntimeService.SETUP,)


def test_interrupted_provisioning_returns_to_setup_runtime() -> None:
    store = MemoryProvisioningStore(ProvisioningSnapshot.attempt_started())

    plan = DeviceRuntimePlanner(store).resolve()

    assert plan.services == (RuntimeService.SETUP,)


def test_node_runs_only_agent() -> None:
    plan = DeviceRuntimePlanner(
        MemoryProvisioningStore(_provisioned(AgentRole.NODE))
    ).resolve()

    assert plan.role is AgentRole.NODE
    assert plan.services == (RuntimeService.AGENT,)


def test_hub_always_runs_core_and_local_agent() -> None:
    plan = DeviceRuntimePlanner(
        MemoryProvisioningStore(_provisioned(AgentRole.HUB))
    ).resolve()

    assert plan.services == (
        RuntimeService.CORE,
        RuntimeService.WEB,
        RuntimeService.AGENT,
    )


def test_standalone_is_a_hub_preset_with_the_same_services() -> None:
    hub = DeviceRuntimePlanner(
        MemoryProvisioningStore(_provisioned(AgentRole.HUB))
    ).resolve()
    standalone = DeviceRuntimePlanner(
        MemoryProvisioningStore(_provisioned(AgentRole.STANDALONE))
    ).resolve()

    assert standalone.services == hub.services
    assert standalone.includes(RuntimeService.AGENT)


@pytest.mark.parametrize("role", list(AgentRole))
@pytest.mark.parametrize("backend", list(NetworkBackend))
def test_recovery_preserves_role_and_workloads_and_uses_local_access(tmp_path, role, backend) -> None:
    marker = FileNetworkRecoveryMarker(tmp_path / "network-recovery.json")
    marker.activate("manual")

    plan = DeviceRuntimePlanner(
        MemoryProvisioningStore(_provisioned(role)),
        marker,
        network_backend=backend,
    ).resolve()

    assert plan.role is role
    assert RuntimeService.AGENT in plan.services
    assert (RuntimeService.CORE in plan.services) == (role is not AgentRole.NODE)
    assert plan.includes(RuntimeService.SETUP)
    assert plan.setup_access is SetupAccess.LOCAL


def test_network_management_is_an_explicit_choice_independent_of_roles():
    for backend, access in ((NetworkBackend.HOST, SetupAccess.LOCAL),
                            (NetworkBackend.NETWORK_MANAGER, SetupAccess.ACCESS_POINT)):
        plan = DeviceRuntimePlanner(MemoryProvisioningStore(), network_backend=backend).resolve()
        assert plan.role is None
        assert plan.setup_access is access
