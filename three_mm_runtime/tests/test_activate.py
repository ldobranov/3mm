from pathlib import Path

from three_mm_provisioning.models import ProvisioningState

import pytest

from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    FileProvisioningStore,
    NetworkCredentials,
    ProvisioningRequest,
    ProvisioningSnapshot,
)
from three_mm_runtime import activate as activation


def test_unprovisioned_runtime_enables_only_local_status_without_network_mutation(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(activation, "_require_setup_interface", lambda: pytest.fail("No Wi-Fi is required"))
    monkeypatch.setattr(activation, "_systemctl", lambda *args: calls.append(args))
    monkeypatch.setattr(
        activation,
        "_bootstrap_local_agent",
        lambda _data_dir: pytest.fail("unprovisioned runtime must not pair an Agent"),
    )

    activation.activate(tmp_path)

    assert calls[0][0:2] == ("disable", "--now")
    assert calls[-1] == ("enable", "--now", "3mm-network-helper.service", activation.LOCAL_SETUP_UNIT)
    assert not any(c[0] == "enable" and "3mm-setup-ap.service" in c for c in calls)


def test_standalone_runtime_disables_setup_before_applications(tmp_path, monkeypatch):
    store = FileProvisioningStore(Path(tmp_path))
    store.save(
        ProvisioningSnapshot.provisioned(
            ProvisioningRequest(
                network=NetworkCredentials("private-network", "not-persisted"),
                locale="en-GB",
                device_name="test-device",
                administrator_name="admin",
                role=AgentRole.STANDALONE,
            )
        )
    )
    calls = []
    pairing_calls = []
    monkeypatch.setattr(activation, "_systemctl", lambda *args: calls.append(args))
    monkeypatch.setattr(
        activation,
        "_bootstrap_local_agent",
        lambda data_dir: pairing_calls.append(data_dir),
    )

    activation.activate(tmp_path)

    assert pairing_calls == [tmp_path]
    assert calls[0] == ("disable", "--now", *activation.ALL_SETUP_UNITS)
    assert calls[-1] == (
        "enable",
        "--now",
        "3mm-core.service",
        "3mm-web.service",
        "3mm-agent.service",
        "3mm-public-web.socket",
        "3mm-platform-runtime.service", "3mm-connector-worker.service",
    )


def test_node_runtime_does_not_attempt_local_core_pairing(tmp_path, monkeypatch):
    store = FileProvisioningStore(Path(tmp_path))
    store.save(
        ProvisioningSnapshot.provisioned(
            ProvisioningRequest(
                network=NetworkCredentials("private-network", "not-persisted"),
                locale="en-GB",
                device_name="test-node",
                administrator_name="admin",
                role=AgentRole.NODE,
                hub_endpoint="http://hub.local",
            )
        )
    )
    calls = []
    monkeypatch.setattr(activation, "_systemctl", lambda *args: calls.append(args))
    monkeypatch.setattr(
        activation,
        "_bootstrap_local_agent",
        lambda _data_dir: pytest.fail("Node runtime uses external pairing"),
    )

    activation.activate(tmp_path)

    assert ("disable", "--now", "3mm-core.service", "3mm-web.service", "3mm-public-web.socket", "3mm-platform-runtime.service", "3mm-connector-worker.service") in calls
    assert calls[-1] == ("enable", "--now", "3mm-agent.service")


def test_missing_setup_interface_does_not_stop_services(tmp_path, monkeypatch):
    monkeypatch.setenv("THREE_MM_NETWORK_BACKEND", "network-manager")
    calls = []
    def missing():
        raise RuntimeError("Setup AP requires wlan0")
    monkeypatch.setattr(activation, "_require_setup_interface", missing)
    monkeypatch.setattr(activation, "_systemctl", lambda *args: calls.append(args))
    activation.activate(tmp_path)
    assert calls[-1] == ("enable", "--now", "3mm-network-helper.service", activation.LOCAL_SETUP_UNIT)
    assert not any("3mm-setup-ap.service" in call for call in calls if call[0] == "enable")


def test_invalid_network_backend_stops_before_service_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("THREE_MM_NETWORK_BACKEND", "arbitrary-network-command")
    monkeypatch.setattr(activation, "_systemctl", lambda *args: pytest.fail("No service mutation"))
    with pytest.raises(ValueError):
        activation.activate(tmp_path)


@pytest.mark.parametrize("role", list(AgentRole))
def test_recovery_never_stops_or_repairs_selected_workloads(tmp_path, monkeypatch, role):
    from three_mm_provisioning import FileNetworkRecoveryMarker

    FileProvisioningStore(tmp_path).save(ProvisioningSnapshot(
        state=ProvisioningState.PROVISIONED, role=role, locale="bg",
        device_name="unchanged", administrator_name="existing-admin"))
    FileNetworkRecoveryMarker(tmp_path / "network-recovery.json").activate("automatic")
    monkeypatch.setenv("THREE_MM_NETWORK_BACKEND", "network-manager")
    calls = []
    monkeypatch.setattr(activation, "_systemctl", lambda *args: calls.append(args))
    monkeypatch.setattr(activation, "_require_setup_interface", lambda: pytest.fail("Recovery must not start an AP"))
    monkeypatch.setattr(activation, "_bootstrap_local_agent", lambda *args: pytest.fail("Do not repair an existing identity"))
    activation.activate(tmp_path)
    selected = {"3mm-agent.service"}
    if role is not AgentRole.NODE:
        selected |= {"3mm-core.service", "3mm-web.service", "3mm-public-web.socket", "3mm-platform-runtime.service", "3mm-connector-worker.service"}
    assert not any(selected.intersection(call[2:]) for call in calls if call[0] in {"disable", "stop", "restart"})
    assert calls[-1] == ("enable", "--now", "3mm-network-helper.service", activation.LOCAL_SETUP_UNIT)
    calls.clear()
    activation.check_active(tmp_path)
    assert {call[-1] for call in calls} == selected | {activation.LOCAL_SETUP_UNIT, "3mm-network-helper.service"}


def test_health_requires_each_selected_service(tmp_path, monkeypatch):
    FileProvisioningStore(tmp_path).save(ProvisioningSnapshot(
        state=ProvisioningState.PROVISIONED,
        role=AgentRole.STANDALONE, locale="en-US", device_name="vm", administrator_name="admin",
    ))
    calls = []
    monkeypatch.setattr(activation, "_systemctl", lambda *args: calls.append(args))
    activation.check_active(tmp_path)
    assert calls == [("is-active", "--quiet", unit) for unit in (
        "3mm-core.service", "3mm-web.service", "3mm-agent.service",
        "3mm-public-web.socket", "3mm-platform-runtime.service", "3mm-connector-worker.service")]

    def agent_failed(*args):
        if args[-1] == "3mm-agent.service":
            raise RuntimeError("Agent is restarting")
    monkeypatch.setattr(activation, "_systemctl", agent_failed)
    with pytest.raises(RuntimeError, match="Agent is restarting"):
        activation.check_active(tmp_path)


@pytest.mark.parametrize('failure', [None, 'activation', 'readiness'])
def test_setup_attempt_is_acknowledged_only_after_runtime_readiness(tmp_path, monkeypatch, failure):
    from three_mm_provisioning.setup_journal import SetupJournal, SetupActivationJournal
    store = FileProvisioningStore(tmp_path)
    snapshot = ProvisioningSnapshot(state=ProvisioningState.PROVISIONED,
        role=AgentRole.STANDALONE, locale='en', device_name='preserved', administrator_name='owner')
    store.save(snapshot)
    journal = SetupJournal(tmp_path)
    journal.begin('a' * 32, None, wifi=False)
    journal.commit()
    activation_journal = SetupActivationJournal(tmp_path)
    activation_journal.handoff(journal)
    journal = activation_journal
    calls = []
    def apply(*args, **kwargs):
        calls.append('activate')
        if failure == 'activation':raise RuntimeError('injected activation failure')
    def ready(*args):
        calls.append('ready')
        if failure == 'readiness':raise RuntimeError('injected readiness failure')
    monkeypatch.setattr(activation, '_activate', apply)
    monkeypatch.setattr(activation, '_wait_setup_ready', ready)
    monkeypatch.setattr(activation, 'check_active', lambda *_: calls.append('active'))
    if failure:
        with pytest.raises(RuntimeError):activation.activate(tmp_path)
        assert journal.load()['committed'] is True
    else:
        activation.activate(tmp_path)
        assert journal.load() is None and calls == ['activate', 'ready', 'active']
    assert store.load() == snapshot
