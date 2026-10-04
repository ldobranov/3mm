import sqlite3
from pathlib import Path

import pytest

from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    FileProvisioningStore,
    ProvisioningSnapshot,
    ProvisioningState,
)
from three_mm_runtime.install_bootstrap import prepare
from three_mm_runtime.install_profile import InstallProfile


def paths(tmp_path):
    net = tmp_path / "net"
    net.mkdir()
    database = tmp_path / "core/3mm.db"
    database.parent.mkdir()
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE users (id INTEGER, username TEXT, role TEXT)")
        db.execute("INSERT INTO users VALUES (1, 'existing-admin', 'admin')")
    return dict(data_dir=tmp_path / "provisioning", database=database, network_root=net)


def test_vm_preflight_is_read_only_and_initialization_is_idempotent(tmp_path):
    args = paths(tmp_path)
    prepare(InstallProfile.FULL, **args, check_only=True)
    assert not args["data_dir"].exists()
    prepare(InstallProfile.FULL, **args)
    store = FileProvisioningStore(args["data_dir"])
    snapshot = store.load()
    assert snapshot.state is ProvisioningState.PROVISIONED
    assert snapshot.role is AgentRole.STANDALONE
    assert snapshot.administrator_name == "existing-admin"
    journal = store.path.read_bytes()
    prepare(InstallProfile.FULL, **args)
    assert store.path.read_bytes() == journal
    from three_mm_provisioning import FileNetworkRecoveryPolicyStore

    assert (
        not FileNetworkRecoveryPolicyStore(
            args["database"].parent / "network-recovery-policy.json"
        )
        .load()
        .automatic_setup_enabled
    )
    assert not (
        tmp_path / "agent"
    ).exists()  # identity/pairing is owned by the existing bootstrap


def test_wifi_keeps_existing_first_boot_setup(tmp_path):
    args = paths(tmp_path)
    (args["network_root"] / "wlan0/wireless").mkdir(parents=True)
    prepare(InstallProfile.FULL, **args)
    assert not args["data_dir"].exists()


@pytest.mark.parametrize(
    "problem",
    ["interrupted", "recovery", "node", "alternate_wifi", "corrupt", "no_admin"],
)
def test_preflight_fails_closed_without_changing_state(tmp_path, problem):
    args = paths(tmp_path)
    profile = InstallProfile.NODE if problem == "node" else InstallProfile.FULL
    store = FileProvisioningStore(args["data_dir"])
    if problem == "interrupted":
        store.save(ProvisioningSnapshot.attempt_started())
    if problem == "recovery":
        args["data_dir"].mkdir()
        (args["data_dir"] / "network-recovery.json").write_text("{}")
    if problem == "alternate_wifi":
        (args["network_root"] / "wlp0/wireless").mkdir(parents=True)
    if problem == "corrupt":
        args["data_dir"].mkdir()
        store.path.write_text("broken")
    if problem == "no_admin":
        with sqlite3.connect(args["database"]) as db:
            db.execute("DELETE FROM users")
    before = store.path.read_bytes() if store.path.exists() else None
    with pytest.raises(RuntimeError):
        prepare(profile, **args, check_only=True)
    assert (store.path.read_bytes() if store.path.exists() else None) == before


def test_existing_role_and_user_recovery_choice_preserved(tmp_path):
    args = paths(tmp_path)
    store = FileProvisioningStore(args["data_dir"])
    store.save(
        ProvisioningSnapshot(
            state=ProvisioningState.PROVISIONED,
            role=AgentRole.HUB,
            locale="bg",
            device_name="unchanged",
            administrator_name="operator",
        )
    )
    policy = args["database"].parent / "network-recovery-policy.json"
    policy.write_text(
        '{"schema_version":1,"automatic_setup_enabled":true,"offline_after_seconds":600}'
    )
    before = policy.read_bytes(), store.path.read_bytes()
    prepare(InstallProfile.FULL, **args)
    assert (policy.read_bytes(), store.path.read_bytes()) == before
