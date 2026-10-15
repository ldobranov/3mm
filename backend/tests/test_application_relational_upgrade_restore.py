"""Actual migration, interrupted fixed restore and fresh explicit completion."""

import json
import os
from pathlib import Path

import pytest

from backend.services import application_authority_management as authority
from backend.services.application_relational_upgrade_admin import inspect_upgrade_source
from backend.tests import test_application_relational_upgrade_rollback as rollback_cases
from backend.tests.test_application_relational_preparation import (
    ROOT_ONLY,
    SECRET,
    action,
    identity,
    managed_installed,
    prepared_paths,
    source_installed,
    source_subject,
    stopped,
)
from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeRollbackTicket,
)
from three_mm_application_sdk.relational_wire import verify_metadata
from three_mm_runtime import application_database_snapshot as snapshots
from three_mm_runtime import application_relational_upgrade as upgrade_helper
from three_mm_runtime import application_relational_upgrade_restore as restore_helper

pytestmark = [
    ROOT_ONLY,
    pytest.mark.skipif(os.name != "posix", reason="Actual POSIX worker"),
]
upgradable = rollback_cases.upgradable


def partial(state, monkeypatch, point="database_detached"):
    state.failed = rollback_cases.upgrade_issue(state)
    real_worker = upgrade_helper.run_prepared_upgrade_migrations
    real_replace, real_rename = os.replace, os.rename
    real_write = upgrade_helper._write_atomic
    real_backup = snapshots._backup
    publication_failed = []
    hits = []

    def migrated(*args, **kw):
        real_worker(*args, **kw)
        if point != "publication":
            raise RuntimeError("Committed migration, original rollback required")

    def backup(src, dst, **kw):
        result = real_backup(src, dst, **kw)
        if (
            point == "database_staged"
            and Path(dst).name == "restored-state.sqlite3"
            and not hits
        ):
            hits.append(point)
            raise OSError("Injected SQLite staging interruption")
        return result

    def replace(src, dst, *a, **kw):
        selected = (
            point == "database_detached" and Path(dst).name == "candidate-state.sqlite3"
        )
        result = real_replace(src, dst, *a, **kw)
        if selected and not hits:
            hits.append(point)
            raise OSError("Injected restore interruption")
        return result

    def rename(src, dst, *a, **kw):
        selected = (
            point == "files_detached" and str(dst) == "candidate-sdk-files"
        ) or (
            point == "files_staged"
            and str(src) == "sdk-files"
            and str(dst) == "candidate-sdk-files"
        )
        if selected and point == "files_staged" and not hits:
            hits.append(point)
            raise OSError("Injected stage interruption")
        result = real_rename(src, dst, *a, **kw)
        if selected and not hits:
            hits.append(point)
            raise OSError("Injected detach interruption")
        return result

    def write(path, *a, **kw):
        result = real_write(path, *a, **kw)
        if (
            point == "publication"
            and Path(path) == state.instance / "relational.json"
            and not publication_failed
        ):
            publication_failed.append(True)
            raise RuntimeError("New publication written; original rollback required")
        if (
            point == "publication"
            and Path(path) == state.instance / "active.json"
            and publication_failed
            and not hits
        ):
            hits.append(point)
            raise OSError("Injected metadata interruption")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(upgrade_helper, "run_prepared_upgrade_migrations", migrated)
        patch.setattr(os, "replace", replace)
        patch.setattr(os, "rename", rename)
        patch.setattr(os, "supports_dir_fd", os.supports_dir_fd | {rename})
        patch.setattr(snapshots, "_backup", backup)
        patch.setattr(upgrade_helper, "_write_atomic", write)
        with pytest.raises(upgrade_helper.RelationalUpgradeError) as failure:
            rollback_cases.upgrade(state, state.failed)
    state.marker = state.instance / (
        ".database-" + state.failed["preparation_id"] + ".rollback"
    )
    assert hits == [point], (
        repr(failure.value.__cause__),
        repr(getattr(failure.value.__cause__, "__cause__", None)),
    )
    assert (
        json.loads((state.marker / "upgrade.json").read_bytes())["phase"] == "restoring"
    )
    return state


def issue(state, **changes):
    return rollback_cases.issue(
        state, confirm_finish_interrupted_restore=True, **changes
    )


@pytest.mark.parametrize(
    "point",
    [
        "files_staged",
        "files_detached",
        "database_staged",
        "database_detached",
        "publication",
    ],
)
def test_partial_restore_finishes_without_replaying_migration(
    upgradable, monkeypatch, point
):
    state = partial(upgradable, monkeypatch, point)
    preimage = (state.marker / "state.sqlite3").read_bytes()
    files = (state.marker / "files.json").read_bytes()
    monkeypatch.setattr(
        upgrade_helper,
        "run_prepared_upgrade_migrations",
        lambda *a, **kw: pytest.fail("Migration replay"),
    )
    # Readonly confirmation must NOT become implicit restore authority.
    with pytest.raises(rollback_cases.REFUSALS + (RuntimeError,)):
        rollback_cases.run(state, rollback_cases.issue(state))
    ticket = issue(state)
    verify_metadata(SECRET, "database_upgrade_restore", ticket)
    with pytest.raises(ValueError):
        _RelationalUpgradeRollbackTicket.model_validate(ticket)
    result = rollback_cases.run(state, ticket)
    assert result["outcome"] == "restored_not_started"
    assert action(state, state.failed)["state"] == "execution_unconfirmed"
    assert action(state, ticket)["state"] == "confirmed"
    archived = state.instance / (
        ".upgrade-rollback-evidence-" + state.failed["preparation_id"]
    )
    assert (archived / "state.sqlite3").read_bytes() == preimage
    assert (archived / "files.json").read_bytes() == files
    assert not list(state.instance.glob(".database-*.rollback"))
    rollback_cases.original(state)
    assert all(call[0] == "stop" for call in state.calls)
    assert not state.manager.inspect(1)["grant_effective"]


def test_interrupted_new_restore_requires_fresh_ticket_and_keeps_all_stages(
    upgradable, monkeypatch
):
    state = partial(upgradable, monkeypatch)
    ticket = issue(state)
    real = restore_helper.restore_database
    with monkeypatch.context() as patch:

        def detached(*a, **kw):
            real(*a, **kw)
            raise OSError("New recovery interrupted after DB switch")

        patch.setattr(restore_helper, "restore_database", detached)
        with pytest.raises(upgrade_helper.RelationalUpgradeError):
            rollback_cases.run(state, ticket)
    marker = state.instance / (".database-" + ticket["preparation_id"] + ".rollback")
    assert (marker / "restore-work/partial-state.sqlite3-wal").exists() or (
        marker / "restore-work/state.sqlite3"
    ).exists()
    with pytest.raises(rollback_cases.REFUSALS + (RuntimeError,)):
        rollback_cases.run(state, ticket)
    fresh = issue(state)
    rollback_cases.run(state, fresh)
    assert action(state, ticket)["data"]["superseded_by"] == fresh["preparation_id"]
    assert (
        state.instance
        / (".upgrade-rollback-evidence-" + ticket["preparation_id"])
        / "restore-work/state.sqlite3"
    ).exists()
    rollback_cases.original(state)


@pytest.mark.parametrize("ack", ["before", "after"])
def test_lost_finish_after_restore_uses_readonly_confirmation(
    upgradable, monkeypatch, ack
):
    state = partial(upgradable, monkeypatch)
    ticket = issue(state)

    def lost(*a, **kw):
        if a[1] == "finish" and ack == "before":
            raise OSError("Lost before Core finish")
        result = rollback_cases.checkpoint(state, *a, **kw)
        if a[1] == "finish":
            raise OSError("Lost after Core finish")
        return result

    with pytest.raises(upgrade_helper.RelationalUpgradeError):
        rollback_cases.run(state, ticket, lost)
    # No fixed restore can be repeated over an already witnessed completion.
    with pytest.raises(rollback_cases.REFUSALS + (RuntimeError,)):
        rollback_cases.run(state, issue(state))
    monkeypatch.setattr(
        restore_helper,
        "finish_partial_restore",
        lambda *a, **kw: pytest.fail("Restore replay"),
    )
    rollback_cases.run(state, rollback_cases.issue(state))
    rollback_cases.original(state)


@pytest.mark.parametrize(
    "problem", ["backup", "files", "metadata", "key", "stop", "foreign", "grant"]
)
def test_partial_restore_refuses_changed_evidence_or_authority(
    upgradable, monkeypatch, problem
):
    state = partial(upgradable, monkeypatch)
    ticket = issue(state)
    if problem == "backup":
        with (state.marker / "state.sqlite3").open("ab") as f:
            f.write(b"corrupt")
    elif problem == "files":
        (state.marker / "files.json").write_bytes(b"{}")
    elif problem == "metadata":
        (state.instance / "active.json").write_bytes(b"{}")
    elif problem == "key":
        (state.transport_keys / (state.instance.name + ".key")).write_bytes(b"x" * 32)
    elif problem == "stop":
        monkeypatch.setattr(
            state.supervisor,
            "stop",
            lambda *a: (_ for _ in ()).throw(OSError("Stop uncertain")),
        )
    elif problem == "foreign":
        (state.instance / (".database-" + identity() + ".rollback")).mkdir(mode=0o700)
    else:
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=state.manager.inspect(1)["grant_record_revision"],
        )
    before = (state.marker / "state.sqlite3").read_bytes()
    with pytest.raises(rollback_cases.REFUSALS + (RuntimeError, OSError)):
        rollback_cases.run(state, ticket)
    assert (state.marker / "state.sqlite3").read_bytes() == before
    assert not list(state.instance.glob(".upgrade-rollback-evidence-*"))


@pytest.mark.parametrize("problem", ["actor", "invalid_actor", "source", "grant"])
def test_admin_inspection_authenticates_and_checks_cas_without_changing_state(
    upgradable, problem
):
    state = upgradable
    values = dict(
        actor_token=state.token,
        source_action_id=state.source["preparation_id"],
        expected_source_revision=action(state, state.source)["revision"],
        expected_grant_record_revision=state.manager.inspect(1)[
            "grant_record_revision"
        ],
    )
    values[
        {
            "actor": "actor_token",
            "invalid_actor": "actor_token",
            "source": "expected_source_revision",
            "grant": "expected_grant_record_revision",
        }[problem]
    ] = (
        "1" * 32
    )
    if problem == "actor":
        values["actor_token"] = state.user_token
    before = action(state, state.source)
    with pytest.raises(rollback_cases.REFUSALS):
        inspect_upgrade_source(state.manager, 1, **values)
    assert action(state, state.source) == before


def test_old_source_clock_is_history_not_replayed_execution_authority(
    upgradable, monkeypatch
):
    state = partial(upgradable, monkeypatch)
    now = state.failed["deadline_ms"] + 1
    monkeypatch.setattr(authority, "_clock", lambda: (state.failed["boot_id"], now))
    # The fresh signed request alone gets a fresh deadline. Root shares that
    # host clock, without editing the historical signed source ticket.
    from three_mm_runtime import application_relational_preparation as preparation

    monkeypatch.setattr(preparation, "_clock", lambda: (state.failed["boot_id"], now))
    ticket = issue(state)
    assert ticket["issued_at_ms"] > state.failed["deadline_ms"]
    rollback_cases.run(state, ticket)
    rollback_cases.original(state)


def test_completed_partial_restore_allows_only_new_reviewed_forward_attempt(
    upgradable, monkeypatch
):
    state = partial(upgradable, monkeypatch)
    rollback_cases.run(state, issue(state))
    state.source_revision = action(state, state.source)["revision"]
    with pytest.raises(rollback_cases.REFUSALS):
        rollback_cases.upgrade_issue(state)
    proof = state.manager.inspect(1)["native_reviews"][0]
    rollback_cases.upgrade_cases.apply(state, proof["native_review_id"])
    fresh = rollback_cases.upgrade_issue(state)
    assert fresh["preparation_id"] != state.failed["preparation_id"]
    rollback_cases.upgrade(state, fresh)
    rollback_cases.original(state)
    assert action(state, state.failed)["state"] == "execution_unconfirmed"
