import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from setup_service.main import PUBLIC_SETUP_ENDPOINTS, create_app
from three_mm_provisioning import (
    FileProvisioningStore,
    MemoryProvisioningStore,
    ProvisioningSnapshot,
    ProvisioningStoreError,
)
from three_mm_provisioning.mock_network import MockNetworkAdapter


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
