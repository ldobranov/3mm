from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    MemoryProvisioningStore,
    NetworkCredentials,
    ProvisioningRequest,
    ProvisioningSnapshot,
    FileNetworkRecoveryMarker,
)
from three_mm_runtime import DeviceRuntimePlanner, RuntimeService


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


def test_recovery_marker_temporarily_overrides_a_provisioned_runtime(tmp_path) -> None:
    marker = FileNetworkRecoveryMarker(tmp_path / "network-recovery.json")
    marker.activate("manual")

    plan = DeviceRuntimePlanner(
        MemoryProvisioningStore(_provisioned(AgentRole.STANDALONE)),
        marker,
    ).resolve()

    assert plan.services == (RuntimeService.SETUP,)
