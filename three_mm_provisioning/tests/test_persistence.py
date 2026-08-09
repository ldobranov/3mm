import json
import os
import stat

import pytest

from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    FileProvisioningStore,
    NetworkCredentials,
    ProvisioningRequest,
    ProvisioningSnapshot,
    ProvisioningState,
    ProvisioningStoreError,
)


def _request() -> ProvisioningRequest:
    return ProvisioningRequest(
        network=NetworkCredentials(
            network_name="private-test-network",
            passphrase="not-a-real-secret",
        ),
        locale="bg-BG",
        device_name="mock-node",
        administrator_name="admin",
        role=AgentRole.NODE,
        hub_endpoint="https://hub.test",
    )


def test_file_store_round_trip_excludes_network_credentials(tmp_path):
    store = FileProvisioningStore(tmp_path)
    snapshot = ProvisioningSnapshot.provisioned(_request())

    store.save(snapshot)
    stored_text = store.path.read_text(encoding="utf-8")

    assert store.load() == snapshot
    assert "private-test-network" not in stored_text
    assert "not-a-real-secret" not in stored_text
    assert not store.path.with_suffix(".tmp").exists()
    if os.name == "posix":
        assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_corrupt_snapshot_fails_without_replacing_it(tmp_path):
    store = FileProvisioningStore(tmp_path)
    store.path.write_text('{"state": "broken"}', encoding="utf-8")

    with pytest.raises(ProvisioningStoreError):
        store.load()

    assert json.loads(store.path.read_text(encoding="utf-8")) == {"state": "broken"}


def test_snapshot_with_invalid_json_types_fails_closed(tmp_path):
    store = FileProvisioningStore(tmp_path)
    store.path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": ["provisioned"],
                "role": "node",
                "locale": "bg-BG",
                "device_name": "mock-node",
                "administrator_name": "admin",
                "hub_endpoint": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProvisioningStoreError):
        store.load()


def test_attempt_snapshot_contains_only_recovery_phase():
    snapshot = ProvisioningSnapshot.attempt_started()

    assert snapshot.state is ProvisioningState.APPLYING_NETWORK
    assert snapshot.to_dict() == {
        "schema_version": 1,
        "state": "applying_network",
        "role": None,
        "locale": None,
        "device_name": None,
        "administrator_name": None,
        "hub_endpoint": None,
    }
