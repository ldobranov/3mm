from __future__ import annotations

from pathlib import Path

import pytest

from deployment import release_retention
from deployment.release_retention import (
    ReleaseInfo,
    RetentionSafetyError,
    create_retention_plan,
)


def release(name: str, modified_ns: int, size_bytes: int = 100) -> ReleaseInfo:
    return ReleaseInfo(
        name=name,
        path=Path("/opt/3mm/releases") / name,
        modified_ns=modified_ns,
        size_bytes=size_bytes,
    )


def test_retention_protects_active_rollback_and_recent_history():
    releases = [release(f"release-{index}", index) for index in range(1, 7)]

    plan = create_retention_plan(
        releases,
        current_release="release-6",
        rollback_release="release-1",
        keep_history=2,
    )

    assert {
        item.name: reason for item, reason in plan.protected
    } == {
        "release-6": "active",
        "release-5": "recent-history",
        "release-4": "recent-history",
        "release-1": "rollback",
    }
    assert [item.name for item in plan.delete_candidates] == ["release-2", "release-3"]
    assert plan.reclaimable_bytes == 200
    assert plan.can_apply is True


def test_retention_dry_run_can_report_without_a_rollback_link():
    plan = create_retention_plan(
        [release("old", 1), release("active", 2)],
        current_release="active",
        rollback_release=None,
        keep_history=0,
    )

    assert [item.name for item in plan.delete_candidates] == ["old"]
    assert plan.can_apply is False


@pytest.mark.parametrize("missing", ["active", "rollback"])
def test_retention_rejects_missing_protected_release(missing: str):
    releases = [release("active", 2), release("rollback", 1)]
    releases = [item for item in releases if item.name != missing]

    with pytest.raises(RetentionSafetyError, match="not present"):
        create_retention_plan(
            releases,
            current_release="active",
            rollback_release="rollback",
            keep_history=0,
        )


def test_retention_rejects_negative_history():
    with pytest.raises(ValueError, match="must not be negative"):
        create_retention_plan(
            [release("active", 1)],
            current_release="active",
            rollback_release=None,
            keep_history=-1,
        )


def test_retention_rejects_active_release_as_rollback():
    with pytest.raises(RetentionSafetyError, match="must differ"):
        create_retention_plan(
            [release("active", 1)],
            current_release="active",
            rollback_release="active",
            keep_history=0,
        )


def test_apply_is_blocked_without_an_explicit_rollback(monkeypatch):
    plan = create_retention_plan(
        [release("old", 1), release("active", 2)],
        current_release="active",
        rollback_release=None,
        keep_history=0,
    )
    monkeypatch.setattr(release_retention, "_running_as_root", lambda: True)

    with pytest.raises(RetentionSafetyError, match="No explicit rollback"):
        release_retention.apply_retention(plan, install_root=Path("/opt/3mm"))
