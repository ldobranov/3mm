"""Exact installed authority + real root/SQLite candidate recovery, no live data."""

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
from backend.services import application_relational as transactions
from backend.services import application_relational_recovery as coordinator
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
from backend.tests.test_application_relational_admission import (
    admit,
    apply,
    commit,
    context,
    status,
)
from backend.tests.test_application_relational_preparation import (
    ROOT_ONLY,
    SECRET,
    action,
)
from backend.tests.test_application_relational_preparation import (
    checkpoint as preparation_checkpoint,
)
from backend.tests.test_application_relational_preparation import (
    issue as issue_preparation,
)
from backend.tests.test_application_relational_preparation import (
    prepared_paths,
    preserved,
)
from backend.tests.test_application_relational_preparation import run as prepare
from backend.tests.test_application_relational_preparation import (
    stopped,
)
from three_mm_application_sdk.relational_receipts import _RelationalReceiptStore
from three_mm_application_sdk.relational_wire import (
    _RelationalRecoveryTicket,
    canonical,
    recovered_lifecycle,
    sign_metadata,
)
from three_mm_runtime import application_relational_recovery as helper
from three_mm_runtime.application_relational_session import _prepared

pytestmark = [
    pytest.mark.skipif(os.name != "posix", reason="Actual POSIX Core keys/clock"),
    ROOT_ONLY,
]


@pytest.fixture
def published(prepared_paths):
    state = prepared_paths
    state.source = issue_preparation(state)
    prepare(state, state.source)
    return state


def issue(state, **changes):
    return coordinator.issue_prepared_candidate_recovery(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "source_preparation_id": state.source["preparation_id"],
            "expected_grant_record_revision": state.manager.inspect(1)[
                "grant_record_revision"
            ],
            "confirm_candidate_and_uncertain_outcomes_reviewed": True,
            "transport_secret": SECRET,
            **changes,
        },
    )


def checkpoint(state, *args, **kwargs):
    return coordinator.recovery_checkpoint(
        state.manager,
        1,
        *args,
        actor_token=state.token,
        transport_secret=SECRET,
        **kwargs,
    )


def run(state, ticket, callback=None):
    return helper.accept_prepared_relational_candidate(
        state.archive,
        ticket,
        configuration=state.configuration,
        root=state.runtime,
        key_root=state.transport_keys,
        state_root=state.helper_state,
        service_uid=1200,
        service_gid=1201,
        supervisor=state.supervisor,
        checkpoint=callback or (lambda *a, **kw: checkpoint(state, *a, **kw)),
    )


def test_confirmation_requires_current_admin_exact_grant_and_started_source(published):
    state = published
    for changes in (
        {"confirm_candidate_and_uncertain_outcomes_reviewed": False},
        {"actor_token": state.user_token},
        {"expected_grant_record_revision": identity()},
        {"source_preparation_id": identity()},
    ):
        with pytest.raises(authority.AuthorityManagementError):
            issue(state, **changes)
    untouched = issue_preparation(state)
    with pytest.raises(authority.AuthorityManagementError, match="source_unavailable"):
        issue(state, source_preparation_id=untouched["preparation_id"])


def test_recovery_fences_epoch_and_old_tickets_before_helper_and_is_one_use(published):
    state = published
    ticket = issue(state)
    assert ticket["authority_epoch"] != state.source["authority_epoch"]
    assert action(state, ticket)["state"] == "recorded"
    with Session(state.engine) as db:
        installed = db.get(Installation, 1)
        assert installed.authority_mode == "review_required" and not installed.enabled
    with pytest.raises(authority.AuthorityManagementError):
        preparation_checkpoint(
            state,
            state.source,
            "finish",
            receipt=action(state, state.source)["data"]["receipt"],
        )
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        issue(state, request_id=ticket["preparation_id"])
    assert checkpoint(state, ticket, "authorize") == {"state": "authorized_not_started"}
    checkpoint(state, ticket, "begin")
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        checkpoint(state, ticket, "begin")
    # SQL has not run, and old signed metadata is not silently changed by issue.
    assert (
        _prepared(state.instance, SECRET)["database_lineage"]
        == state.source["database_lineage"]
    )


@pytest.mark.parametrize("ack", ["delivered", "lost_before_core", "lost_after_core"])
def test_actual_candidate_acceptance_preserves_data_receipts_and_evidence(
    prepared_paths, ack
):
    state = prepared_paths
    state.source = issue_preparation(state)

    def lose(*args, **kwargs):
        if args[1] == "finish" and ack == "lost_before_core":
            raise OSError("lost before Core")
        result = preparation_checkpoint(state, *args, **kwargs)
        if args[1] == "finish" and ack == "lost_after_core":
            raise OSError("lost after Core")
        return result

    if ack == "delivered":
        prepare(state, state.source)
    else:
        with pytest.raises(Exception, match="recovery review"):
            prepare(state, state.source, lose)
        with pytest.raises(ValueError, match="recovery is pending"):
            _prepared(state.instance, SECRET)
    transaction_id, permit_sha = identity(), "c" * 64
    with sqlite3.connect(state.database) as db:
        db.execute("BEGIN IMMEDIATE")
        store = _RelationalReceiptStore(
            database_lineage=state.source["database_lineage"],
            schema_revision=state.validated.application_extension.storage.schema_revision,
            secret=SECRET,
        )
        old_receipt = store._insert(db, transaction_id, permit_sha)
    ticket = issue(state)

    def probe(*args, **kwargs):
        # Core callbacks never overlap the application DB write lock.
        with sqlite3.connect(state.database, timeout=0) as db:
            db.execute("BEGIN IMMEDIATE")
            db.rollback()
        return checkpoint(state, *args, **kwargs)

    receipt = run(state, ticket, probe)
    assert action(state, ticket)["state"] == "recovered"
    assert _prepared(state.instance, SECRET) == recovered_lifecycle(ticket, SECRET)
    assert ticket["database_lineage"] != state.source["database_lineage"]
    assert not list(state.instance.glob(".database-*.rollback"))
    assert not list(state.instance.glob(".activation-*.rollback"))
    evidence = list(state.instance.glob(".recovery-evidence-*"))
    assert len(evidence) == (1 if ack == "delivered" else 2)
    assert any((path / "previous-relational.json").is_file() for path in evidence)
    assert all((path / "database.json").is_file() for path in evidence)
    assert state.database.stat().st_uid == 1200
    preserved(state)
    with sqlite3.connect(state.database) as db:
        assert (
            json.loads(
                db.execute(
                    "SELECT payload FROM three_mm_relational_commits"
                ).fetchone()[0]
            )
            == old_receipt
        )
        store = _RelationalReceiptStore(
            database_lineage=ticket["database_lineage"],
            schema_revision=ticket["schema_revision"],
            secret=SECRET,
        )
        with pytest.raises(ValueError, match="identity changed"):
            store.lookup(db, transaction_id, permit_sha)
    assert checkpoint(state, ticket, "finish", receipt=receipt) == {
        "state": "prepared_not_started",
        "historical": True,
    }
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        run(state, ticket)
    assert state.calls == [("stop", state.instance.name)] * 2
    with Session(state.engine) as db:
        installed = db.get(Installation, 1)
        assert not installed.enabled and installed.status == "disabled"
        assert installed.authority_mode == "review_required"
    assert state.manager.inspect(1)["grant_effective"] is False
    # Even a new exact approve/apply cannot replay recovery of the same source.
    apply(state, state.native_id)
    with pytest.raises(authority.AuthorityManagementError, match="source_unavailable"):
        issue(state)


@pytest.mark.parametrize(
    "drift",
    [
        "actor",
        "native",
        "epoch",
        "configuration",
        "enabled",
        "recovery",
        "core_key",
        "boot",
        "deadline",
    ],
)
def test_recovery_checkpoints_refuse_authority_drift(published, monkeypatch, drift):
    state = published
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
    elif drift == "core_key":
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
            elif drift == "recovery":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            else:
                db.execute(
                    update(Installation).values(
                        **{
                            "epoch": {"authority_epoch": identity()},
                            "configuration": {
                                "configuration": {
                                    **state.configuration,
                                    "PRIVATE_NOTE": "changed",
                                }
                            },
                            "enabled": {"enabled": True, "status": "active"},
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
    # Key/global-generation drift intentionally makes historical seals unreadable.
    # Inspect raw stored state only to prove the failure did not silently resolve it.
    from backend.db.application_authority_grant import (
        ApplicationAuthorityAction as Action,
    )

    with Session(state.engine) as db:
        assert (
            json.loads(db.get(Action, ticket["preparation_id"]).payload)["state"]
            == "execution_unconfirmed"
        )


@pytest.mark.parametrize(
    "problem",
    [
        "lineage",
        "active",
        "key",
        "missing_db",
        "receipt",
        "unknown_marker",
        "worker_unconfirmed",
        "symlink",
    ],
)
def test_candidate_drift_never_repairs_replays_or_clears_evidence(published, problem):
    state = published
    ticket = issue(state)
    if problem == "lineage":
        path = state.instance / "relational.json"
        record = json.loads(path.read_bytes())
        path.write_bytes(
            canonical(
                sign_metadata(
                    SECRET, "lifecycle", {**record, "database_lineage": identity()}
                )
            )
        )
    elif problem == "active":
        (state.instance / "active.json").write_bytes(b"{}")
    elif problem == "key":
        (state.transport_keys / (state.instance.name + ".key")).write_bytes(b"x" * 32)
    elif problem == "missing_db":
        state.database.unlink()
    elif problem == "receipt":
        with sqlite3.connect(state.database) as db:
            db.execute(
                "INSERT INTO three_mm_relational_commits VALUES (?, ?)",
                (identity(), "{}"),
            )
    elif problem == "symlink":
        path = state.instance / "relational.json"
        path.rename(state.instance / "old-record")
        path.symlink_to(state.instance / "old-record")
    else:
        marker = state.instance / (
            ".activation-"
            + (
                identity()
                if problem == "unknown_marker"
                else state.source["preparation_id"]
            )
            + ".rollback"
        )
        marker.mkdir(mode=0o700)
        (marker / "activation.json").write_bytes(
            canonical(
                {
                    "schema_version": 1,
                    "candidate_sha256": state.validated.sha256,
                    "previous_present": True,
                    "previous_was_enabled": False,
                    "database_present": True,
                    "operation": "prepare_migrated_schema",
                    "preparation_id": state.source["preparation_id"],
                    "phase": "migrating_schema",
                }
            )
        )
    with pytest.raises((helper.RelationalRecoveryError, ValueError, OSError)):
        run(state, ticket)
    assert not list(state.instance.glob(".recovery-evidence-*"))
    assert action(state, ticket)["state"] in {"recorded", "execution_unconfirmed"}
    assert all(call[0] == "stop" for call in state.calls)


def test_lost_recovery_finish_ack_retains_fresh_candidate_without_replay(published):
    state = published
    ticket = issue(state)

    def lose(*args, **kwargs):
        result = checkpoint(state, *args, **kwargs)
        if args[1] == "finish":
            raise OSError("lost response after recovery commit")
        return result

    with pytest.raises(helper.RelationalRecoveryError, match="evidence retained"):
        run(state, ticket, lose)
    assert action(state, ticket)["state"] == "recovered"
    assert json.loads(
        (state.instance / "relational.json").read_bytes()
    ) == recovered_lifecycle(ticket, SECRET)
    assert list(state.instance.glob(".database-*.rollback"))
    with pytest.raises(ValueError, match="recovery is pending"):
        _prepared(state.instance, SECRET)
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        run(state, ticket)
    assert state.calls == [("stop", state.instance.name)] * 2
    preserved(state)


def test_closed_separate_purpose_ticket_cannot_be_used_as_preparation(published):
    state = published
    ticket = issue(state)
    for changes in (
        {"deadline_ms": True},
        {"database_path": "/foreign"},
        {"action": "prepare_existing_schema"},
    ):
        with pytest.raises(ValidationError):
            _RelationalRecoveryTicket.model_validate(
                sign_metadata(SECRET, "recovery", {**ticket, **changes})
            )
    with pytest.raises(ValueError, match="signature"):
        checkpoint(state, sign_metadata(SECRET, "preparation", ticket), "authorize")
    with pytest.raises(ValidationError):
        prepare(state, ticket)


def test_recovery_fences_old_core_completions_without_resolving_unknown_work(published):
    state = published
    state.runtime_nonce, state.database_lineage = (
        identity(),
        state.source["database_lineage"],
    )
    # Disposable installed host activity: grant is unchanged, no authority row
    # is fabricated. Existing tested Core admission creates the real journal.
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=True, status="active"))
    host = context(state)
    permit = admit(state, host=host)
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    ticket = issue(state)
    with pytest.raises(transactions.RelationalAuthorityError):
        commit(state, permit, host)
    assert status(state, permit["transaction_id"])["outcome"] == "execution_unconfirmed"
    run(state, ticket)
    with pytest.raises(transactions.RelationalAuthorityError):
        commit(state, permit, host)
    assert status(state, permit["transaction_id"])["outcome"] == "execution_unconfirmed"
    # Fresh approval after recovery does not rehabilitate the old admission.
    apply(state, state.native_id)
    with pytest.raises(transactions.RelationalAuthorityError):
        commit(state, permit, host)


@pytest.mark.parametrize("failure", ["stop", "publication", "ack_before_core"])
def test_recovery_interruption_retains_preimage_and_blocks_readiness(
    published, monkeypatch, failure
):
    state = published
    ticket = issue(state)
    old_record = (state.instance / "relational.json").read_bytes()
    if failure == "stop":

        def fail_stop(_identifier):
            raise OSError("stop unconfirmed")

        monkeypatch.setattr(state.supervisor, "stop", fail_stop)
    elif failure == "publication":
        original = helper._write_atomic

        def fail_record(path, *args):
            if path.name == "relational.json":
                raise OSError("publication interrupted")
            return original(path, *args)

        monkeypatch.setattr(helper, "_write_atomic", fail_record)

    def callback(*args, **kwargs):
        if args[1] == "finish" and failure == "ack_before_core":
            raise OSError("finish never reached Core")
        return checkpoint(state, *args, **kwargs)

    with pytest.raises(helper.RelationalRecoveryError, match="evidence retained"):
        run(state, ticket, callback)
    evidence = next(state.instance.glob(".database-*.rollback"))
    assert not list(state.instance.glob(".recovery-evidence-*"))
    with pytest.raises(ValueError, match="recovery is pending"):
        _prepared(state.instance, SECRET)
    preserved(state)
    if failure == "stop":
        assert action(state, ticket)["state"] == "recorded"
        assert not (evidence / "database.json").exists()
        assert (state.instance / "relational.json").read_bytes() == old_record
    else:
        assert action(state, ticket)["state"] == "execution_unconfirmed"
        assert (evidence / "previous-relational.json").read_bytes() == old_record
        assert (evidence / "state.sqlite3").is_file()
        with sqlite3.connect(state.database) as db:
            assert (
                json.loads(
                    db.execute(
                        "SELECT payload FROM three_mm_relational_lineage"
                    ).fetchone()[0]
                )["database_lineage"]
                == ticket["database_lineage"]
            )
