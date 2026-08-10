from pathlib import Path

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
    monkeypatch.setattr(activation, "_systemctl", lambda *args: calls.append(args))

    activation.activate(tmp_path)

    assert calls[0] == ("disable", "--now", *activation.SETUP_UNITS)
    assert calls[-1] == (
        "enable",
        "--now",
        "3mm-core.service",
        "3mm-web.service",
        "3mm-agent.service",
    )
