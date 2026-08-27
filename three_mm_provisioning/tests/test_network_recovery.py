import os
from pathlib import Path

import pytest

from three_mm_provisioning import (
    FileNetworkRecoveryMarker,
    FileNetworkRecoveryPolicyStore,
    NetworkRecoveryPolicy,
    NetworkRecoveryStoreError,
)


def test_missing_policy_defaults_to_enabled_after_five_minutes(tmp_path: Path) -> None:
    policy = FileNetworkRecoveryPolicyStore(tmp_path / "policy.json").load()

    assert policy.automatic_setup_enabled is True
    assert policy.offline_after_seconds == 300


def test_policy_is_persisted_without_secrets_and_with_private_permissions(
    tmp_path: Path,
) -> None:
    store = FileNetworkRecoveryPolicyStore(tmp_path / "policy.json")
    store.save(NetworkRecoveryPolicy(automatic_setup_enabled=False))

    assert store.load().automatic_setup_enabled is False
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o777 == 0o600
    assert "pass" not in store.path.read_text(encoding="utf-8").lower()


def test_invalid_policy_disables_automatic_decisions_instead_of_resetting_defaults(
    tmp_path: Path,
) -> None:
    path = tmp_path / "policy.json"
    path.write_text('{"automatic_setup_enabled":"yes"}', encoding="utf-8")

    with pytest.raises(NetworkRecoveryStoreError):
        FileNetworkRecoveryPolicyStore(path).load()


def test_recovery_marker_is_explicit_and_recoverable(tmp_path: Path) -> None:
    marker = FileNetworkRecoveryMarker(tmp_path / "network-recovery.json")

    marker.activate("manual")
    assert marker.is_active() is True
    marker.clear()
    assert marker.is_active() is False
