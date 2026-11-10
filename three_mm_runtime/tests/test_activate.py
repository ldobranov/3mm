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


@pytest.mark.parametrize('failure', [None, 'activation', 'readiness', 'active'])
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
    def active(*args):
        calls.append('active')
        if failure == 'active':raise RuntimeError('injected unit failure')
    monkeypatch.setattr(activation, 'check_active', active)
    if failure:
        with pytest.raises(RuntimeError):activation.activate(tmp_path)
        assert journal.load()['committed'] is True
    else:
        activation.activate(tmp_path)
        assert journal.load() is None and calls == ['activate', 'ready', 'active']
    assert store.load() == snapshot


@pytest.fixture
def readiness_clock(monkeypatch):
    from types import SimpleNamespace
    clock = SimpleNamespace(now=0.0, sleeps=[])
    def sleep(seconds):
        clock.sleeps.append(seconds)
        clock.now += seconds
    monkeypatch.setattr(activation, 'time', SimpleNamespace(monotonic=lambda: clock.now, sleep=sleep))
    monkeypatch.setattr(activation.platform, 'machine', lambda: 'aarch64')
    return clock


def provision_role(path, role=AgentRole.STANDALONE):
    FileProvisioningStore(path).save(ProvisioningSnapshot(
        state=ProvisioningState.PROVISIONED, role=role, locale='en',
        device_name='test', administrator_name='owner'))


def test_armv6_cold_start_and_slow_http_finish_the_real_setup_handoff(tmp_path, monkeypatch, readiness_clock):
    from three_mm_provisioning.setup_journal import SetupJournal, SetupActivationJournal
    import deployment.service_component as component
    provision_role(tmp_path)
    pending = SetupJournal(tmp_path)
    pending.begin('b' * 32, None, wifi=False)
    pending.commit()
    journal = SetupActivationJournal(tmp_path)
    journal.handoff(pending)
    monkeypatch.setattr(activation.platform, 'machine', lambda: 'armv6l')
    monkeypatch.setattr(activation, '_activate', lambda *a, **kw: None)
    monkeypatch.setattr(activation, 'check_active', lambda *a: None)
    calls = []
    def probe(url, *, timeout):
        calls.append((url, timeout))
        if readiness_clock.now < 218:
            raise ConnectionRefusedError
        readiness_clock.now += 1.2
        assert timeout >= 1.2
        return {'status': 'ready'} if url.endswith('/ready') else {'role': 'standalone'}
    monkeypatch.setattr(component, '_http_identity', probe)
    activation.activate(tmp_path)
    assert journal.load() is None
    assert 220 < readiness_clock.now < 300
    assert all(url.endswith('/ready') or url.endswith('/hello') for url, _ in calls)
    assert len(calls) < 225  # One-second backoff, no hot startup polling.


@pytest.mark.parametrize('role', list(AgentRole))
def test_setup_readiness_checks_only_selected_role(tmp_path, monkeypatch, readiness_clock, role):
    import deployment.service_component as component
    provision_role(tmp_path, role)
    urls = []
    def probe(url, *, timeout):
        urls.append(url)
        return {'status': 'ready'} if url.endswith('/ready') else {'role': role.value}
    monkeypatch.setattr(component, '_http_identity', probe)
    activation._wait_setup_ready(tmp_path)
    assert urls[-1].endswith('/hello')
    assert len(urls) == (1 if role is AgentRole.NODE else 2)


@pytest.mark.parametrize('machine,budget', [('armv6l', 300), ('aarch64', 90)])
@pytest.mark.parametrize('fault', ['timeout', 'wrong_role', 'not_ready', 'invalid_body', 'late_success'])
def test_setup_readiness_is_bounded_and_refuses_false_success(
        tmp_path, monkeypatch, readiness_clock, machine, budget, fault):
    import deployment.service_component as component
    provision_role(tmp_path)
    monkeypatch.setattr(activation.platform, 'machine', lambda: machine)
    calls = []
    def probe(url, *, timeout):
        calls.append(timeout)
        assert 0 < timeout <= min(5, budget - readiness_clock.now)
        if fault == 'timeout':
            readiness_clock.now += timeout
            raise TimeoutError
        if fault == 'late_success':
            readiness_clock.now = budget
            return {'status': 'ready'}
        if fault == 'invalid_body':return []
        if url.endswith('/ready'):
            return {'status': 'ok' if fault == 'not_ready' else 'ready'}
        return {'role': 'node'}
    monkeypatch.setattr(component, '_http_identity', probe)
    with pytest.raises(RuntimeError, match=r'readiness deadline exceeded \((core|agent)\)'):
        activation._wait_setup_ready(tmp_path)
    assert readiness_clock.now == budget
    assert calls and max(calls) <= 5


def test_setup_handoff_changed_during_readiness_is_not_erased(tmp_path, monkeypatch, readiness_clock):
    from three_mm_provisioning.setup_journal import SetupJournal, SetupActivationJournal, atomic_json
    provision_role(tmp_path)
    pending = SetupJournal(tmp_path)
    pending.begin('c' * 32, None, wifi=False)
    pending.commit()
    journal = SetupActivationJournal(tmp_path)
    journal.handoff(pending)
    replacement = {**journal.load(), 'id': 'd' * 32}
    monkeypatch.setattr(activation, '_activate', lambda *a, **kw: None)
    monkeypatch.setattr(activation, '_wait_setup_ready', lambda *_: atomic_json(journal.path, replacement))
    monkeypatch.setattr(activation, 'check_active', lambda *a: None)
    with pytest.raises(RuntimeError, match='transaction changed'):
        activation.activate(tmp_path)
    assert journal.load() == replacement
