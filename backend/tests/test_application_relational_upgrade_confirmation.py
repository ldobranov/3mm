"""Real Core + non-root upgrade + Root readonly reconciliation, disposable data."""

import json
import os
import sqlite3
from contextlib import closing
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.session import UserSession
from backend.services import application_authority_management as authority
from backend.services import application_relational_activation as activation
from backend.services import application_relational_upgrade_confirmation as coordinator
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_policy_reviews import PolicyReviewStoreError
from backend.tests.test_application_relational_migrations import candidate, script
from backend.tests.test_application_relational_preparation import (
    ROOT_ONLY,
    SECRET,
    action,
    apply,
    identity,
    managed_installed,
    prepared_paths,
    source_installed,
    source_subject,
    stopped,
)
from backend.tests.test_application_relational_upgrade import (
    checkpoint as upgrade_checkpoint,
)
from backend.tests.test_application_relational_upgrade import issue as issue_upgrade
from backend.tests.test_application_relational_upgrade import (
    original,
)
from backend.tests.test_application_relational_upgrade import run as upgrade
from backend.tests.test_application_relational_upgrade import (
    upgradable,
)
from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeConfirmationTicket,
    _RelationalUpgradeTicket,
    upgraded_lifecycle,
)
from three_mm_application_sdk.relational_wire import canonical, sign_metadata
from three_mm_runtime import application_relational_upgrade as upgrade_helper
from three_mm_runtime import application_relational_upgrade_confirmation as helper
from three_mm_runtime.application_relational_session import _prepared

pytestmark = [
    pytest.mark.skipif(os.name != "posix", reason="Actual POSIX authority/worker"),
    ROOT_ONLY,
]
REFUSALS = (
    authority.AuthorityManagementError,
    AuthorityReviewKeyError,
    PolicyReviewStoreError,
    ValueError,
)


def image(state):
    """Compare the committed DB + WAL, not GC-dependent checkpoint timing.

    sqlite3's connection context manager does not close the connection. Older
    fixture connections may be collected during a callback, checkpointing WAL
    into the main file without any business/metadata SQL change. Serialization
    under a readonly snapshot includes committed WAL pages and closes promptly.
    """
    with closing(
        sqlite3.connect(state.database.absolute().as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.execute("BEGIN")
        return db.serialize()


def test_readonly_image_includes_wal_and_ignores_checkpoint_timing(tmp_path):
    state = SimpleNamespace(database=tmp_path / "snapshot.db")
    with closing(sqlite3.connect(state.database)) as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        db.execute("CREATE TABLE business(value TEXT)")
        db.execute("INSERT INTO business VALUES ('committed in WAL')")
        db.commit()
        raw = state.database.read_bytes()
        snapshot = image(state)
        assert db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0
        assert state.database.read_bytes() != raw
        assert image(state) == snapshot


def interrupt(state, ack="after"):
    state.upgrade = issue_upgrade(state)

    def lose(*args, **kwargs):
        if args[1] == "finish" and ack == "before":
            raise OSError("lost request before Core")
        result = upgrade_checkpoint(state, *args, **kwargs)
        if args[1] == "finish":
            raise OSError("lost response after Core")
        return result

    with pytest.raises(upgrade_helper.RelationalUpgradeError):
        upgrade(state, state.upgrade, lose)
    return state


@pytest.fixture
def interrupted(upgradable):
    return interrupt(upgradable)


def issue(state, **changes):
    return coordinator.issue_published_upgrade_confirmation(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "source_upgrade_id": state.upgrade["preparation_id"],
            "expected_source_revision": action(state, state.upgrade)["revision"],
            "expected_grant_record_revision": state.manager.inspect(1)[
                "grant_record_revision"
            ],
            "confirm_published_upgrade_reviewed": True,
            "transport_secret": SECRET,
            **changes,
        },
    )


def checkpoint(state, *args, **kwargs):
    return coordinator.upgrade_confirmation_checkpoint(
        state.manager,
        1,
        *args,
        actor_token=state.token,
        transport_secret=SECRET,
        **kwargs,
    )


def run(state, ticket, callback=None):
    return helper.confirm_published_relational_upgrade(
        state.source_archive,
        state.archive,
        ticket,
        state.upgrade,
        configuration=state.configuration,
        root=state.runtime,
        key_root=state.transport_keys,
        state_root=state.helper_state,
        service_uid=1200,
        service_gid=1201,
        supervisor=state.supervisor,
        checkpoint=callback or (lambda *a, **kw: checkpoint(state, *a, **kw)),
    )


@pytest.mark.parametrize("ack", ["before", "after"])
def test_readonly_confirmation_retains_schema_lineage_old_receipts_and_preimages(
    upgradable, monkeypatch, ack
):
    state = interrupt(upgradable, ack)
    prior_state = action(state, state.upgrade)["state"]
    before = image(state)
    record = (state.instance / "relational.json").read_bytes()
    marker = next(state.instance.glob(".database-*.rollback"))
    preimage = (marker / "state.sqlite3").read_bytes()
    monkeypatch.setattr(
        upgrade_helper,
        "run_prepared_upgrade_migrations",
        lambda *a, **kw: pytest.fail("Migration replay"),
    )
    monkeypatch.setattr(
        upgrade_helper,
        "upgrade_receipt_lineage",
        lambda *a, **kw: pytest.fail("Lineage rewrite"),
    )
    ticket = issue(state)
    assert ticket["authority_epoch"] != state.upgrade["authority_epoch"]
    assert ticket["database_lineage"] == state.upgrade["database_lineage"]

    def unlocked(*args, **kwargs):
        with sqlite3.connect(state.database, timeout=0) as db:
            db.execute("BEGIN IMMEDIATE")
            db.rollback()
        return checkpoint(state, *args, **kwargs)

    result = run(state, ticket, unlocked)
    source = action(state, state.upgrade)
    assert (
        source["state"] == "upgraded" and action(state, ticket)["state"] == "confirmed"
    )
    if prior_state == "execution_unconfirmed":
        assert source["data"]["confirmation_previous_state"] == prior_state
    assert result["outcome"] == "upgraded_not_started"
    assert image(state) == before
    assert (state.instance / "relational.json").read_bytes() == record
    assert _prepared(state.instance, SECRET) == upgraded_lifecycle(
        state.upgrade, SECRET
    )
    original(state)
    archive = state.instance / (".upgrade-evidence-" + state.upgrade["preparation_id"])
    assert (archive / "state.sqlite3").read_bytes() == preimage
    assert not any(
        os.path.lexists(archive / ("state.sqlite3" + suffix))
        for suffix in ("-wal", "-shm", "-journal")
    )
    assert not list(state.instance.glob(".database-*.rollback"))
    assert len(list(state.instance.glob(".upgrade-confirmation-evidence-*"))) == 1
    with Session(state.engine) as db:
        installed = db.get(Installation, 1)
        assert (
            not installed.enabled
            and installed.status == "disabled"
            and installed.authority_mode == "review_required"
        )
    assert not state.manager.inspect(1)["grant_effective"]
    assert all(call[0] == "stop" for call in state.calls)
    assert checkpoint(state, ticket, "finish", receipt=result) == {
        "state": "upgraded_not_started",
        "historical": True,
    }
    with pytest.raises(REFUSALS):
        upgrade_checkpoint(
            state, state.upgrade, "finish", receipt=source["data"]["receipt"]
        )
    with pytest.raises(REFUSALS):
        run(state, ticket)


@pytest.mark.parametrize(
    "changes",
    [
        {"confirm_published_upgrade_reviewed": False},
        {"actor_token": "invalid"},
        {"expected_source_revision": "1" * 32},
        {"expected_grant_record_revision": "2" * 32},
        {"source_upgrade_id": "3" * 32},
    ],
)
def test_confirmation_requires_current_admin_exact_source_and_explicit_consent(
    interrupted, changes
):
    with pytest.raises(REFUSALS):
        issue(interrupted, **changes)
    original(interrupted)


@pytest.mark.parametrize(
    "drift",
    [
        "actor",
        "native",
        "grant",
        "epoch",
        "configuration",
        "enabled",
        "generation",
        "key",
        "boot",
        "deadline",
    ],
)
def test_each_checkpoint_rechecks_live_authority(interrupted, monkeypatch, drift):
    state = interrupted
    ticket = issue(state)
    checkpoint(state, ticket, "begin")
    with Session(state.engine) as db:
        sealed_before = db.get(Action, ticket["preparation_id"]).payload
    if drift == "native":
        proof = state.manager.inspect(1)["native_reviews"][0]
        state.manager.revoke_native_review(
            1,
            actor_token=state.token,
            request_id=identity(),
            native_review_id=proof["native_review_id"],
            expected_revision=proof["revision"],
        )
    elif drift == "grant":
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=state.manager.inspect(1)["grant_record_revision"],
        )
    elif drift == "key":
        state.keys.rotate(expected_key_id=state.keys.identity().key_id)
    elif drift in {"boot", "deadline"}:
        monkeypatch.setattr(
            authority,
            "_clock",
            lambda: (
                (
                    ticket["boot_id"]
                    if drift == "deadline"
                    else "00000000-0000-0000-0000-000000000001"
                ),
                ticket["deadline_ms"],
            ),
        )
    else:
        with state.engine.begin() as db:
            if drift == "actor":
                db.execute(update(UserSession).values(is_active=False))
            elif drift == "generation":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            else:
                db.execute(
                    update(Installation).values(
                        **{
                            "epoch": {"authority_epoch": identity()},
                            "enabled": {"enabled": True, "status": "active"},
                            "configuration": {
                                "configuration": {
                                    **state.configuration,
                                    "PRIVATE_NOTE": "changed",
                                }
                            },
                        }[drift]
                    )
                )
    with pytest.raises(REFUSALS):
        checkpoint(state, ticket, "check")
    # A key/generation change deliberately makes authenticated decoding fail.
    # Compare the retained sealed bytes, without bypassing that security fence.
    with Session(state.engine) as db:
        assert db.get(Action, ticket["preparation_id"]).payload == sealed_before
    assert list(state.instance.glob(".database-*.rollback"))


@pytest.mark.parametrize(
    "problem",
    [
        "record",
        "active",
        "lineage",
        "receipt",
        "missing_receipt",
        "history",
        "preimage",
        "previous_record",
        "previous_active",
        "files",
        "wheel",
        "source_wheel",
        "key",
        "symlink",
        "unknown_marker",
        "phase",
        "marker_ticket",
        "archive_collision",
        "stop",
    ],
)
def test_invalid_or_partial_upgrade_is_never_repaired(
    interrupted, monkeypatch, problem
):
    state = interrupted
    ticket = issue(state)
    marker = next(state.instance.glob(".database-*.rollback"))
    if problem in {"record", "active", "previous_record", "previous_active"}:
        path = {
            "record": state.instance / "relational.json",
            "active": state.instance / "active.json",
            "previous_record": marker / "previous-relational.json",
            "previous_active": marker / "previous-active.json",
        }[problem]
        path.write_bytes(b"{}")
    elif problem in {"lineage", "receipt", "missing_receipt", "history"}:
        with sqlite3.connect(state.database) as db:
            if problem == "lineage":
                db.execute("UPDATE three_mm_relational_lineage SET payload='{}'")
            elif problem == "receipt":
                db.execute("UPDATE three_mm_relational_commits SET payload='{}'")
            elif problem == "missing_receipt":
                db.execute("DELETE FROM three_mm_relational_commits")
            else:
                db.execute(
                    "DELETE FROM three_mm_schema_migrations WHERE revision='0001'"
                )
    elif problem == "preimage":
        with (marker / "state.sqlite3").open("ab") as stream:
            stream.write(b"corrupt")
    elif problem == "files":
        next(
            path for path in (marker / "sdk-files").iterdir() if path.name != ".lock"
        ).write_bytes(b"corrupt")
    elif problem in {"wheel", "source_wheel"}:
        digest = (
            ticket["package_sha256"]
            if problem == "wheel"
            else state.upgrade["source_package_sha256"]
        )
        (state.instance / "releases" / digest / "service.whl").write_bytes(b"changed")
    elif problem == "key":
        (state.transport_keys / (state.instance.name + ".key")).write_bytes(b"x" * 32)
    elif problem == "symlink":
        path = state.instance / "relational.json"
        path.rename(state.instance / "old-record")
        path.symlink_to(state.instance / "old-record")
    elif problem == "unknown_marker":
        (state.instance / (".database-" + identity() + ".rollback")).mkdir(mode=0o700)
    elif problem == "phase":
        path = marker / "upgrade.json"
        path.write_bytes(
            canonical({**json.loads(path.read_bytes()), "phase": "migrating_schema"})
        )
    elif problem == "marker_ticket":
        path = marker / "upgrade.json"
        proof = json.loads(path.read_bytes())
        proof["ticket"]["version"] = True
        path.write_bytes(canonical(proof))
    elif problem == "archive_collision":
        archive = state.instance / (
            ".upgrade-evidence-" + state.upgrade["preparation_id"]
        )
        archive.mkdir(mode=0o700)
        (archive / "preserve").write_bytes(b"foreign evidence")
    else:
        monkeypatch.setattr(
            state.supervisor,
            "stop",
            lambda *a: (_ for _ in ()).throw(OSError("unconfirmed stop")),
        )
    before = image(state)
    with pytest.raises((RuntimeError, ValueError, OSError)):
        run(state, ticket)
    assert image(state) == before
    assert list(state.instance.glob(".database-*.rollback"))
    assert not list(state.instance.glob(".upgrade-confirmation-evidence-*"))
    with pytest.raises(ValueError, match="pending"):
        _prepared(state.instance, SECRET)


@pytest.mark.parametrize("ack", ["before", "after"])
def test_interrupted_confirmation_requires_new_human_action_without_replay(
    interrupted, ack
):
    state = interrupted
    ticket = issue(state)

    def lose(*args, **kwargs):
        if args[1] == "finish" and ack == "before":
            raise OSError("lost before Core")
        result = checkpoint(state, *args, **kwargs)
        if args[1] == "finish":
            raise OSError("lost after Core")
        return result

    with pytest.raises(upgrade_helper.RelationalUpgradeError):
        run(state, ticket, lose)
    before = image(state)
    with pytest.raises(REFUSALS):
        run(state, ticket)
    fresh = issue(state)
    assert fresh["authority_epoch"] != ticket["authority_epoch"]
    with pytest.raises(REFUSALS):
        checkpoint(state, ticket, "check")
    run(state, fresh)
    assert action(state, ticket)["data"]["superseded_by"] == fresh["preparation_id"]
    assert image(state) == before
    assert not list(state.instance.glob(".database-*.rollback"))
    assert len(list(state.instance.glob(".upgrade-confirmation-evidence-*"))) == 2
    original(state)


def test_partial_archive_can_be_confirmed_again_without_losing_evidence(
    interrupted, monkeypatch
):
    state = interrupted
    ticket = issue(state)
    sync = helper._sync_directory
    failed = []

    def fail_once(path):
        if not failed:
            failed.append(True)
            raise OSError("Interrupted archive synchronization")
        sync(path)

    with monkeypatch.context() as patch:
        patch.setattr(helper, "_sync_directory", fail_once)
        with pytest.raises(upgrade_helper.RelationalUpgradeError):
            run(state, ticket)
    assert action(state, ticket)["state"] == "confirmed"
    assert list(state.instance.glob(".database-*.rollback"))
    run(state, issue(state))
    assert not list(state.instance.glob(".database-*.rollback"))
    assert len(list(state.instance.glob(".upgrade-confirmation-evidence-*"))) == 2
    original(state)


def test_boot_evidence_is_never_cleared_by_upgrade_confirmation(interrupted):
    state = interrupted
    ticket = issue(state)
    boot = state.instance / "boot-required.json"
    boot.symlink_to(state.instance / "missing-boot-state")
    calls = list(state.calls)
    with pytest.raises(ValueError, match="Boot policy"):
        run(
            state,
            ticket,
            lambda *a, **kw: pytest.fail("Core called before boot refusal"),
        )
    assert boot.is_symlink() and state.calls == calls


def test_expired_upgrade_is_historical_evidence_not_renewed_worker_permission(
    interrupted, monkeypatch
):
    from three_mm_runtime import (
        application_relational_preparation as preparation_helper,
    )

    state = interrupted
    clock = lambda: (state.upgrade["boot_id"], state.upgrade["deadline_ms"] + 1)
    monkeypatch.setattr(authority, "_clock", clock)
    monkeypatch.setattr(preparation_helper, "_clock", clock)
    ticket = issue(state)
    assert ticket["issued_at_ms"] > state.upgrade["deadline_ms"]
    run(state, ticket)
    original(state)


def test_confirmed_upgrade_is_start_source_only_after_separate_fresh_review(
    interrupted,
):
    state = interrupted
    ticket = issue(state)

    def start():
        return activation.issue_prepared_activation(
            state.manager,
            1,
            actor_token=state.token,
            request_id=identity(),
            source_preparation_id=state.upgrade["preparation_id"],
            expected_grant_record_revision=state.manager.inspect(1)[
                "grant_record_revision"
            ],
            confirm_start_prepared_service=True,
            transport_secret=SECRET,
            service_uid=1200,
            service_gid=1201,
            coordinator_uid=1202,
        )

    with pytest.raises(REFUSALS):
        start()
    run(state, ticket)
    with pytest.raises(REFUSALS):
        start()
    proof = state.manager.inspect(1)["native_reviews"][0]
    apply(state, proof["native_review_id"])
    result = start()
    assert result["source_preparation_id"] == state.upgrade["preparation_id"]
    assert result["database_lineage"] == state.upgrade["database_lineage"]
    assert all(call[0] == "stop" for call in state.calls)


def test_a_fresh_grant_does_not_bypass_an_unconfirmed_upgrade_source(interrupted):
    state = interrupted
    ticket = issue(state)
    proof = state.manager.inspect(1)["native_reviews"][0]
    apply(state, proof["native_review_id"])
    with pytest.raises(
        authority.AuthorityManagementError, match="confirmation_pending"
    ):
        activation.issue_prepared_activation(
            state.manager,
            1,
            actor_token=state.token,
            request_id=identity(),
            source_preparation_id=state.upgrade["preparation_id"],
            expected_grant_record_revision=state.manager.inspect(1)[
                "grant_record_revision"
            ],
            confirm_start_prepared_service=True,
            transport_secret=SECRET,
            service_uid=1200,
            service_gid=1201,
            coordinator_uid=1202,
        )
    assert action(state, ticket)["state"] == "recorded"
    assert list(state.instance.glob(".database-*.rollback"))
    original(state)


def test_confirmation_wire_is_closed_and_cannot_be_worker_or_original_finish(
    interrupted,
):
    state = interrupted
    ticket = issue(state)
    for changes in (
        {"database_path": "/foreign"},
        {"issued_at_ms": True},
        {"action": "upgrade_prepared_schema"},
        {"preparation_id": ticket["source_upgrade_id"]},
    ):
        with pytest.raises(ValidationError):
            _RelationalUpgradeConfirmationTicket.model_validate(
                sign_metadata(
                    SECRET, "database_upgrade_confirmation", {**ticket, **changes}
                )
            )
    with pytest.raises(ValidationError):
        _RelationalUpgradeTicket.model_validate(ticket)
    with pytest.raises(ValueError, match="signature"):
        checkpoint(
            state, sign_metadata(SECRET, "database_upgrade", ticket), "authorize"
        )
    checkpoint(state, ticket, "begin")
    body = {
        "version": 1,
        "preparation_id": ticket["preparation_id"],
        "lifecycle_sha256": ticket["published_lifecycle_sha256"],
        "outcome": "upgraded_not_started",
    }
    for receipt in (
        sign_metadata(SECRET, "database_upgrade_result", body),
        sign_metadata(
            SECRET,
            "database_upgrade_confirmation_result",
            {**body, "lifecycle_sha256": "0" * 64},
        ),
    ):
        with pytest.raises(REFUSALS):
            checkpoint(state, ticket, "finish", receipt=receipt)
    assert action(state, ticket)["state"] == "execution_unconfirmed"


def test_uninterrupted_upgrade_has_nothing_to_reconcile(upgradable):
    state = upgradable
    state.upgrade = issue_upgrade(state)
    upgrade(state, state.upgrade)
    before = image(state)
    with pytest.raises(ValueError, match="No interrupted"):
        run(state, issue(state))
    assert image(state) == before
    assert not list(state.instance.glob(".database-*.rollback"))


def test_upgrade_not_started_is_not_a_published_confirmation_source(upgradable):
    state = upgradable
    state.upgrade = issue_upgrade(state)
    with pytest.raises(authority.AuthorityManagementError, match="source_unavailable"):
        issue(state)
    assert (state.instance / "relational.json").read_bytes() == state.previous_record


def test_real_failed_migration_remains_blocked_for_separate_rollback_reconciliation(
    upgradable,
):
    state = upgradable
    candidate(state, script("raise RuntimeError('migration failed')"))
    state.upgrade = issue_upgrade(state)
    with pytest.raises(upgrade_helper.RelationalUpgradeError):
        upgrade(state, state.upgrade)
    marker = next(state.instance.glob(".database-*.rollback"))
    assert (
        json.loads((marker / "upgrade.json").read_bytes())["phase"]
        == "restored_not_started"
    )
    before = image(state)
    with pytest.raises(ValueError, match="separate recovery"):
        run(state, issue(state))
    assert image(state) == before
    assert action(state, state.upgrade)["state"] == "execution_unconfirmed"
    assert marker.is_dir()
    original(state)


def test_confirmation_checkpoint_budget_is_bounded_before_service_effects(interrupted):
    state = interrupted
    ticket = issue(state)
    for _ in range(helper.MAX_CONFIRMATION_MARKERS):
        (state.instance / (".database-" + identity() + ".rollback")).mkdir(mode=0o700)
    calls = list(state.calls)
    with pytest.raises(ValueError, match="budget exceeded"):
        run(state, ticket)
    assert state.calls == calls
    assert not (
        state.instance / (".database-" + ticket["preparation_id"] + ".rollback")
    ).exists()


def test_confirmed_upgrade_can_be_the_source_of_the_next_real_forward_upgrade(
    interrupted,
):
    state = interrupted
    run(state, issue(state))
    state.source = state.upgrade
    state.source_revision = action(state, state.source)["revision"]
    state.source_archive = state.archive
    candidate(
        state,
        """from three_mm_application_sdk import ApplicationMigration

def applied(db):
    raise RuntimeError('Applied migration must not run')

def third(db):
    db.execute('ALTER TABLE business ADD COLUMN third INTEGER DEFAULT 3')

def get_migrations():
    return [ApplicationMigration('0001', applied), ApplicationMigration('0002', applied), ApplicationMigration('0003', third)]
""",
        revision="0003",
    )
    state.upgrade = issue_upgrade(state)

    def lose(*args, **kwargs):
        if args[1] == "finish":
            raise OSError("Second upgrade finish lost before Core")
        return upgrade_checkpoint(state, *args, **kwargs)

    with pytest.raises(upgrade_helper.RelationalUpgradeError):
        upgrade(state, state.upgrade, lose)
    before = image(state)
    run(state, issue(state))
    assert image(state) == before
    with sqlite3.connect(state.database) as db:
        assert db.execute("SELECT value,migrated,third FROM business").fetchall() == [
            ("preserved", 1, 3)
        ]
    assert _prepared(state.instance, SECRET) == upgraded_lifecycle(
        state.upgrade, SECRET
    )
    original(state)
