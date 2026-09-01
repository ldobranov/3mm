from pathlib import Path

import pytest

from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    FileProvisioningStore,
    NetworkCredentials,
    ProvisioningRequest,
    ProvisioningSnapshot,
)
from three_mm_runtime import activate as activation


def test_unprovisioned_runtime_enables_only_setup_services(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(activation, "_systemctl", lambda *args: calls.append(args))
    monkeypatch.setattr(
        activation,
        "_bootstrap_local_agent",
        lambda _data_dir: pytest.fail("unprovisioned runtime must not pair an Agent"),
    )

    activation.activate(tmp_path)

    assert calls[0][0:2] == ("disable", "--now")
    assert calls[1] == ("enable", "--now", *activation.SETUP_UNITS)


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
    assert calls[0] == ("disable", "--now", *activation.SETUP_UNITS)
    assert calls[-1] == (
        "enable",
        "--now",
        "3mm-core.service",
        "3mm-web.service",
        "3mm-agent.service",
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

    assert calls[-1] == ("enable", "--now", "3mm-agent.service")
