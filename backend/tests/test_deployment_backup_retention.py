from __future__ import annotations

from pathlib import Path

import pytest

from deployment.deployment_backup_retention import (
    BackupInfo,
    BackupRetentionSafetyError,
    create_backup_retention_plan,
)


def backup(name: str, modified_ns: int, size_bytes: int = 100) -> BackupInfo:
    return BackupInfo(
        name=name,
        path=Path("/var/lib/3mm/deploy-backups") / name,
        modified_ns=modified_ns,
        size_bytes=size_bytes,
    )


def test_backup_retention_protects_active_and_recent_recovery_points():
    backups = [backup(f"release-{index}", index) for index in range(1, 7)]

    plan = create_backup_retention_plan(
        backups,
        active_release="release-1",
        rollback_release="release-2",
        keep_history=2,
    )

    assert {
        item.name: reason for item, reason in plan.protected
    } == {
        "release-6": "recent-recovery",
        "release-5": "recent-recovery",
        "release-1": "active-rollback",
        "release-2": "rollback-release",
    }
    assert [item.name for item in plan.delete_candidates] == [
        "release-3",
        "release-4",
    ]
    assert plan.reclaimable_bytes == 200


def test_backup_retention_blocks_cleanup_without_active_backup():
    with pytest.raises(BackupRetentionSafetyError, match="active release has no"):
        create_backup_retention_plan(
            [backup("old", 1)],
            active_release="active",
            rollback_release="old",
            keep_history=0,
        )


def test_backup_retention_blocks_cleanup_without_rollback_backup():
    with pytest.raises(BackupRetentionSafetyError, match="rollback release has no"):
        create_backup_retention_plan(
            [backup("active", 2)],
            active_release="active",
            rollback_release="rollback",
            keep_history=0,
        )


def test_backup_retention_rejects_negative_history():
    with pytest.raises(ValueError, match="must not be negative"):
        create_backup_retention_plan(
            [backup("active", 1)],
            active_release="active",
            rollback_release="rollback",
            keep_history=-1,
        )


def test_backup_retention_rejects_duplicate_names():
    with pytest.raises(BackupRetentionSafetyError, match="Duplicate"):
        create_backup_retention_plan(
            [backup("active", 1), backup("active", 2)],
            active_release="active",
            rollback_release="rollback",
            keep_history=0,
        )
