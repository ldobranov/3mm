"""Real private Core consent/non-root forward upgrade on disposable paths."""

import hashlib
import json
import os
import sqlite3

import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.session import UserSession
from backend.services import application_authority_management as authority
from backend.services import application_relational as transactions
from backend.services import application_relational_activation as activation
from backend.services import application_relational_upgrade as coordinator
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_policy_reviews import PolicyReviewStoreError
from backend.tests.test_application_relational_admission import (
    admit,
    commit,
    context,
    status,
)
from backend.tests.test_application_relational_migrations import candidate, read, script
from backend.tests.test_application_relational_preparation import (
    ROOT_ONLY,
    SECRET,
    action,
    apply,
    identity,
)
from backend.tests.test_application_relational_preparation import (
    issue as prepare_ticket,
)
from backend.tests.test_application_relational_preparation import (
    managed_installed,
    prepared_paths,
)
from backend.tests.test_application_relational_preparation import run as prepare
from backend.tests.test_application_relational_preparation import (
    source_installed,
    source_subject,
    stopped,
)
from three_mm_application_sdk.files import ApplicationFileStorage
from three_mm_application_sdk.relational_receipts import _RelationalReceiptStore
from three_mm_application_sdk.relational_upgrade_receipts import (
    validate_upgrade_history,
)
from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeTicket,
    upgraded_lifecycle,
)
from three_mm_application_sdk.relational_wire import (
    _RelationalMigrationPreparationTicket,
    canonical,
    sign_metadata,
)
from three_mm_runtime import application_relational_upgrade as helper
from three_mm_runtime.application_relational_migrations import (
    MigrationWorkerUnconfirmed,
)
from three_mm_runtime.application_relational_session import _prepared

pytestmark = [
    pytest.mark.skipif(os.name != "posix", reason="Actual POSIX authority/worker"),
    ROOT_ONLY,
]


@pytest.fixture
def upgradable(prepared_paths, tmp_path):
    state = prepared_paths
    for directory in (tmp_path, tmp_path.parent, tmp_path.parent.parent):
        directory.chmod(directory.stat().st_mode | 0o111)
    for directory in (state.runtime, state.instance, state.instance / "releases"):
        os.chown(directory, 0, 1201)
    state.source = prepare_ticket(state)
    prepare(state, state.source)
    state.source_archive = state.archive
    state.source_revision = action(state, state.source)["revision"]
    state.previous_active = (state.instance / "active.json").read_bytes()
    state.previous_record = (state.instance / "relational.json").read_bytes()
    state.old_transaction, state.old_permit = identity(), "b" * 64
    with sqlite3.connect(state.database) as db:
        db.execute("BEGIN IMMEDIATE")
        state.old_receipt = _RelationalReceiptStore(
            database_lineage=state.source["database_lineage"],
            schema_revision="0001",
            secret=SECRET,
        )._insert(db, state.old_transaction, state.old_permit)
    # Test-only installed candidate binding; staging/public adoption stays gated.
    # Real native review + normal review/approve/apply supplies target consent.
    candidate(state, script())
    return state


def issue(state, **changes):
    return coordinator.issue_prepared_database_upgrade(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "source_preparation_id": state.source["preparation_id"],
            "expected_source_revision": state.source_revision,
            "expected_grant_record_revision": state.manager.inspect(1)[
                "grant_record_revision"
            ],
            "confirm_owned_forward_upgrade": True,
            "transport_secret": SECRET,
            **changes,
        },
    )


def checkpoint(state, *args, **kwargs):
    return coordinator.upgrade_checkpoint(
        state.manager,
        1,
        *args,
        actor_token=state.token,
        transport_secret=SECRET,
        **kwargs,
    )


def run(state, ticket, callback=None):
    return helper.upgrade_prepared_relational_database(
        state.source_archive,
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


def original(state):
    assert read(state, "SELECT value FROM business") == [("preserved",)]
    assert read(state, "SELECT COUNT(*) FROM three_mm_outbox") == [(1,)]
    assert (
        ApplicationFileStorage(state.data, mode="read").get("example_txt").content
        == b"preserved"
    )
    assert (
        state.transport_keys / (state.instance.name + ".key")
    ).read_bytes() == SECRET
    assert (
        json.loads(read(state, "SELECT payload FROM three_mm_relational_commits")[0][0])
        == state.old_receipt
    )


def test_real_upgrade_preserves_business_history_and_never_starts_or_regrants(
    upgradable,
):
    state = upgradable
    ticket = issue(state)
    assert ticket["authority_epoch"] != state.source["authority_epoch"]
    assert ticket["database_lineage"] != state.source["database_lineage"]
    with pytest.raises(ValidationError):
        _RelationalMigrationPreparationTicket.model_validate(ticket)

    def unlocked(*args, **kwargs):
        with sqlite3.connect(state.database, timeout=0) as db:
            db.execute("BEGIN IMMEDIATE")
            db.rollback()
        return checkpoint(state, *args, **kwargs)

    result = run(state, ticket, unlocked)
    assert result["outcome"] == "upgraded_not_started"
    assert action(state, ticket)["state"] == "upgraded"
    assert _prepared(state.instance, SECRET) == upgraded_lifecycle(ticket, SECRET)
    assert read(state, "SELECT value,migrated FROM business") == [("preserved", 1)]
    assert read(
        state, "SELECT revision FROM three_mm_schema_migrations ORDER BY rowid"
    ) == [("0001",), ("0002",)]
    original(state)
    assert not list(state.instance.glob(".database-*.rollback"))
    evidence = state.instance / (".upgrade-evidence-" + ticket["preparation_id"])
    assert (evidence / "previous-relational.json").read_bytes() == state.previous_record
    assert (evidence / "previous-active.json").read_bytes() == state.previous_active
    with sqlite3.connect(state.database) as db:
        validate_upgrade_history(db, schema_revision="0002", secret=SECRET)
        with pytest.raises(ValueError, match="identity changed"):
            _RelationalReceiptStore(
                database_lineage=ticket["database_lineage"],
                schema_revision="0002",
                secret=SECRET,
            ).lookup(db, state.old_transaction, state.old_permit)
    assert checkpoint(state, ticket, "finish", receipt=result) == {
        "state": "upgraded_not_started",
        "historical": True,
    }
    assert all(call[0] == "stop" for call in state.calls)
    with Session(state.engine) as db:
        installed = db.get(Installation, 1)
        assert (
            not installed.enabled
            and installed.status == "disabled"
            and installed.authority_mode == "review_required"
        )
    assert state.manager.inspect(1)["grant_effective"] is False
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        checkpoint(state, ticket, "authorize")
    with pytest.raises(ValueError, match="source changed"):
        run(state, ticket)


@pytest.mark.parametrize(
    "changes",
    [
        {"confirm_owned_forward_upgrade": False},
        {"actor_token": "invalid"},
        {"expected_source_revision": "1" * 32},
        {"expected_grant_record_revision": "2" * 32},
        {"source_preparation_id": "3" * 32},
    ],
)
def test_issue_requires_fresh_human_exact_source_and_target_consent(
    upgradable, changes
):
    with pytest.raises((authority.AuthorityManagementError, ValueError)):
        issue(upgradable, **changes)
    assert (
        upgradable.instance / "relational.json"
    ).read_bytes() == upgradable.previous_record
    assert not list(upgradable.instance.glob(".database-*.rollback"))


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM three_mm_relational_commits",
        "UPDATE three_mm_relational_lineage SET payload='{}'",
        "DROP TABLE three_mm_relational_lineage",
        "ALTER TABLE business RENAME TO three_mm_escape",
        "ATTACH ':memory:' AS escape",
    ],
)
def test_migration_cannot_change_receipt_evidence_or_escape_sql_fence(upgradable, sql):
    state = upgradable
    candidate(state, script("db.execute(" + repr(sql) + ")"))
    ticket = issue(state)
    with pytest.raises(helper.RelationalUpgradeError, match="evidence retained"):
        run(state, ticket)
    original(state)
    assert read(state, "SELECT revision FROM three_mm_schema_migrations") == [("0001",)]
    assert (state.instance / "relational.json").read_bytes() == state.previous_record
    assert action(state, ticket)["state"] == "execution_unconfirmed"
    marker = next(state.instance.glob(".database-*.rollback"))
    assert (
        json.loads((marker / "upgrade.json").read_bytes())["phase"]
        == "restored_not_started"
    )


@pytest.mark.parametrize("ack", ["before_core", "after_core"])
def test_lost_finish_ack_preserves_candidate_and_preimage_without_replay(
    upgradable, ack
):
    state = upgradable
    ticket = issue(state)

    def lost(*args, **kwargs):
        if args[1] == "finish" and ack == "before_core":
            raise OSError("lost before Core")
        result = checkpoint(state, *args, **kwargs)
        if args[1] == "finish":
            raise OSError("lost after Core")
        return result

    with pytest.raises(helper.RelationalUpgradeError, match="evidence retained"):
        run(state, ticket, lost)
    assert read(state, "SELECT value,migrated FROM business") == [("preserved", 1)]
    original(state)
    assert action(state, ticket)["state"] == (
        "upgraded" if ack == "after_core" else "execution_unconfirmed"
    )
    marker = next(state.instance.glob(".database-*.rollback"))
    assert (marker / "previous-relational.json").read_bytes() == state.previous_record
    with pytest.raises(ValueError, match="recovery is pending"):
        _prepared(state.instance, SECRET)
    with pytest.raises(Exception, match="unfinished rollback"):
        run(state, ticket)


@pytest.mark.parametrize("drift", ["revoke", "actor", "deadline", "boot", "native"])
def test_checkpoint_rechecks_current_authority_after_issue(
    upgradable, monkeypatch, drift
):
    state = upgradable
    ticket = issue(state)
    if drift == "revoke":
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=state.manager.inspect(1)["grant_record_revision"],
        )
    elif drift == "actor":
        with state.engine.begin() as db:
            db.execute(update(UserSession).values(is_active=False))
    elif drift == "native":
        proof = state.manager.inspect(1)["native_reviews"][0]
        state.manager.revoke_native_review(
            1,
            actor_token=state.token,
            request_id=identity(),
            native_review_id=proof["native_review_id"],
            expected_revision=proof["revision"],
        )
    else:
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
    with pytest.raises(
        (
            authority.AuthorityManagementError,
            AuthorityReviewKeyError,
            PolicyReviewStoreError,
        )
    ):
        checkpoint(state, ticket, "authorize")
    assert action(state, ticket)["state"] == "recorded"
    assert (state.instance / "relational.json").read_bytes() == state.previous_record


def test_unconfirmed_worker_stop_never_rolls_back_over_possible_live_writes(
    upgradable, monkeypatch
):
    state = upgradable
    ticket = issue(state)

    def uncertain(*args, **kwargs):
        with sqlite3.connect(state.database) as db:
            db.execute("UPDATE business SET value='possibly live'")
        raise MigrationWorkerUnconfirmed("stop uncertain")

    monkeypatch.setattr(helper, "run_prepared_upgrade_migrations", uncertain)
    with pytest.raises(helper.RelationalUpgradeError, match="evidence retained"):
        run(state, ticket)
    assert read(state, "SELECT value FROM business") == [("possibly live",)]
    marker = next(state.instance.glob(".database-*.rollback"))
    assert not (marker / "candidate-state.sqlite3").exists()
    assert (marker / "state.sqlite3").is_file()


def test_boot_gate_refusal_precedes_core_checkpoint_or_service_action(upgradable):
    state = upgradable
    ticket = issue(state)
    marker = state.instance / "boot-required.json"
    marker.symlink_to(state.instance / "missing-boot-state")
    calls = list(state.calls)
    with pytest.raises(ValueError, match="Boot policy requires explicit"):
        run(
            state,
            ticket,
            lambda *a, **kw: pytest.fail("Core called before boot reconciliation"),
        )
    assert marker.is_symlink() and state.calls == calls
    assert not list(state.instance.glob(".database-*.rollback"))
    original(state)


def test_completed_upgrade_requires_new_grant_and_explicit_separate_start(upgradable):
    state = upgradable
    ticket = issue(state)
    run(state, ticket)
    with pytest.raises(authority.AuthorityManagementError):
        activation.issue_prepared_activation(
            state.manager,
            1,
            actor_token=state.token,
            request_id=identity(),
            source_preparation_id=ticket["preparation_id"],
            expected_grant_record_revision=state.manager.inspect(1)[
                "grant_record_revision"
            ],
            confirm_start_prepared_service=True,
            transport_secret=SECRET,
            service_uid=1200,
            service_gid=1201,
            coordinator_uid=1202,
        )
    # The normal separate review/approve/apply, not upgrade, authorizes start.
    proof = state.manager.inspect(1)["native_reviews"][0]
    apply(state, proof["native_review_id"])
    start = activation.issue_prepared_activation(
        state.manager,
        1,
        actor_token=state.token,
        request_id=identity(),
        source_preparation_id=ticket["preparation_id"],
        expected_grant_record_revision=state.manager.inspect(1)[
            "grant_record_revision"
        ],
        confirm_start_prepared_service=True,
        transport_secret=SECRET,
        service_uid=1200,
        service_gid=1201,
        coordinator_uid=1202,
    )
    assert start["database_lineage"] == ticket["database_lineage"]
    assert start["source_preparation_id"] == ticket["preparation_id"]
    assert all(call[0] == "stop" for call in state.calls)


def test_real_intermediate_commit_rolls_back_data_and_protected_metadata(upgradable):
    state = upgradable
    candidate(
        state,
        """import json, os, sqlite3
from pathlib import Path
from three_mm_application_sdk import ApplicationMigration
def first(db):
    raise RuntimeError('Existing prefix must not run')
def second(db):
    db.execute('ALTER TABLE business ADD COLUMN marker TEXT')
    db.execute("UPDATE business SET marker='intermediate'")
def third(db):
    with sqlite3.connect('file:state.sqlite3?mode=ro', uri=True) as observer:
        values = observer.execute('SELECT value, marker FROM business').fetchall()
        history = observer.execute('SELECT revision FROM three_mm_schema_migrations ORDER BY rowid').fetchall()
    assert values == [('preserved', 'intermediate')]
    assert history == [('0001',), ('0002',)]
    Path('upgrade-intermediate.json').write_text(json.dumps({'uid': os.geteuid(), 'values': values, 'history': history}))
    raise RuntimeError('Failure after committed forward migration')
def get_migrations():
    return [ApplicationMigration('0001', first), ApplicationMigration('0002', second), ApplicationMigration('0003', third)]
""",
        revision="0003",
    )
    ticket = issue(state)
    with pytest.raises(helper.RelationalUpgradeError, match="evidence retained"):
        run(state, ticket)
    assert (
        json.loads((state.data / "upgrade-intermediate.json").read_bytes())["uid"]
        == 1200
    )
    original(state)
    assert read(state, "SELECT revision FROM three_mm_schema_migrations") == [("0001",)]
    assert (state.instance / "active.json").read_bytes() == state.previous_active
    assert (state.instance / "relational.json").read_bytes() == state.previous_record
    marker = next(state.instance.glob(".database-*.rollback"))
    with sqlite3.connect(marker / "candidate-state.sqlite3") as db:
        assert db.execute("SELECT value,marker FROM business").fetchall() == [
            ("preserved", "intermediate")
        ]


@pytest.mark.parametrize("drift", ["revoke", "key"])
def test_authority_or_key_drift_after_migration_never_publishes_or_restarts(
    upgradable, drift
):
    state = upgradable
    ticket = issue(state)
    changed = []

    def mutate(*args, **kwargs):
        if args[1] == "check" and not changed:
            changed.append(True)
            if drift == "key":
                (state.transport_keys / (state.instance.name + ".key")).write_bytes(
                    b"x" * 32
                )
            else:
                state.manager.revoke(
                    1,
                    actor_token=state.token,
                    request_id=identity(),
                    expected_revision=state.manager.inspect(1)["grant_record_revision"],
                )
        return checkpoint(state, *args, **kwargs)

    with pytest.raises(helper.RelationalUpgradeError, match="evidence retained"):
        run(state, ticket, mutate)
    assert changed == [True]
    assert (state.instance / "relational.json").read_bytes() == state.previous_record
    assert action(state, ticket)["state"] == "execution_unconfirmed"
    marker = next(state.instance.glob(".database-*.rollback"))
    if drift == "key":
        assert read(state, "SELECT value,migrated FROM business") == [("preserved", 1)]
        assert not (marker / "candidate-state.sqlite3").exists()
        assert (
            state.transport_keys / (state.instance.name + ".key")
        ).read_bytes() == b"x" * 32
    else:
        original(state)
        assert read(state, "SELECT revision FROM three_mm_schema_migrations") == [
            ("0001",)
        ]
    assert all(call[0] == "stop" for call in state.calls)


def test_raw_native_metadata_tamper_is_detected_and_never_accepted(upgradable):
    state = upgradable
    candidate(
        state,
        script(
            import_code="with __import__('sqlite3').connect('state.sqlite3') as raw: raw.execute('DELETE FROM three_mm_relational_commits')"
        ),
    )
    ticket = issue(state)
    with pytest.raises(helper.RelationalUpgradeError, match="evidence retained"):
        run(state, ticket)
    original(state)
    assert (state.instance / "relational.json").read_bytes() == state.previous_record


def test_upgrade_fences_old_sealed_sql_without_claiming_a_rollback(upgradable):
    state = upgradable
    # Explicit test-only trusted host context, no real service bypass/SQL claim.
    state.runtime_nonce, state.database_lineage = (
        identity(),
        state.source["database_lineage"],
    )
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
    before = action(state, {"preparation_id": permit["transaction_id"]})
    assert before["data"]["permit"] == permit
    assert before["data"]["recovery_fenced_by"] == ticket["preparation_id"]
    run(state, ticket)
    assert status(state, permit["transaction_id"])["outcome"] == "execution_unconfirmed"


def test_upgrade_has_no_downgrade_or_replay_of_the_applied_prefix(upgradable):
    state = upgradable
    candidate(state, script(), revision="0000")
    ticket = issue(state)
    with pytest.raises(helper.RelationalUpgradeError, match="evidence retained"):
        run(state, ticket)
    original(state)
    assert read(state, "SELECT revision FROM three_mm_schema_migrations") == [("0001",)]


@pytest.mark.parametrize(
    "problem", ["key", "record", "source_wheel", "target_artifact", "rollback"]
)
def test_changed_source_or_target_is_refused_before_helper_effects(upgradable, problem):
    state = upgradable
    ticket = issue(state)
    calls = list(state.calls)
    if problem == "key":
        (state.transport_keys / (state.instance.name + ".key")).write_bytes(b"x" * 32)
    elif problem == "record":
        (state.instance / "relational.json").write_bytes(b"{}")
    elif problem == "source_wheel":
        (
            state.instance
            / "releases"
            / ticket["source_package_sha256"]
            / "service.whl"
        ).write_bytes(b"changed")
    elif problem == "target_artifact":
        state.archive.write_bytes(b"changed")
    else:
        (state.instance / (".database-" + identity() + ".rollback")).mkdir(mode=0o700)
    before = state.database.read_bytes()
    with pytest.raises((ValueError, RuntimeError)):
        run(
            state,
            ticket,
            lambda *a, **kw: pytest.fail("Checkpoint before exact source validation"),
        )
    assert state.database.read_bytes() == before and state.calls == calls
    assert not (
        state.instance / (".database-" + ticket["preparation_id"] + ".rollback")
    ).exists()
    assert action(state, ticket)["state"] == "recorded"


def test_archive_collision_retains_both_evidence_sets_after_core_completion(upgradable):
    state = upgradable
    ticket = issue(state)
    archive = state.instance / (".upgrade-evidence-" + ticket["preparation_id"])

    def existing_evidence(*args, **kwargs):
        result = checkpoint(state, *args, **kwargs)
        if args[1] == "finish":
            archive.mkdir(mode=0o700)
            (archive / "preserve").write_bytes(b"existing evidence")
        return result

    with pytest.raises(helper.RelationalUpgradeError, match="evidence retained"):
        run(state, ticket, existing_evidence)
    assert (archive / "preserve").read_bytes() == b"existing evidence"
    assert next(state.instance.glob(".database-*.rollback"))
    assert read(state, "SELECT value,migrated FROM business") == [("preserved", 1)]
    assert action(state, ticket)["state"] == "upgraded"
    with pytest.raises(ValueError, match="recovery is pending"):
        _prepared(state.instance, SECRET)


def test_changed_worker_profile_cannot_authorize_current_execution(upgradable):
    state = upgradable
    ticket = sign_metadata(
        SECRET, "database_upgrade", {**issue(state), "worker_profile_sha256": "0" * 64}
    )
    with pytest.raises(
        authority.AuthorityManagementError, match="worker_profile_changed"
    ):
        checkpoint(state, ticket, "authorize")
    with pytest.raises(ValueError, match="worker profile changed"):
        run(state, ticket)
    assert action(state, ticket)["state"] == "recorded"


def test_second_real_upgrade_preserves_old_schema_receipts_without_prefix_replay(
    upgradable,
):
    state = upgradable
    first = issue(state)
    run(state, first)
    state.source_archive = state.archive
    state.source = first
    state.source_revision = action(state, first)["revision"]
    candidate(
        state,
        """import os
from three_mm_application_sdk import ApplicationMigration
def applied(db):
    raise RuntimeError('Applied schema prefix must not execute again')
def third(db):
    assert os.geteuid() == 1200
    db.execute('ALTER TABLE business ADD COLUMN third INTEGER DEFAULT 3')
def get_migrations():
    return [ApplicationMigration('0001', applied), ApplicationMigration('0002', applied), ApplicationMigration('0003', third)]
""",
        revision="0003",
    )
    second = issue(state)
    run(state, second)
    original(state)
    assert read(state, "SELECT value,migrated,third FROM business") == [
        ("preserved", 1, 3)
    ]
    assert _prepared(state.instance, SECRET) == upgraded_lifecycle(second, SECRET)
    assert first["database_lineage"] != second["database_lineage"]
    assert len(list(state.instance.glob(".upgrade-evidence-*"))) == 2
