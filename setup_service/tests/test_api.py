import sqlite3

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from setup_service.config import SetupSettings
from setup_service.main import PUBLIC_SETUP_ENDPOINTS, create_app
from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    FileNetworkRecoveryMarker,
    FileProvisioningStore,
    MemoryProvisioningStore,
    NetworkCredentials,
    ProvisioningRequest,
    ProvisioningSnapshot,
    ProvisioningStoreError,
)
from three_mm_provisioning.mock_network import MockNetworkAdapter
from three_mm_provisioning.network_manager import WifiNetwork
from three_mm_provisioning.wifi_scan_cache import write_wifi_scan_cache


@pytest.fixture
def configuration() -> dict[str, str]:
    return {
        "network_name": "private-test-network",
        "passphrase": "not-a-real-secret",
        "locale": "bg-BG",
        "device_name": "mock-node",
        "administrator_name": "admin",
        "role": "node",
        "hub_endpoint": "https://hub.test",
    }


@pytest.fixture
def store() -> MemoryProvisioningStore:
    return MemoryProvisioningStore()


def test_public_route_surface_is_explicit_and_setup_page_is_available(store):
    app = create_app(MockNetworkAdapter(), store)
    actual_routes = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }

    assert actual_routes == PUBLIC_SETUP_ENDPOINTS
    with TestClient(app) as client:
        response = client.get("/setup")
        status = client.get("/api/v1/setup/status")

    assert response.status_code == 200
    assert "Set up this 3mm device" in response.text
    assert "Setup saved. Connect to" in response.text
    assert "Setup could not be applied." not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert status.json() == {
        "state": "setup",
        "setup_active": True,
        "role": None,
    }


@pytest.mark.parametrize(
    "probe",
    [
        "/generate_204",
        "/hotspot-detect.html",
        "/connecttest.txt",
        "/ncsi.txt",
    ],
)
def test_captive_portal_probes_redirect_to_setup(probe, store):
    with TestClient(create_app(MockNetworkAdapter(), store)) as client:
        response = client.get(probe, follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/setup"


def test_setup_lists_cached_wifi_networks(store):
    class ScanAdapter(MockNetworkAdapter):
        def scan_wifi_networks(self):
            return (WifiNetwork("Nearby Wi-Fi", 76, True),)

    with TestClient(create_app(ScanAdapter(), store)) as client:
        response = client.get("/api/v1/setup/networks")

    assert response.json() == {
        "items": [{"network_name": "Nearby Wi-Fi", "signal": 76, "secured": True}]
    }


def test_setup_merges_pre_ap_scan_and_filters_its_own_network(store, tmp_path):
    class ScanAdapter(MockNetworkAdapter):
        def scan_wifi_networks(self):
            return (
                WifiNetwork("3mm Setup 546E", 100, False),
                WifiNetwork("Cafe", 45, False),
            )

    data_dir = tmp_path / "provisioning"
    write_wifi_scan_cache(
        data_dir,
        (
            WifiNetwork("KavalaVIVA", 81, True),
            WifiNetwork("Cafe", 30, False),
        ),
    )
    settings = SetupSettings(data_dir=data_dir)

    with TestClient(create_app(ScanAdapter(), store, settings)) as client:
        response = client.get("/api/v1/setup/networks")

    assert response.json() == {
        "items": [
            {"network_name": "KavalaVIVA", "signal": 81, "secured": True},
            {"network_name": "Cafe", "signal": 45, "secured": False},
        ]
    }


def test_setup_uses_pre_ap_scan_when_live_scan_fails(store, tmp_path):
    class FailingScanAdapter(MockNetworkAdapter):
        def scan_wifi_networks(self):
            raise RuntimeError("simulated scan failure")

    data_dir = tmp_path / "provisioning"
    write_wifi_scan_cache(data_dir, (WifiNetwork("KavalaVIVA", 81, True),))
    settings = SetupSettings(data_dir=data_dir)

    with TestClient(create_app(FailingScanAdapter(), store, settings)) as client:
        response = client.get("/api/v1/setup/networks")

    assert response.status_code == 200
    assert response.json()["items"][0]["network_name"] == "KavalaVIVA"


def test_setup_theme_uses_safe_values_from_the_core_database(store, tmp_path):
    database = tmp_path / "core.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE settings (id INTEGER PRIMARY KEY, key TEXT, value TEXT)"
        )
        connection.executemany(
            "INSERT INTO settings (key, value) VALUES (?, ?)",
            [
                ("user_theme", "dark"),
                ("dark_body_bg", "#101820"),
                ("dark_card_bg", "#18242f"),
                ("dark_button_primary_bg", "#4caf50"),
                ("header_bg_color", "not-a-color"),
            ],
        )
    settings = SetupSettings(
        data_dir=tmp_path / "provisioning",
        core_database_path=database,
    )

    with TestClient(create_app(MockNetworkAdapter(), store, settings)) as client:
        response = client.get("/api/v1/setup/theme")

    assert response.status_code == 200
    assert response.json()["mode"] == "dark"
    assert response.json()["body_bg"] == "#101820"
    assert response.json()["card_bg"] == "#18242f"
    assert response.json()["primary"] == "#4caf50"
    assert response.json()["header_bg"] == "#4caf50"


def test_successful_configuration_stops_setup_mode(configuration, store):
    adapter = MockNetworkAdapter()
    with TestClient(create_app(adapter, store)) as client:
        response = client.post("/api/v1/setup/configure", json=configuration)
        status = client.get("/api/v1/setup/status")
        repeated = client.post("/api/v1/setup/configure", json=configuration)

    assert response.status_code == 200
    assert response.json() == {
        "state": "provisioned",
        "role": "node",
        "recovery_required": False,
        "error_code": None,
    }
    assert status.json() == {
        "state": "provisioned",
        "setup_active": False,
        "role": "node",
    }
    assert repeated.status_code == 409
    assert store.snapshot is not None
    assert store.snapshot.state.value == "provisioned"


def test_failed_configuration_rolls_back_without_exposing_secrets(
    configuration,
    store,
):
    adapter = MockNetworkAdapter(connectivity_succeeds=False)
    with TestClient(create_app(adapter, store)) as client:
        response = client.post("/api/v1/setup/configure", json=configuration)
        status = client.get("/api/v1/setup/status")

    combined_response = response.text + status.text
    assert response.json() == {
        "state": "setup",
        "role": None,
        "recovery_required": True,
        "error_code": "network_configuration_failed",
    }
    assert status.json() == {
        "state": "setup",
        "setup_active": True,
        "role": None,
    }
    assert store.snapshot is None
    assert configuration["network_name"] not in combined_response
    assert configuration["passphrase"] not in combined_response


def test_invalid_input_does_not_echo_the_passphrase(configuration, store):
    configuration["network_name"] = "private-network-name-that-is-much-too-long"
    configuration["device_name"] = "invalid device name"
    with TestClient(create_app(MockNetworkAdapter(), store)) as client:
        response = client.post("/api/v1/setup/configure", json=configuration)

    assert response.status_code == 422
    assert configuration["network_name"] not in response.text
    assert configuration["passphrase"] not in response.text
    assert '"input"' not in response.text


def test_completed_provisioning_is_restored_without_setup_mode(
    configuration,
    tmp_path,
):
    store = FileProvisioningStore(tmp_path)
    with TestClient(create_app(MockNetworkAdapter(), store)) as client:
        assert (
            client.post("/api/v1/setup/configure", json=configuration).status_code
            == 200
        )

    restarted_adapter = MockNetworkAdapter()
    with TestClient(create_app(restarted_adapter, store)) as client:
        status = client.get("/api/v1/setup/status")

    assert status.json() == {
        "state": "provisioned",
        "setup_active": False,
        "role": "node",
    }
    assert restarted_adapter.calls == []


def test_interrupted_attempt_rolls_back_on_restart():
    store = MemoryProvisioningStore(ProvisioningSnapshot.attempt_started())
    adapter = MockNetworkAdapter()

    with TestClient(create_app(adapter, store)) as client:
        status = client.get("/api/v1/setup/status")

    assert status.json() == {
        "state": "setup",
        "setup_active": True,
        "role": None,
    }
    assert adapter.calls == ["rollback", "enter_setup_mode"]
    assert store.snapshot is None


def test_failed_final_snapshot_recovers_setup(configuration):
    class FailingFinalStore(MemoryProvisioningStore):
        save_count = 0

        def save(self, snapshot):
            self.save_count += 1
            if self.save_count == 2:
                raise ProvisioningStoreError("simulated final write failure")
            super().save(snapshot)

    store = FailingFinalStore()
    adapter = MockNetworkAdapter()
    with TestClient(create_app(adapter, store)) as client:
        response = client.post("/api/v1/setup/configure", json=configuration)
        status = client.get("/api/v1/setup/status")

    assert response.status_code == 503
    assert response.json() == {"detail": "setup_persistence_failed"}
    assert status.json() == {
        "state": "setup",
        "setup_active": True,
        "role": None,
    }
    assert adapter.configuration_committed is False
    assert adapter.setup_active is True


def recovery_snapshot() -> ProvisioningSnapshot:
    return ProvisioningSnapshot.provisioned(
        ProvisioningRequest(
            network=NetworkCredentials("old-network", "not-persisted"),
            locale="en-GB",
            device_name="old-device",
            administrator_name="admin",
            role=AgentRole.STANDALONE,
        )
    )


def test_recovery_setup_keeps_previous_provisioning_when_new_wifi_fails(
    configuration, tmp_path
):
    store = MemoryProvisioningStore(recovery_snapshot())
    marker = FileNetworkRecoveryMarker(tmp_path / "network-recovery.json")
    marker.activate("manual")
    adapter = MockNetworkAdapter(connectivity_succeeds=False)

    with TestClient(create_app(adapter, store, recovery_marker=marker)) as client:
        response = client.post("/api/v1/setup/configure", json=configuration)

    assert response.json()["recovery_required"] is True
    assert store.snapshot == recovery_snapshot()
    assert marker.is_active() is True


def test_recovery_setup_prefills_only_non_secret_previous_values(tmp_path) -> None:
    snapshot = recovery_snapshot()
    store = MemoryProvisioningStore(snapshot)
    marker = FileNetworkRecoveryMarker(tmp_path / "network-recovery.json")
    marker.activate("manual")

    with TestClient(
        create_app(MockNetworkAdapter(), store, recovery_marker=marker)
    ) as client:
        response = client.get("/api/v1/setup/prefill")

    assert response.status_code == 200
    assert response.json() == {
        "locale": "en-GB",
        "device_name": "old-device",
        "administrator_name": "admin",
        "role": "standalone",
        "hub_endpoint": None,
    }
    assert "network" not in response.text
    assert "passphrase" not in response.text


def test_first_boot_setup_prefill_is_empty(store) -> None:
    with TestClient(create_app(MockNetworkAdapter(), store)) as client:
        response = client.get("/api/v1/setup/prefill")

    assert response.json() == {
        "locale": None,
        "device_name": None,
        "administrator_name": None,
        "role": None,
        "hub_endpoint": None,
    }


def test_successful_recovery_replaces_snapshot_and_clears_marker(
    configuration, tmp_path
):
    store = MemoryProvisioningStore(recovery_snapshot())
    marker = FileNetworkRecoveryMarker(tmp_path / "network-recovery.json")
    marker.activate("manual")

    with TestClient(
        create_app(MockNetworkAdapter(), store, recovery_marker=marker)
    ) as client:
        response = client.post("/api/v1/setup/configure", json=configuration)

    assert response.json()["state"] == "provisioned"
    assert store.snapshot is not None
    assert store.snapshot.device_name == configuration["device_name"]
    assert marker.is_active() is False
