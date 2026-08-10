from three_mm_provisioning import (
    NetworkCredentials,
    TemporaryNetworkManagerAdapter,
)


class FakeBoundary:
    def __init__(self):
        self.calls = []

    def active_connection_uuid(self, interface):
        self.calls.append(("active", interface))
        return "setup-uuid"

    def schedule_rollback(self, uuid, delay_seconds, unit_name):
        self.calls.append(("schedule", uuid, delay_seconds, unit_name))

    def connect_temporary_wifi(self, **values):
        self.calls.append(
            ("connect", values["interface"], values["connection_name"])
        )

    def cancel_rollback(self, unit_name):
        self.calls.append(("cancel", unit_name))


def test_temporary_adapter_schedules_ap_recovery_before_connecting():
    boundary = FakeBoundary()
    adapter = TemporaryNetworkManagerAdapter(boundary)
    credentials = NetworkCredentials("private-network", "temporary-secret")

    adapter.enter_setup_mode()
    adapter.stage_configuration(credentials)
    adapter.activate_staged()

    assert boundary.calls[0] == ("active", "wlan0")
    assert boundary.calls[1][:3] == ("schedule", "setup-uuid", 120)
    assert boundary.calls[2][0] == "connect"
    assert adapter.verify_connectivity() is True

    adapter.commit()
    assert boundary.calls[-1][0] == "cancel"
    assert "temporary-secret" not in repr(boundary.calls)
