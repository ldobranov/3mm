from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    NetworkCredentials,
    ProvisioningRequest,
    ProvisioningState,
    ProvisioningStateMachine,
)
from three_mm_provisioning.mock_network import MockNetworkAdapter


def _request() -> ProvisioningRequest:
    return ProvisioningRequest(
        network=NetworkCredentials(
            network_name="private-test-network",
            passphrase="not-a-real-secret",
        ),
        locale="bg-BG",
        device_name="mock-node",
        administrator_name="admin",
        role=AgentRole.NODE,
        hub_endpoint="https://hub.test",
    )


def test_successful_provisioning_commits_network_and_stops_setup_mode():
    adapter = MockNetworkAdapter()
    machine = ProvisioningStateMachine(adapter)

    assert machine.start_setup().state is ProvisioningState.SETUP
    result = machine.provision(_request())

    assert result.state is ProvisioningState.PROVISIONED
    assert result.role is AgentRole.NODE
    assert result.recovery_required is False
    assert adapter.configuration_committed is True
    assert adapter.setup_active is False
    assert machine.history == (
        ProvisioningState.UNPROVISIONED,
        ProvisioningState.SETUP,
        ProvisioningState.APPLYING_NETWORK,
        ProvisioningState.VERIFYING_NETWORK,
        ProvisioningState.PROVISIONED,
    )


def test_failed_connectivity_rolls_back_and_returns_to_setup():
    adapter = MockNetworkAdapter(connectivity_succeeds=False)
    machine = ProvisioningStateMachine(adapter)
    machine.start_setup()

    result = machine.provision(_request())

    assert result.state is ProvisioningState.SETUP
    assert result.recovery_required is True
    assert result.error_code == "network_configuration_failed"
    assert adapter.configuration_committed is False
    assert adapter.setup_active is True
    assert adapter.calls[-2:] == ["rollback", "enter_setup_mode"]


def test_adapter_failure_uses_the_same_recovery_path():
    adapter = MockNetworkAdapter(fail_operation="activate_staged")
    machine = ProvisioningStateMachine(adapter)
    machine.start_setup()

    result = machine.provision(_request())

    assert result.state is ProvisioningState.SETUP
    assert result.recovery_required is True
    assert adapter.configuration_staged is False
    assert adapter.setup_active is True


def test_network_credentials_are_absent_from_repr_results_and_history():
    request = _request()
    adapter = MockNetworkAdapter(connectivity_succeeds=False)
    machine = ProvisioningStateMachine(adapter)
    machine.start_setup()

    result = machine.provision(request)
    rendered = repr((request, result, machine.history, adapter.calls))

    assert "private-test-network" not in rendered
    assert "not-a-real-secret" not in rendered


def test_provisioning_cannot_run_outside_setup_mode():
    machine = ProvisioningStateMachine(MockNetworkAdapter())

    try:
        machine.provision(_request())
    except RuntimeError as exc:
        assert str(exc) == "Provisioning requires setup mode"
    else:
        raise AssertionError("Provisioning unexpectedly started")


def test_provisioned_role_can_be_restored_after_restart():
    adapter = MockNetworkAdapter()
    machine = ProvisioningStateMachine(adapter)

    result = machine.restore_provisioned(AgentRole.HUB)

    assert result.state is ProvisioningState.PROVISIONED
    assert result.role is AgentRole.HUB
    assert machine.role is AgentRole.HUB
    assert adapter.calls == []


def test_interrupted_state_can_recover_setup():
    adapter = MockNetworkAdapter()
    machine = ProvisioningStateMachine(adapter)

    result = machine.recover_setup()

    assert result.state is ProvisioningState.SETUP
    assert result.recovery_required is True
    assert adapter.calls == ["rollback", "enter_setup_mode"]
