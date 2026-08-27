from collections import deque

import pytest

from three_mm_provisioning import (
    NetworkInspectionError,
    NetworkManagerReadOnlyAdapter,
)
from three_mm_provisioning.network_manager import CommandResult


class FakeRunner:
    def __init__(self, results):
        self.results = deque(results)
        self.calls = []

    def run(self, arguments, timeout_seconds):
        self.calls.append((tuple(arguments), timeout_seconds))
        return self.results.popleft()


def test_adapter_parses_privacy_safe_status_from_fixed_commands():
    runner = FakeRunner(
        [
            CommandResult(
                0,
                "running:connected (global):full:enabled:enabled\n",
            ),
            CommandResult(
                0,
                "eth0:ethernet:connected\n"
                "wlan0:wifi:connected\n"
                "lo:loopback:connected\n",
            ),
        ]
    )
    adapter = NetworkManagerReadOnlyAdapter("/usr/bin/nmcli", runner)

    status = adapter.inspect()

    assert status.running is True
    assert status.state == "connected (global)"
    assert status.connectivity == "full"
    assert status.wifi_hardware_enabled is True
    assert status.wifi_enabled is True
    assert [
        (device.interface, device.device_type, device.state)
        for device in status.devices
    ] == [
        ("eth0", "ethernet", "connected"),
        ("wlan0", "wifi", "connected"),
        ("lo", "loopback", "connected"),
    ]

    flattened_commands = " ".join(
        argument for arguments, _timeout in runner.calls for argument in arguments
    ).lower()
    assert len(runner.calls) == 2
    assert "connection" not in flattened_commands
    assert "ssid" not in flattened_commands
    assert "uuid" not in flattened_commands
    assert "password" not in flattened_commands
    assert "ip4" not in flattened_commands


@pytest.mark.parametrize(
    ("general_output", "device_output"),
    [
        ("running:connected\n", "eth0:ethernet:connected\n"),
        ("running:connected:full:enabled:enabled\n", "broken-device-line\n"),
        ("unknown:connected:full:enabled:enabled\n", ""),
    ],
)
def test_adapter_rejects_malformed_or_unknown_output(
    general_output,
    device_output,
):
    runner = FakeRunner(
        [CommandResult(0, general_output), CommandResult(0, device_output)]
    )

    with pytest.raises(NetworkInspectionError):
        NetworkManagerReadOnlyAdapter("nmcli", runner).inspect()


def test_adapter_rejects_failed_command_without_exposing_output():
    runner = FakeRunner([CommandResult(10, "sensitive unexpected output")])

    with pytest.raises(NetworkInspectionError) as captured:
        NetworkManagerReadOnlyAdapter("nmcli", runner).inspect()

    assert "sensitive unexpected output" not in str(captured.value)


def test_cached_wifi_scan_is_deduplicated_sorted_and_does_not_rescan():
    runner = FakeRunner(
        [
            CommandResult(
                0,
                "Office\\:Lab:80:WPA2\n"
                "Cafe:35:--\n"
                "Office\\:Lab:95:WPA2\n"
                ":100:WPA2\n",
            )
        ]
    )
    adapter = NetworkManagerReadOnlyAdapter("/usr/bin/nmcli", runner)

    networks = adapter.scan_wifi_networks()

    assert [
        (item.network_name, item.signal, item.secured) for item in networks
    ] == [("Office:Lab", 95, True), ("Cafe", 35, False)]
    command = runner.calls[0][0]
    assert command[-2:] == ("--rescan", "no")


def test_from_system_fails_when_nmcli_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        "three_mm_provisioning.network_manager.shutil.which",
        lambda _name: None,
    )

    with pytest.raises(NetworkInspectionError):
        NetworkManagerReadOnlyAdapter.from_system()
