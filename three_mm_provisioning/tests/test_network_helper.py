from three_mm_provisioning import NetworkCredentials
from three_mm_provisioning.network_helper import _handle_request
from three_mm_provisioning import network_helper
from three_mm_provisioning.network_manager import WifiNetwork


def test_helper_rejects_unknown_or_malformed_fields():
    assert _handle_request({"network_name": "test"}) == {
        "ok": False,
        "error": "invalid_request",
    }
    assert _handle_request(
        {
            "network_name": "test",
            "passphrase": "valid-secret",
            "extra": True,
        }
    ) == {"ok": False, "error": "invalid_request"}


def test_network_credentials_remain_secret_in_representation():
    credentials = NetworkCredentials("private-network", "valid-secret")

    assert "private-network" not in repr(credentials)
    assert "valid-secret" not in repr(credentials)


def test_helper_schedules_runtime_activation(monkeypatch):
    calls = []

    class FakeBoundary:
        def schedule_runtime_activation(self):
            calls.append("scheduled")

    monkeypatch.setattr(network_helper, "NetworkManagerMutationBoundary", FakeBoundary)

    assert _handle_request({"action": "activate_runtime"}) == {"ok": True}
    assert calls == ["scheduled"]


def test_helper_returns_only_validated_cached_wifi_scan(monkeypatch):
    class FakeInspector:
        @classmethod
        def from_system(cls, **_values):
            return cls()

        def scan_wifi_networks(self):
            return (WifiNetwork("Test Wi-Fi", 82, True),)

    monkeypatch.setattr(network_helper, "NetworkManagerReadOnlyAdapter", FakeInspector)

    assert _handle_request({"action": "scan_wifi"}) == {
        "ok": True,
        "items": [
            {"network_name": "Test Wi-Fi", "signal": 82, "secured": True}
        ],
    }
