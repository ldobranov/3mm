"""Actual installed authority + root readonly reconciliation, disposable data."""

import json
import os
import sqlite3

import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.session import UserSession
from backend.services import application_authority_management as authority
from backend.services import application_relational_recovery_confirmation as coordinator
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_policy_reviews import PolicyReviewStoreError
from backend.tests.test_application_authority_management import (
    identity,
)
from backend.tests.test_application_authority_management import (
    installed as managed_installed,
)
from backend.tests.test_application_authority_management import (
    native,
)
from backend.tests.test_application_authority_subjects import (
    installed as source_subject,
)
from backend.tests.test_application_authority_subjects import (
    source_installed,
)
from backend.tests.test_application_relational_preparation import (
    ROOT_ONLY,
    SECRET,
    action,
    prepared_paths,
    preserved,
    stopped,
)
from backend.tests.test_application_relational_recovery import (
    checkpoint as recovery_checkpoint,
)
from backend.tests.test_application_relational_recovery import issue as issue_recovery
from backend.tests.test_application_relational_recovery import (
    published,
)
from backend.tests.test_application_relational_recovery import run as recover
from three_mm_application_sdk.relational_wire import (
    _RelationalRecoveryConfirmationTicket,
    canonical,
    recovered_lifecycle,
    sign_metadata,
)
from three_mm_runtime import application_relational_recovery as recovery_helper
from three_mm_runtime import application_relational_recovery_confirmation as helper
from three_mm_runtime.application_relational_session import _prepared

pytestmark = [
    pytest.mark.skipif(os.name != "posix", reason="Actual POSIX Core keys/clock"),
    ROOT_ONLY,
]


def issue(state, **changes):
    return coordinator.issue_published_recovery_confirmation(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "source_recovery_id": state.recovery["preparation_id"],
            "expected_grant_record_revision": state.manager.inspect(1)[
                "grant_record_revision"
            ],
            "confirm_published_recovery_reviewed": True,
            "transport_secret": SECRET,
            **changes,
        },
    )


def checkpoint(state, *args, **kwargs):
    return coordinator.confirmation_checkpoint(
        state.manager,
        1,
        *args,
        actor_token=state.token,
        transport_secret=SECRET,
        **kwargs,
    )


def run(state, ticket, callback=None):
    return helper.confirm_published_relational_recovery(
        state.archive,
        ticket,
        state.recovery,
        configuration=state.configuration,
        root=state.runtime,
        key_root=state.transport_keys,
        state_root=state.helper_state,
        service_uid=1200,
        service_gid=1201,
        supervisor=state.supervisor,
        checkpoint=callback or (lambda *a, **kw: checkpoint(state, *a, **kw)),
    )


def interrupt(state, ack):
    state.recovery = issue_recovery(state)

    def lose(*args, **kwargs):
        if args[1] == "finish" and ack == "before":
            raise OSError("lost request before Core")
        result = recovery_checkpoint(state, *args, **kwargs)
        if args[1] == "finish":
            raise OSError("lost response after Core")
        return result

    with pytest.raises(recovery_helper.RelationalRecoveryError):
        recover(state, state.recovery, lose)
    return state


@pytest.fixture
def interrupted(published):
    return interrupt(published, "after")


@pytest.mark.parametrize("ack", ["before", "after"])
def test_readonly_confirmation_preserves_lineage_data_and_evidence(
    published, monkeypatch, ack
):
    state = interrupt(published, ack)
    old_state = action(state, state.recovery)["state"]
    marker = next(state.instance.glob(".database-*.rollback"))
    old_snapshot = (marker / "state.sqlite3").read_bytes()
    old_db, old_record = (
        state.database.read_bytes(),
        (state.instance / "relational.json").read_bytes(),
    )
    monkeypatch.setattr(
        recovery_helper,
        "_recover_receipt_lineage",
        lambda *a, **kw: pytest.fail("Confirmation replayed SQL recovery"),
    )
    ticket = issue(state)
    assert ticket["authority_epoch"] != state.recovery["authority_epoch"]
    assert ticket["database_lineage"] == state.recovery["database_lineage"]

    def probe(*args, **kwargs):
        with sqlite3.connect(state.database, timeout=0) as db:
            db.execute("BEGIN IMMEDIATE")
            db.rollback()
        return checkpoint(state, *args, **kwargs)

    receipt = run(state, ticket, probe)
    assert action(state, ticket)["state"] == "confirmed"
    source = action(state, state.recovery)
    assert source["state"] == "recovered"
    if old_state == "execution_unconfirmed":
        assert source["data"]["confirmation_previous_state"] == old_state
    assert state.database.read_bytes() == old_db
    assert (state.instance / "relational.json").read_bytes() == old_record
    assert _prepared(state.instance, SECRET) == recovered_lifecycle(
        state.recovery, SECRET
    )
    archived = state.instance / (".recovery-evidence-" + marker.name[1:])
    assert (archived / "state.sqlite3").read_bytes() == old_snapshot
    assert not any(
        os.path.lexists(archived / ("state.sqlite3" + suffix))
        for suffix in ("-wal", "-shm", "-journal")
    )
    assert len(list(state.instance.glob(".recovery-evidence-*"))) == 2
    assert not list(state.instance.glob(".database-*.rollback"))
    preserved(state)
    assert checkpoint(state, ticket, "finish", receipt=receipt) == {
        "state": "prepared_not_started",
        "historical": True,
    }
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        run(state, ticket)
    with pytest.raises(authority.AuthorityManagementError):
        recovery_checkpoint(
            state, state.recovery, "finish", receipt=source["data"]["receipt"]
        )
    assert state.calls == [("stop", state.instance.name)] * 3
    with Session(state.engine) as db:
        installed = db.get(Installation, 1)
        assert (
            installed.status == "disabled"
            and not installed.enabled
            and installed.authority_mode == "review_required"
        )


def test_confirmation_requires_explicit_current_admin_and_exact_source(interrupted):
    state = interrupted
    for changes in (
        {"confirm_published_recovery_reviewed": False},
        {"actor_token": state.user_token},
        {"expected_grant_record_revision": identity()},
        {"source_recovery_id": identity()},
    ):
        with pytest.raises(authority.AuthorityManagementError):
            issue(state, **changes)
    ticket = issue(state)
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        issue(state, request_id=ticket["preparation_id"])
    checkpoint(state, ticket, "begin")
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        checkpoint(state, ticket, "begin")
    assert action(state, state.recovery)["state"] == "recovered"


@pytest.mark.parametrize(
    "drift",
    [
        "actor",
        "native",
        "epoch",
        "configuration",
        "enabled",
        "generation",
        "key",
        "boot",
        "deadline",
    ],
)
def test_each_confirmation_checkpoint_refuses_drift(interrupted, monkeypatch, drift):
    state = interrupted
    ticket = issue(state)
    checkpoint(state, ticket, "begin")
    if drift == "native":
        proof = state.manager.inspect(1)["native_reviews"][0]
        state.manager.revoke_native_review(
            1,
            actor_token=state.token,
            request_id=identity(),
            native_review_id=proof["native_review_id"],
            expected_revision=proof["revision"],
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
                (
                    ticket["deadline_ms"]
                    if drift == "deadline"
                    else ticket["issued_at_ms"]
                ),
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
    with pytest.raises(
        (
            authority.AuthorityManagementError,
            AuthorityReviewKeyError,
            PolicyReviewStoreError,
        )
    ):
        checkpoint(state, ticket, "check")
    assert list(state.instance.glob(".database-*.rollback"))


@pytest.mark.parametrize(
    "problem",
    [
        "record",
        "lineage",
        "receipt",
        "preimage",
        "files",
        "wheel",
        "unknown_marker",
        "phase",
        "key",
        "symlink",
        "stop",
    ],
)
def test_invalid_or_incomplete_recovery_is_never_repaired_or_archived(
    interrupted, monkeypatch, problem
):
    state = interrupted
    ticket = issue(state)
    marker = next(state.instance.glob(".database-*.rollback"))
    if problem == "record":
        (state.instance / "relational.json").write_bytes(b"{}")
    elif problem == "lineage":
        with sqlite3.connect(state.database) as db:
            db.execute("UPDATE three_mm_relational_lineage SET payload='{}'")
    elif problem == "receipt":
        with sqlite3.connect(state.database) as db:
            db.execute(
                "INSERT INTO three_mm_relational_commits VALUES (?, '{}')",
                (identity(),),
            )
    elif problem == "preimage":
        with (marker / "state.sqlite3").open("ab") as stream:
            stream.write(b"corrupt")
    elif problem == "files":
        path = next(
            path for path in (marker / "sdk-files").iterdir() if path.name != ".lock"
        )
        path.write_bytes(b"corrupt")
    elif problem == "wheel":
        (
            state.instance / "releases" / ticket["package_sha256"] / "service.whl"
        ).write_bytes(b"corrupt")
    elif problem == "unknown_marker":
        (state.instance / (".database-" + identity() + ".rollback")).mkdir(mode=0o700)
    elif problem == "phase":
        path = marker / "recovery.json"
        path.write_bytes(
            canonical({**json.loads(path.read_bytes()), "phase": "publishing"})
        )
    elif problem == "key":
        (state.transport_keys / (state.instance.name + ".key")).write_bytes(b"x" * 32)
    elif problem == "symlink":
        path = state.instance / "relational.json"
        path.rename(state.instance / "old-record")
        path.symlink_to(state.instance / "old-record")
    else:
        monkeypatch.setattr(
            state.supervisor,
            "stop",
            lambda *a: (_ for _ in ()).throw(OSError("stop unconfirmed")),
        )
    with pytest.raises((recovery_helper.RelationalRecoveryError, ValueError, OSError)):
        run(state, ticket)
    assert list(state.instance.glob(".database-*.rollback"))
    assert not list(state.instance.glob(".recovery-evidence-*"))
    assert action(state, ticket)["state"] in {"recorded", "execution_unconfirmed"}
    with pytest.raises(ValueError, match="pending"):
        _prepared(state.instance, SECRET)


@pytest.mark.parametrize("ack", ["before", "after"])
def test_confirmation_lost_ack_requires_new_human_action_without_sql_replay(
    interrupted, ack
):
    state = interrupted
    ticket = issue(state)

    def lose(*args, **kwargs):
        if args[1] == "finish" and ack == "before":
            raise OSError("lost request")
        result = checkpoint(state, *args, **kwargs)
        if args[1] == "finish":
            raise OSError("lost response")
        return result

    with pytest.raises(recovery_helper.RelationalRecoveryError):
        run(state, ticket, lose)
    old_db = state.database.read_bytes()
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        run(state, ticket)
    fresh = issue(state)
    assert fresh["preparation_id"] != ticket["preparation_id"]
    assert fresh["authority_epoch"] != ticket["authority_epoch"]
    with pytest.raises(authority.AuthorityManagementError):
        checkpoint(state, ticket, "check")
    run(state, fresh)
    assert state.database.read_bytes() == old_db
    assert action(state, ticket)["data"]["superseded_by"] == fresh["preparation_id"]
    assert len(list(state.instance.glob(".recovery-evidence-*"))) == 3
    assert not list(state.instance.glob(".database-*.rollback"))
    preserved(state)


def test_confirmation_ticket_is_closed_separate_purpose_and_not_recovery_authority(
    interrupted,
):
    state = interrupted
    ticket = issue(state)
    for changes in (
        {"database_path": "/foreign"},
        {"issued_at_ms": True},
        {"action": "accept_prepared_candidate"},
    ):
        with pytest.raises(ValidationError):
            _RelationalRecoveryConfirmationTicket.model_validate(
                sign_metadata(SECRET, "recovery_confirmation", {**ticket, **changes})
            )
    with pytest.raises(ValueError, match="signature"):
        checkpoint(state, sign_metadata(SECRET, "recovery", ticket), "authorize")
    with pytest.raises(ValidationError):
        recover(state, ticket)


def test_successful_uninterrupted_recovery_does_not_need_reconciliation(published):
    state = published
    state.recovery = issue_recovery(state)
    recover(state, state.recovery)
    before = state.database.read_bytes()
    ticket = issue(state)
    with pytest.raises(ValueError, match="No interrupted"):
        run(state, ticket)
    assert state.database.read_bytes() == before
    assert not list(state.instance.glob(".database-*.rollback"))


@pytest.mark.parametrize("ack", ["before", "after"])
def test_confirmation_preserves_original_pending_preparation_checkpoint(
    prepared_paths, ack
):
    from backend.tests.test_application_relational_preparation import (
        checkpoint as prepare_checkpoint,
    )
    from backend.tests.test_application_relational_preparation import (
        issue as prepare_issue,
    )
    from backend.tests.test_application_relational_preparation import run as prepare

    state = prepared_paths
    state.source = prepare_issue(state)

    def lose(*args, **kwargs):
        if args[1] == "finish" and ack == "before":
            raise OSError("preparation request lost")
        result = prepare_checkpoint(state, *args, **kwargs)
        if args[1] == "finish":
            raise OSError("preparation response lost")
        return result

    with pytest.raises(Exception, match="recovery review"):
        prepare(state, state.source, lose)
    state = interrupt(state, "after")
    assert list(state.instance.glob(".activation-*.rollback"))
    run(state, issue(state))
    assert not list(state.instance.glob(".activation-*.rollback"))
    assert len(list(state.instance.glob(".recovery-evidence-*"))) == 3
    preserved(state)


def test_partial_archive_requires_new_human_confirmation_and_keeps_all_evidence(
    interrupted, monkeypatch
):
    state = interrupted
    ticket = issue(state)
    original = helper._sync_directory
    failed = False

    def fail_once(path):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("archive synchronization interrupted")
        return original(path)

    with monkeypatch.context() as patch:
        patch.setattr(helper, "_sync_directory", fail_once)
        with pytest.raises(recovery_helper.RelationalRecoveryError):
            run(state, ticket)
    assert action(state, ticket)["state"] == "confirmed"
    assert list(state.instance.glob(".database-*.rollback"))
    assert list(state.instance.glob(".recovery-evidence-*"))
    run(state, issue(state))
    assert len(list(state.instance.glob(".recovery-evidence-*"))) == 3
    assert not list(state.instance.glob(".database-*.rollback"))
    preserved(state)


def test_expired_source_is_evidence_not_renewed_sql_authority(interrupted, monkeypatch):
    from three_mm_runtime import (
        application_relational_preparation as preparation_helper,
    )

    state = interrupted
    future = state.recovery["deadline_ms"] + 1
    clock = lambda: (state.recovery["boot_id"], future)
    monkeypatch.setattr(authority, "_clock", clock)
    monkeypatch.setattr(preparation_helper, "_clock", clock)
    monkeypatch.setattr(helper, "_clock", clock)
    ticket = issue(state)
    assert ticket["issued_at_ms"] > state.recovery["deadline_ms"]
    before = state.database.read_bytes()
    run(state, ticket)
    assert state.database.read_bytes() == before


def test_confirmation_receipt_has_exact_identity_and_separate_purpose(interrupted):
    state = interrupted
    ticket = issue(state)
    checkpoint(state, ticket, "begin")
    body = {
        "version": 1,
        "preparation_id": ticket["preparation_id"],
        "lifecycle_sha256": ticket["published_lifecycle_sha256"],
        "outcome": "prepared_not_started",
    }
    for receipt in (
        sign_metadata(SECRET, "recovery_result", body),
        sign_metadata(
            SECRET,
            "recovery_confirmation_result",
            {**body, "lifecycle_sha256": "0" * 64},
        ),
    ):
        with pytest.raises((ValueError, authority.AuthorityManagementError)):
            checkpoint(state, ticket, "finish", receipt=receipt)
    assert action(state, ticket)["state"] == "execution_unconfirmed"
    assert list(state.instance.glob(".database-*.rollback"))
