from three_mm_provisioning import (
    NetworkCredentials,
    PersistentNetworkManagerAdapter,
)


class FakeBoundary:
    def __init__(self):
        self.calls = []
        self.active_uuid = "setup-uuid"
        self.staged_uuid = "staged-uuid"
        self.previous_uuid = "previous-uuid"

    def active_connection_uuid(self, interface):
        self.calls.append(("active", interface))
        return self.active_uuid

    def connection_uuid(self, name):
        self.calls.append(("uuid", name))
        if name == "3mm-wifi":
            return self.previous_uuid
        return self.staged_uuid

    def schedule_rollback(self, uuid, delay_seconds, unit_name):
        self.calls.append(("schedule", uuid, delay_seconds, unit_name))

    def connect_persistent_wifi(self, **values):
        self.calls.append(("connect", values))
        self.active_uuid = self.staged_uuid

    def delete_connection(self, uuid):
        self.calls.append(("delete", uuid))

    def rename_connection(self, uuid, name):
        self.calls.append(("rename", uuid, name))

    def cancel_rollback(self, unit_name):
        self.calls.append(("cancel", unit_name))


def test_persistent_adapter_replaces_old_profile_only_after_verification():
    boundary = FakeBoundary()
    adapter = PersistentNetworkManagerAdapter(boundary=boundary)
    credentials = NetworkCredentials("private-network", "persistent-secret")

    adapter.stage_configuration(credentials)
    adapter.activate_staged()

    assert adapter.verify_connectivity() is True
    assert ("delete", "previous-uuid") not in boundary.calls

    adapter.commit()

    rename_index = boundary.calls.index(("rename", "staged-uuid", "3mm-wifi"))
    delete_index = boundary.calls.index(("delete", "previous-uuid"))
    cancel_index = boundary.calls.index(("cancel", "3mm-network-client-rollback"))
    assert rename_index < delete_index < cancel_index
    connect_values = next(call[1] for call in boundary.calls if call[0] == "connect")
    assert connect_values["passphrase"] == "persistent-secret"
    assert connect_values["connection_name"].startswith("3mm-wifi-staged-")


def test_failed_persistent_attempt_deletes_only_staged_profile():
    boundary = FakeBoundary()
    adapter = PersistentNetworkManagerAdapter(boundary=boundary)

    adapter.stage_configuration(
        NetworkCredentials("private-network", "persistent-secret")
    )
    adapter.activate_staged()
    adapter.rollback()

    assert ("delete", "staged-uuid") in boundary.calls
    assert ("delete", "previous-uuid") not in boundary.calls
    assert not any(call[0] == "cancel" for call in boundary.calls)
