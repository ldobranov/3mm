from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from agent.config import AgentSettings
from agent.core_client import DeviceCredential, DeviceCredentialStore
from agent.hub_connection import normalize_hub_endpoint, resolve_hub_connection
from agent.identity import AgentIdentityStore
from agent.main import create_app
from three_mm_protocol import AgentRole
from three_mm_provisioning import FileProvisioningStore, ProvisioningSnapshot, ProvisioningState


def snapshot(endpoint="http://hub.local"):
    return ProvisioningSnapshot(
        state=ProvisioningState.PROVISIONED, role=AgentRole.NODE,
        locale="en", device_name="test-node", administrator_name="owner",
        hub_endpoint=endpoint,
    )


@pytest.mark.parametrize("endpoint", [
    "http://name:password@hub", "http://hub?token=secret", "http://hub#secret",
    "ftp://hub", "http://hub:99999", "http://hub:0", "http://hub\\other",
    "http://hub\n", "http://",
])
def test_unsafe_endpoint_is_not_returned_or_used(endpoint):
    result = resolve_hub_connection(
        role=AgentRole.NODE, snapshot=snapshot(endpoint),
        configured_endpoint=None, has_credential=False,
    )
    assert result.state == "invalid_endpoint"
    assert result.hub_endpoint is None


def test_normalization_preserves_scheme_port_and_base_path():
    assert normalize_hub_endpoint("http://HUB.local:80/") == "http://hub.local"
    assert normalize_hub_endpoint("https://HUB.local:443/core/") == "https://hub.local/core"
    assert normalize_hub_endpoint("http://[::1]:8887/") == "http://[::1]:8887"


@pytest.mark.parametrize("previous,has_credential,expected", [
    (None, False, "awaiting_pairing"),
    (None, True, "reassignment_required"),
    ("http://other.local", True, "reassignment_required"),
    ("https://hub.local", True, "reassignment_required"),
    ("http://HUB.local:80/", True, "credential_available"),
])
def test_setup_selection_does_not_transfer_existing_authority(previous, has_credential, expected):
    result = resolve_hub_connection(
        role=AgentRole.NODE, snapshot=snapshot(),
        configured_endpoint=previous, has_credential=has_credential,
    )
    assert result.state == expected
    assert result.central_management_path == "via_hub"


@pytest.mark.parametrize("role", [AgentRole.HUB, AgentRole.STANDALONE])
def test_local_core_roles_keep_local_controller(role):
    result = resolve_hub_connection(
        role=role, snapshot=replace(snapshot(), role=role),
        configured_endpoint="http://127.0.0.1:8887", has_credential=True,
    )
    assert result.hub_endpoint == "http://127.0.0.1:8887"
    assert result.state == "credential_available"


def test_incomplete_setup_does_not_select_a_controller():
    result = resolve_hub_connection(
        role=AgentRole.NODE, snapshot=ProvisioningSnapshot.attempt_started(),
        configured_endpoint=None, has_credential=False,
    )
    assert result.state == "not_configured"


def test_restart_keeps_pending_selection_and_identity_without_network_calls(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.main.NodeEnrollmentWorker.start", lambda _: None)
    monkeypatch.setattr("agent.main.CorePublisher.start", lambda _: pytest.fail("Must not publish before pairing"))
    store = FileProvisioningStore(tmp_path / "setup")
    store.save(snapshot())
    settings = AgentSettings(data_dir=tmp_path / "agent", provisioning_data_dir=tmp_path / "setup")
    observations = []
    for _ in range(2):
        with TestClient(create_app(settings)) as client:
            observations.append((client.get("/ready").json(), client.get("/api/v1/agent/hub-connection").json()))
    assert observations[0] == observations[1]
    assert observations[0][1]["hub_endpoint"] == "http://hub.local"
    assert observations[0][1]["state"] == "awaiting_pairing"


def test_changed_hub_does_not_start_publisher_or_modify_credential(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.main.CorePublisher.start", lambda _: pytest.fail("Credential would leak"))
    identity = AgentIdentityStore(tmp_path / "agent").load_or_create()
    credentials = DeviceCredentialStore(tmp_path / "agent")
    credentials.save(DeviceCredential(
        device_id=identity.device_id, credential_id="cred_" + "a" * 32,
        credential_secret="private-test-value" * 3,
    ))
    original = credentials.path.read_bytes()
    FileProvisioningStore(tmp_path / "setup").save(snapshot())
    settings = AgentSettings(data_dir=tmp_path / "agent", provisioning_data_dir=tmp_path / "setup", core_url="http://old-hub.local")
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/agent/hub-connection")
        assert response.json()["state"] == "reassignment_required"
        assert "private-test-value" not in response.text
        assert client.get("/ready").status_code == 200
    assert credentials.path.read_bytes() == original


def test_existing_controller_starts_exactly_one_publisher(tmp_path, monkeypatch):
    started, stopped = [], []
    monkeypatch.setattr("agent.main.CorePublisher.start", lambda publisher: started.append(publisher.core_url))
    monkeypatch.setattr("agent.main.CorePublisher.stop", lambda publisher: stopped.append(publisher.core_url))
    identity = AgentIdentityStore(tmp_path / "agent").load_or_create()
    DeviceCredentialStore(tmp_path / "agent").save(DeviceCredential(
        device_id=identity.device_id, credential_id="cred_" + "a" * 32,
        credential_secret="private-test-value" * 3,
    ))
    FileProvisioningStore(tmp_path / "setup").save(snapshot())
    settings = AgentSettings(data_dir=tmp_path / "agent", provisioning_data_dir=tmp_path / "setup", core_url="http://HUB.local:80/")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/agent/hub-connection").json()["state"] == "credential_available"
    assert started == stopped == ["http://hub.local"]


def test_bound_credential_survives_restart_without_legacy_core_url(tmp_path, monkeypatch):
    import json

    started = []
    monkeypatch.setattr("agent.main.CorePublisher.start", lambda publisher: started.append(publisher.core_url))
    monkeypatch.setattr("agent.main.CorePublisher.stop", lambda _: None)
    identity = AgentIdentityStore(tmp_path / "agent").load_or_create()
    store = DeviceCredentialStore(tmp_path / "agent")
    credential = DeviceCredential(
        device_id=identity.device_id, credential_id="cred_" + "a" * 32,
        credential_secret="private-test-value" * 3,
        hub_endpoint="http://hub.local", api_endpoint="http://hub.local:8887",
    )
    store.save(credential)
    assert store.load() == credential
    # Older releases reject unknown fields: keep the original credential schema.
    assert "hub_endpoint" not in json.loads(store.path.read_text())
    assert "api_endpoint" not in json.loads(store.path.read_text())
    FileProvisioningStore(tmp_path / "setup").save(snapshot())
    settings = AgentSettings(data_dir=tmp_path / "agent", provisioning_data_dir=tmp_path / "setup")
    for _ in range(2):
        with TestClient(create_app(settings)) as client:
            assert client.get("/api/v1/agent/hub-connection").json()["state"] == "credential_available"
    assert started == ["http://hub.local:8887"] * 2
