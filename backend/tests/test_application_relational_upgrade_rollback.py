"""Real non-root forward attempt/rollback followed by readonly Root acceptance."""

import json
import os
import sqlite3
from contextlib import closing

import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.session import UserSession
from backend.services import application_authority_management as authority
from backend.services import application_relational_upgrade_confirmation as published
from backend.services import application_relational_upgrade_rollback as coordinator
from backend.tests import test_application_relational_upgrade as upgrade_cases
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
from backend.tests.test_application_relational_upgrade_confirmation import (
    REFUSALS,
    image,
)
from three_mm_application_sdk.files import ApplicationFileStorage
from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeRollbackTicket,
    _RelationalUpgradeTicket,
)
from three_mm_application_sdk.relational_wire import (
    canonical,
    prepared_lifecycle,
    sign_metadata,
)
from three_mm_runtime import application_relational_upgrade as upgrade_helper
from three_mm_runtime import application_relational_upgrade_rollback as helper
from three_mm_runtime.application_relational_session import _prepared

pytestmark = [
    pytest.mark.skipif(os.name != "posix", reason="Actual POSIX authority/worker"),
    ROOT_ONLY,
]

upgradable = upgrade_cases.upgradable
original = upgrade_cases.original
upgrade_issue = upgrade_cases.issue
upgrade_checkpoint = upgrade_cases.checkpoint
upgrade = upgrade_cases.run


@pytest.fixture
def restored(upgradable, monkeypatch):
    state = upgradable
    state.failed = upgrade_issue(state)
    real = upgrade_helper.run_prepared_upgrade_migrations

    def completed_then_failed(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("Real migration committed, publication not attempted")

    with monkeypatch.context() as patch:
        patch.setattr(
            upgrade_helper, "run_prepared_upgrade_migrations", completed_then_failed
        )
        with pytest.raises(upgrade_helper.RelationalUpgradeError) as failure:
            upgrade(state, state.failed)
    state.marker = state.instance / (
        ".database-" + state.failed["preparation_id"] + ".rollback"
    )
    assert (
        json.loads((state.marker / "upgrade.json").read_bytes())["phase"]
        == "restored_not_started"
    ), repr(failure.value.__cause__)
    assert (state.marker / "rollback-proof.json").is_file()
    original(state)
    return state


def issue(state, **changes):
    return coordinator.issue_restored_upgrade_confirmation(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "source_upgrade_id": state.failed["preparation_id"],
            "expected_source_revision": action(state, state.failed)["revision"],
            "expected_grant_record_revision": state.manager.inspect(1)[
                "grant_record_revision"
            ],
            "confirm_restored_state_reviewed": True,
            "transport_secret": SECRET,
            **changes,
        },
    )


def checkpoint(state, *args, **kwargs):
    return coordinator.rollback_confirmation_checkpoint(
        state.manager,
        1,
        *args,
        actor_token=state.token,
        transport_secret=SECRET,
        **kwargs,
    )


def run(state, ticket, callback=None):
    return helper.confirm_restored_relational_upgrade(
        state.source_archive,
        state.archive,
        ticket,
        state.failed,
        configuration=state.configuration,
        root=state.runtime,
        key_root=state.transport_keys,
        state_root=state.helper_state,
        service_uid=1200,
        service_gid=1201,
        supervisor=state.supervisor,
        checkpoint=callback or (lambda *a, **kw: checkpoint(state, *a, **kw)),
    )


def test_confirmed_rollback_is_readonly_preserves_unknown_outcome_and_evidence(
    restored, monkeypatch
):
    state = restored
    before = image(state)
    old_record = (state.instance / "relational.json").read_bytes()
    proof = (state.marker / "rollback-proof.json").read_bytes()
    monkeypatch.setattr(
        upgrade_helper,
        "run_prepared_upgrade_migrations",
        lambda *a, **kw: pytest.fail("Automatic migration replay"),
    )
    ticket = issue(state)

    def unlocked(*args, **kwargs):
        with closing(sqlite3.connect(state.database, timeout=0)) as db:
            db.execute("BEGIN IMMEDIATE")
            db.rollback()
        return checkpoint(state, *args, **kwargs)

    result = run(state, ticket, unlocked)
    assert result["outcome"] == "restored_not_started"
    assert action(state, ticket)["state"] == "confirmed"
    assert action(state, state.failed)["state"] == "execution_unconfirmed"
    assert image(state) == before
    assert (state.instance / "relational.json").read_bytes() == old_record
    assert _prepared(state.instance, SECRET) == prepared_lifecycle(state.source, SECRET)
    archive = state.instance / (
        ".upgrade-rollback-evidence-" + state.failed["preparation_id"]
    )
    assert (archive / "rollback-proof.json").read_bytes() == proof
    assert (archive / "candidate-state.sqlite3").is_file()
    assert not list(state.instance.glob(".database-*.rollback"))
    original(state)
    assert not state.manager.inspect(1)["grant_effective"]
    with Session(state.engine) as db:
        value = db.get(Installation, 1)
        assert (
            value.status == "disabled"
            and not value.enabled
            and value.authority_mode == "review_required"
        )
    assert all(call[0] == "stop" for call in state.calls)
    assert checkpoint(state, ticket, "finish", receipt=result) == {
        "state": "restored_not_started",
        "historical": True,
    }
    with pytest.raises(REFUSALS):
        run(state, ticket)
    with pytest.raises(REFUSALS):
        upgrade_checkpoint(state, state.failed, "check")


def test_new_forward_attempt_requires_both_confirmed_rollback_and_fresh_consent(
    restored,
):
    state = restored
    state.source_revision = action(state, state.source)["revision"]
    ticket = issue(state)
    proof = state.manager.inspect(1)["native_reviews"][0]
    # A current grant alone cannot consume the still-uncertain source.
    apply(state, proof["native_review_id"])
    with pytest.raises(
        authority.AuthorityManagementError, match="rollback_confirmation_pending"
    ):
        upgrade_issue(state)
    # That grant also changes the already-issued confirmation binding; no fallback.
    with pytest.raises(REFUSALS):
        checkpoint(state, ticket, "authorize")


def test_after_confirmed_rollback_a_new_reviewed_forward_attempt_actually_works(
    restored,
):
    state = restored
    run(state, issue(state))
    state.source_revision = action(state, state.source)["revision"]
    with pytest.raises(REFUSALS):
        upgrade_issue(state)
    proof = state.manager.inspect(1)["native_reviews"][0]
    apply(state, proof["native_review_id"])
    fresh = upgrade_issue(state)
    assert fresh["preparation_id"] != state.failed["preparation_id"]
    assert (
        action(state, fresh)["data"]["result"]["previous_upgrade_id"]
        == state.failed["preparation_id"]
    )
    upgrade(state, fresh)
    with closing(sqlite3.connect(state.database)) as db:
        assert db.execute("SELECT value,migrated FROM business").fetchall() == [
            ("preserved", 1)
        ]
    assert action(state, state.failed)["state"] == "execution_unconfirmed"
    original(state)


@pytest.mark.parametrize(
    "changes",
    [
        {"confirm_restored_state_reviewed": False},
        {"actor_token": "invalid"},
        {"expected_source_revision": "1" * 32},
        {"expected_grant_record_revision": "2" * 32},
        {"source_upgrade_id": "3" * 32},
    ],
)
def test_confirmation_requires_current_admin_and_exact_human_review(restored, changes):
    with pytest.raises(REFUSALS):
        issue(restored, **changes)


@pytest.mark.parametrize(
    "problem",
    [
        "business",
        "proof",
        "missing_proof",
        "preimage",
        "files",
        "record",
        "phase",
        "key",
        "unknown_marker",
        "stop",
    ],
)
def test_changed_or_partial_restore_is_never_accepted_or_repaired(
    restored, monkeypatch, problem
):
    state = restored
    ticket = issue(state)
    if problem == "business":
        with closing(sqlite3.connect(state.database)) as db:
            db.execute("UPDATE business SET value='changed after rollback'")
            db.commit()
    elif problem == "proof":
        (state.marker / "rollback-proof.json").write_bytes(b"{}")
    elif problem == "missing_proof":
        (state.marker / "rollback-proof.json").rename(
            state.marker / "missing-proof-evidence"
        )
    elif problem == "preimage":
        with (state.marker / "state.sqlite3").open("ab") as stream:
            stream.write(b"corrupt")
    elif problem == "files":
        storage = ApplicationFileStorage(state.data)
        storage.put(
            "example_txt", b"changed", expected_sha256=storage.get("example_txt").sha256
        )
    elif problem == "record":
        (state.instance / "relational.json").write_bytes(b"{}")
    elif problem == "phase":
        path = state.marker / "upgrade.json"
        path.write_bytes(
            canonical({**json.loads(path.read_bytes()), "phase": "restoring"})
        )
    elif problem == "key":
        (state.transport_keys / (state.instance.name + ".key")).write_bytes(b"x" * 32)
    elif problem == "unknown_marker":
        (state.instance / (".database-" + identity() + ".rollback")).mkdir(mode=0o700)
    else:
        monkeypatch.setattr(
            state.supervisor,
            "stop",
            lambda *a: (_ for _ in ()).throw(OSError("Unconfirmed stop")),
        )
    before = image(state)
    with pytest.raises((RuntimeError, ValueError, OSError)):
        run(state, ticket)
    assert image(state) == before
    assert state.marker.is_dir()
    assert not list(state.instance.glob(".upgrade-rollback-evidence-*"))


@pytest.mark.parametrize("ack", ["before", "after"])
def test_lost_confirmation_ack_needs_new_human_action_without_restore_replay(
    restored, ack
):
    state = restored
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
    fresh = issue(state)
    with pytest.raises(REFUSALS):
        checkpoint(state, ticket, "check")
    run(state, fresh)
    assert image(state) == before
    assert action(state, ticket)["data"]["superseded_by"] == fresh["preparation_id"]
    assert action(state, state.failed)["state"] == "execution_unconfirmed"


def test_partial_archive_preserves_both_evidence_sets_until_new_confirmation(
    restored, monkeypatch
):
    state = restored
    sync = helper._sync_directory
    failed = []

    def once(path):
        if not failed:
            failed.append(True)
            raise OSError("Archive interrupted")
        sync(path)

    ticket = issue(state)
    with monkeypatch.context() as patch:
        patch.setattr(helper, "_sync_directory", once)
        with pytest.raises(upgrade_helper.RelationalUpgradeError):
            run(state, ticket)
    run(state, issue(state))
    assert not list(state.instance.glob(".database-*.rollback"))
    assert len(list(state.instance.glob(".upgrade-rollback-evidence-*"))) == 3


@pytest.mark.parametrize(
    "drift", ["actor", "native", "grant", "generation", "deadline"]
)
def test_checkpoints_refuse_authority_drift(restored, monkeypatch, drift):
    state = restored
    ticket = issue(state)
    checkpoint(state, ticket, "begin")
    with Session(state.engine) as db:
        before = db.get(Action, ticket["preparation_id"]).payload
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
    elif drift == "deadline":
        monkeypatch.setattr(
            authority, "_clock", lambda: (ticket["boot_id"], ticket["deadline_ms"])
        )
    else:
        with state.engine.begin() as db:
            db.execute(
                update(UserSession).values(is_active=False)
                if drift == "actor"
                else update(CoreAuthorityGuard).values(generation=identity())
            )
    with pytest.raises(REFUSALS):
        checkpoint(state, ticket, "check")
    with Session(state.engine) as db:
        assert db.get(Action, ticket["preparation_id"]).payload == before


def test_wrong_published_confirmation_can_be_superseded_by_exact_rollback_review(
    restored,
):
    state = restored
    old = published.issue_published_upgrade_confirmation(
        state.manager,
        1,
        actor_token=state.token,
        request_id=identity(),
        source_upgrade_id=state.failed["preparation_id"],
        expected_source_revision=action(state, state.failed)["revision"],
        expected_grant_record_revision=state.manager.inspect(1)[
            "grant_record_revision"
        ],
        confirm_published_upgrade_reviewed=True,
        transport_secret=SECRET,
    )
    ticket = issue(state)
    run(state, ticket)
    assert action(state, old)["data"]["superseded_by"] == ticket["preparation_id"]
    with pytest.raises(REFUSALS):
        published.upgrade_confirmation_checkpoint(
            state.manager,
            1,
            old,
            "authorize",
            actor_token=state.token,
            transport_secret=SECRET,
        )


def test_rollback_ticket_cannot_run_an_upgrade_and_boot_evidence_is_untouched(restored):
    state = restored
    ticket = issue(state)
    with pytest.raises(ValidationError):
        _RelationalUpgradeTicket.model_validate(ticket)
    with pytest.raises(ValueError, match="signature"):
        checkpoint(
            state,
            sign_metadata(SECRET, "database_upgrade_confirmation", ticket),
            "authorize",
        )
    path = state.instance / "boot-required.json"
    path.symlink_to(state.instance / "missing-boot-policy")
    calls = list(state.calls)
    with pytest.raises(ValueError, match="Boot policy"):
        run(state, ticket)
    assert path.is_symlink() and state.calls == calls
