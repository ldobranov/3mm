from collections import deque

import pytest

from three_mm_provisioning import (
    MutationCommandResult,
    NetworkAdapterError,
    NetworkManagerMutationBoundary,
)


class FakeRunner:
    def __init__(self, results=()):
        self.results = deque(results)
        self.calls = []

    def run(self, arguments, timeout_seconds, secret_input=None):
        self.calls.append((tuple(arguments), timeout_seconds, secret_input))
        if self.results:
            return self.results.popleft()
        return MutationCommandResult(0)


def test_temporary_ap_secret_uses_stdin_and_is_marked_not_saved():
    runner = FakeRunner()
    boundary = NetworkManagerMutationBoundary(runner=runner)

    boundary.create_temporary_setup_access_point(
        interface="wlan0",
        connection_name="3mm-setup",
        network_name="3mm-device-test",
        passphrase="temporary-secret",
    )

    command_text = repr([call[0] for call in runner.calls])
    assert "temporary-secret" not in command_text
    assert "psk-flags', '2" in command_text
    assert runner.calls[-1][2] == "temporary-secret\n"
    assert runner.calls[0][2] is None
    assert runner.calls[1][2] is None


def test_rollback_is_scheduled_before_the_caller_can_start_ap():
    runner = FakeRunner()
    boundary = NetworkManagerMutationBoundary(runner=runner)

    boundary.schedule_rollback("safe-connection-uuid", 90)

    command = runner.calls[0][0]
    assert command[0] == "/usr/bin/systemd-run"
    assert "--on-active=90s" in command
    assert command[-3:] == ("up", "uuid", "safe-connection-uuid")


def test_runtime_activation_cancels_external_setup_safety_first():
    runner = FakeRunner()
    boundary = NetworkManagerMutationBoundary(runner=runner)

    boundary.schedule_runtime_activation()

    assert runner.calls[0][0][-2:] == ("stop", "3mm-setup-safety.timer")
    assert runner.calls[1][0][0] == "/usr/bin/systemd-run"
    assert "PYTHONPATH=/opt/3mm/current" in runner.calls[1][0]


def test_temporary_client_secret_uses_stdin_and_is_not_saved():
    runner = FakeRunner()
    boundary = NetworkManagerMutationBoundary(runner=runner)

    boundary.connect_temporary_wifi(
        interface="wlan0",
        connection_name="3mm-target-smoke",
        network_name="private-network",
        passphrase="temporary-secret",
    )

    command_text = repr([call[0] for call in runner.calls])
    assert "temporary-secret" not in command_text
    assert "psk-flags', '2" in command_text
    assert runner.calls[-1][2] == "temporary-secret\n"


def test_persistent_client_secret_uses_stdin_and_is_saved_by_network_manager():
    runner = FakeRunner()
    boundary = NetworkManagerMutationBoundary(runner=runner)

    boundary.connect_persistent_wifi(
        interface="wlan0",
        connection_name="3mm-wifi-staged-test",
        network_name="private-network",
        passphrase="persistent-secret",
    )

    command_text = repr([call[0] for call in runner.calls])
    assert "persistent-secret" not in command_text
    assert "psk-flags', '0" in command_text
    assert runner.calls[-1][2] == "persistent-secret\n"


def test_missing_connection_can_be_queried_without_exposing_output():
    runner = FakeRunner([MutationCommandResult(10, "sensitive output")])
    boundary = NetworkManagerMutationBoundary(runner=runner)

    assert boundary.connection_uuid("missing-profile") is None


def test_open_setup_ap_contains_no_secret_operations():
    runner = FakeRunner()
    boundary = NetworkManagerMutationBoundary(runner=runner)

    boundary.create_temporary_open_setup_access_point(
        interface="wlan0",
        connection_name="3mm-open-smoke",
        network_name="3mm Setup TEST",
    )

    command_text = repr([call[0] for call in runner.calls])
    assert "remove', '802-11-wireless-security" in command_text
    assert all(call[2] is None for call in runner.calls)


def test_active_connection_uuid_is_read_without_exposing_command_output():
    runner = FakeRunner([MutationCommandResult(0, "safe-uuid\n")])
    boundary = NetworkManagerMutationBoundary(runner=runner)

    assert boundary.active_connection_uuid("wlan0") == "safe-uuid"


def test_failed_mutation_does_not_expose_output():
    runner = FakeRunner([MutationCommandResult(10, "sensitive output")])
    boundary = NetworkManagerMutationBoundary(runner=runner)

    with pytest.raises(NetworkAdapterError) as captured:
        boundary.restore_connection("safe-uuid")

    assert "sensitive output" not in str(captured.value)


def test_ap_passphrase_requires_twelve_characters():
    boundary = NetworkManagerMutationBoundary(runner=FakeRunner())

    with pytest.raises(ValueError):
        boundary.create_temporary_setup_access_point(
            interface="wlan0",
            connection_name="3mm-setup",
            network_name="3mm-device-test",
            passphrase="too-short",
        )
