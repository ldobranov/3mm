import sqlite3

import pytest

from three_mm_protocol import AgentRole
from three_mm_provisioning import FileProvisioningStore, ProvisioningSnapshot, ProvisioningState
from three_mm_runtime.install_bootstrap import prepare
from three_mm_runtime.install_profile import InstallProfile, NetworkBackend


def paths(tmp_path):
    net = tmp_path / "net"
    net.mkdir()
    database = tmp_path / "core/3mm.db"
    database.parent.mkdir()
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE users (id INTEGER, username TEXT, role TEXT)")
        db.execute("INSERT INTO users VALUES (1, 'existing-admin', 'admin')")
    db.close()
    return dict(data_dir=tmp_path / "provisioning", database=database, network_root=net)


@pytest.mark.parametrize("wireless", [None, "wlan0", "wlp7s0"])
def test_hardware_never_selects_role_or_changes_state(tmp_path, wireless):
    args = paths(tmp_path)
    if wireless:
        (args["network_root"] / wireless / "wireless").mkdir(parents=True)
    prepare(InstallProfile.FULL, **args, check_only=True)
    prepare(InstallProfile.FULL, **args)
    assert not args["data_dir"].exists()


@pytest.mark.parametrize("role", [AgentRole.HUB, AgentRole.STANDALONE])
def test_explicit_core_role_uses_real_admin_and_is_idempotent(tmp_path, role):
    args = paths(tmp_path)
    prepare(InstallProfile.FULL, **args, role=role, check_only=True)
    assert not args["data_dir"].exists()
    prepare(InstallProfile.FULL, **args, role=role)
    store = FileProvisioningStore(args["data_dir"])
    snapshot = store.load()
    assert snapshot.role is role
    assert snapshot.administrator_name == "existing-admin"
    journal = store.path.read_bytes()
    prepare(InstallProfile.FULL, **args)
    assert store.path.read_bytes() == journal
    from three_mm_provisioning import FileNetworkRecoveryPolicyStore
    assert not FileNetworkRecoveryPolicyStore(
        args["database"].parent / "network-recovery-policy.json").load().automatic_setup_enabled
    assert not (tmp_path / "agent").exists()


def test_minimal_node_can_select_hub_without_core_database_or_issuing_identity(tmp_path):
    args = paths(tmp_path)
    args["database"].unlink()
    prepare(InstallProfile.NODE, **args, role=AgentRole.NODE, hub_endpoint="http://hub.local")
    snapshot = FileProvisioningStore(args["data_dir"]).load()
    assert snapshot.role is AgentRole.NODE
    assert snapshot.hub_endpoint == "http://hub.local"
    from agent.hub_connection import resolve_hub_connection
    connection = resolve_hub_connection(role=snapshot.role, snapshot=snapshot,
        configured_endpoint=None, has_credential=False)
    assert connection.state == "awaiting_pairing"
    assert not args["database"].exists()
    assert not (tmp_path / "agent").exists()
    assert "token" not in FileProvisioningStore(args["data_dir"]).path.read_text()


@pytest.mark.parametrize("endpoint", [None, "ssh://hub", "http://user:secret@hub", "http://hub:bad", "http://hub/#token", "http://hub:0", "http://hub\n"])
def test_invalid_node_endpoint_fails_before_persistence(tmp_path, endpoint):
    args = paths(tmp_path)
    with pytest.raises(RuntimeError):
        prepare(InstallProfile.NODE, **args, role=AgentRole.NODE, hub_endpoint=endpoint)
    assert not args["data_dir"].exists()


@pytest.mark.parametrize("problem", ["interrupted", "corrupt", "no_admin", "node_promotion"])
def test_invalid_initialization_never_changes_existing_journal(tmp_path, problem):
    args = paths(tmp_path)
    store = FileProvisioningStore(args["data_dir"])
    if problem == "interrupted":
        store.save(ProvisioningSnapshot.attempt_started())
    elif problem == "corrupt":
        args["data_dir"].mkdir()
        store.path.write_text("broken")
    elif problem == "no_admin":
        with sqlite3.connect(args["database"]) as db:
            db.execute("DELETE FROM users")
    before = store.path.read_bytes() if store.path.exists() else None
    with pytest.raises(RuntimeError):
        prepare(InstallProfile.NODE if problem == "node_promotion" else InstallProfile.FULL,
                **args, role=AgentRole.HUB, check_only=True)
    assert (store.path.read_bytes() if store.path.exists() else None) == before


def test_existing_role_policy_and_recovery_marker_are_preserved(tmp_path):
    from three_mm_provisioning import FileNetworkRecoveryMarker
    args = paths(tmp_path)
    store = FileProvisioningStore(args["data_dir"])
    store.save(ProvisioningSnapshot(state=ProvisioningState.PROVISIONED,
        role=AgentRole.HUB, locale="bg", device_name="unchanged", administrator_name="operator"))
    marker = FileNetworkRecoveryMarker(args["data_dir"] / "network-recovery.json")
    marker.activate("automatic")
    policy = args["database"].parent / "network-recovery-policy.json"
    policy.write_text('{"schema_version":1,"automatic_setup_enabled":true,"offline_after_seconds":600}')
    before = policy.read_bytes(), store.path.read_bytes(), marker.path.read_bytes()
    prepare(InstallProfile.FULL, **args)
    assert (policy.read_bytes(), store.path.read_bytes(), marker.path.read_bytes()) == before
    with pytest.raises(RuntimeError, match="existing device role"):
        prepare(InstallProfile.FULL, **args, role=AgentRole.STANDALONE)


def test_nm_first_boot_needs_no_specific_wifi_interface(tmp_path):
    args = paths(tmp_path)
    prepare(InstallProfile.FULL, **args, network_backend=NetworkBackend.NETWORK_MANAGER)
    (args["network_root"] / "wlan0/wireless").mkdir(parents=True)
    prepare(InstallProfile.FULL, **args, network_backend=NetworkBackend.NETWORK_MANAGER)
    assert not args["data_dir"].exists()
