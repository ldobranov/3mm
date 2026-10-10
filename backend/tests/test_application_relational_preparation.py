"""Private exact Core authority + existing-schema helper, not deployed dispatch.

Real ZIP/native reviews/admin sessions/sealed grants. Root-only helper cases
operate on disposable paths; no application migration/factory runs as root.
"""

import json
import os
import sqlite3

import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.session import UserSession
from backend.services import application_authority_management as authority
from backend.services import application_relational_lifecycle as coordinator
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
from backend.tests.test_application_relational_admission import apply
from backend.tests.test_application_relational_review_api import store_package
from three_mm_application_sdk import ApplicationMigration, ApplicationStorage
from three_mm_application_sdk.files import ApplicationFileStorage
from three_mm_application_sdk.relational_wire import (
    _RelationalPreparationTicket,
    canonical,
    prepared_lifecycle,
    sign_metadata,
)
from three_mm_protocol.tests.test_application_relational_storage import (
    relational_request,
)
from three_mm_runtime import application_lifecycle as locks
from three_mm_runtime import application_relational_preparation as helper
from three_mm_runtime.application_activation import (
    ApplicationActivationError,
    activate_application_package,
    application_instance_id,
)
from three_mm_runtime.application_relational_session import _prepared

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Actual POSIX Core keys/clock"
)
ROOT_ONLY = pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() != 0,
    reason="Actual root helper boundary; no production ownership override",
)
SECRET = b"t" * 32


@pytest.fixture
def stopped(managed_installed):
    state = managed_installed
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["service"]["sdk_version"] = "1.3"
    definition["storage"]["relational"] = relational_request()
    store_package(state, definition)
    with state.engine.begin() as db:
        db.execute(
            update(Installation).values(
                enabled=False,
                status="disabled",
                instance_id=application_instance_id(state.validated.manifest.module_id),
            )
        )
    proof = native(state)
    apply(state, proof["native_review_id"])
    state.native_id = proof["native_review_id"]
    return state


def issue(state, **changes):
    return coordinator.issue_existing_schema_preparation(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "expected_grant_record_revision": state.manager.inspect(1)[
                "grant_record_revision"
            ],
            "confirm_owned_metadata_preparation": True,
            "transport_secret": SECRET,
            **changes,
        },
    )


def checkpoint(state, ticket, phase, **kwargs):
    return coordinator.preparation_checkpoint(
        state.manager,
        1,
        ticket,
        phase,
        actor_token=state.token,
        transport_secret=SECRET,
        **kwargs,
    )


def action(state, ticket):
    with state.keys.locked() as key, Session(state.engine) as db:
        row = db.get(Action, ticket["preparation_id"])
        return authority._load(db, key, "action", row, ticket["preparation_id"])


def test_preparation_is_explicit_one_use_and_does_not_enable(stopped):
    state = stopped
    for changes in (
        {"confirm_owned_metadata_preparation": False},
        {"actor_token": state.user_token},
        {"expected_grant_record_revision": identity()},
    ):
        with pytest.raises(authority.AuthorityManagementError):
            issue(state, **changes)
    ticket = issue(state)
    assert action(state, ticket)["state"] == "recorded"
    assert checkpoint(state, ticket, "authorize") == {"state": "authorized_not_started"}
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        issue(state, request_id=ticket["preparation_id"])
    checkpoint(state, ticket, "begin")
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        checkpoint(state, ticket, "begin")
    with Session(state.engine) as db:
        assert not db.get(Installation, 1).enabled
    assert action(state, ticket)["state"] == "execution_unconfirmed"


@pytest.mark.parametrize(
    "drift",
    [
        "revoke",
        "native_revoke",
        "enable",
        "configuration",
        "epoch",
        "recovery",
        "key",
        "actor",
        "artifact",
    ],
)
def test_each_checkpoint_rechecks_current_authority(stopped, drift):
    state = stopped
    ticket = issue(state)
    checkpoint(state, ticket, "begin")
    if drift == "revoke":
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=state.manager.inspect(1)["grant_record_revision"],
        )
    elif drift == "native_revoke":
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
    elif drift == "artifact":
        definition = state.validated.application_extension.model_dump(mode="json")
        definition["storage"]["relational"]["max_busy_ms"] = 0
        store_package(state, definition)
    else:
        with state.engine.begin() as db:
            if drift == "actor":
                db.execute(
                    update(UserSession)
                    .where(UserSession.id == 1)
                    .values(is_active=False)
                )
            elif drift == "recovery":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            else:
                db.execute(
                    update(Installation).values(
                        **{
                            "enable": {"enabled": True, "status": "active"},
                            "configuration": {
                                "configuration": {
                                    **state.configuration,
                                    "PRIVATE_NOTE": "changed",
                                }
                            },
                            "epoch": {"authority_epoch": identity()},
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


@pytest.mark.parametrize(
    "changes",
    [
        {"version": True},
        {"issued_at_ms": True},
        {"action": "migrate"},
        {"database_path": "/foreign"},
        {"deadline_ms": 0},
        {"service_sha256": "bad"},
    ],
)
def test_preparation_ticket_is_closed_and_not_migration_authority(stopped, changes):
    ticket = issue(stopped)
    malformed = sign_metadata(SECRET, "preparation", {**ticket, **changes})
    with pytest.raises(ValidationError):
        _RelationalPreparationTicket.model_validate(malformed)


@pytest.mark.parametrize("drift", ["deadline", "boot"])
def test_preparation_does_not_renew_after_deadline_or_reboot(
    stopped, monkeypatch, drift
):
    ticket = issue(stopped)
    monkeypatch.setattr(
        authority,
        "_clock",
        lambda: (
            (
                ticket["boot_id"]
                if drift == "deadline"
                else "00000000-0000-0000-0000-000000000001"
            ),
            ticket["deadline_ms"] if drift == "deadline" else ticket["issued_at_ms"],
        ),
    )
    with pytest.raises(authority.AuthorityManagementError, match="changed"):
        checkpoint(stopped, ticket, "authorize")
    assert action(stopped, ticket)["state"] == "recorded"


def test_completion_is_exact_signed_metadata_not_runtime_authority(stopped):
    ticket = issue(stopped)
    checkpoint(stopped, ticket, "begin")
    import hashlib

    body = {
        "version": 1,
        "preparation_id": ticket["preparation_id"],
        "lifecycle_sha256": hashlib.sha256(
            canonical(prepared_lifecycle(ticket, SECRET))
        ).hexdigest(),
        "outcome": "prepared_not_started",
    }
    for receipt in (
        sign_metadata(SECRET, "receipt", body),
        sign_metadata(
            SECRET, "preparation_result", {**body, "lifecycle_sha256": "0" * 64}
        ),
    ):
        with pytest.raises((ValueError, authority.AuthorityManagementError)):
            checkpoint(stopped, ticket, "finish", receipt=receipt)
    assert action(stopped, ticket)["state"] == "execution_unconfirmed"
    receipt = sign_metadata(SECRET, "preparation_result", body)
    assert checkpoint(stopped, ticket, "finish", receipt=receipt) == {
        "state": "prepared_not_started"
    }
    assert checkpoint(stopped, ticket, "finish", receipt=receipt) == {
        "state": "prepared_not_started",
        "historical": True,
    }


@pytest.fixture
def prepared_paths(stopped, tmp_path, monkeypatch):
    state = stopped
    state.runtime = tmp_path / "runtime"
    state.transport_keys = tmp_path / "transport-keys"
    state.helper_state = tmp_path / "helper-state"
    state.instance = state.runtime / application_instance_id(
        state.validated.manifest.module_id
    )
    for path in (
        state.runtime,
        state.transport_keys,
        state.helper_state,
        state.instance,
        state.instance / "releases",
        state.instance / "data",
        state.instance / "run",
    ):
        path.mkdir(mode=0o750)
    state.data = state.instance / "data"
    state.database = state.data / "state.sqlite3"
    storage = ApplicationStorage(state.data)
    revision = state.validated.application_extension.storage.schema_revision
    storage.migrate(
        [
            ApplicationMigration(
                revision, lambda db: db.execute("CREATE TABLE business(value TEXT)")
            )
        ],
        revision,
    )
    with storage.transaction() as db:
        db.execute("INSERT INTO business VALUES ('preserved')")
        storage.enqueue_outbox(
            db,
            outbox_id="once",
            event_type="example.event.v1",
            payload={"value": "preserved"},
            idempotency_key="once",
        )
    ApplicationFileStorage(state.data).put(
        "example_txt", b"preserved", expected_sha256=None
    )
    state.previous = canonical(
        {"instance_id": state.instance.name, "storage": {"schema_revision": revision}}
    )
    (state.instance / "active.json").write_bytes(state.previous)
    (state.instance / "active.json").chmod(0o640)
    (state.transport_keys / (state.instance.name + ".key")).write_bytes(SECRET)
    (state.transport_keys / (state.instance.name + ".key")).chmod(0o640)
    for path in (state.data, state.instance / "run"):
        os.chown(path, 1200, 1201)
    monkeypatch.setattr(locks, "RELEASE_MUTATION_LOCK", tmp_path / "release.lock")
    state.calls = []

    class Supervisor:
        def stop(self, identifier):
            state.calls.append(("stop", identifier))

        def restart(self, identifier):
            pytest.fail("Preparation restarted an application")

    state.supervisor = Supervisor()
    monkeypatch.setattr(
        ApplicationStorage,
        "migrate",
        lambda *a, **kw: pytest.fail("Root executed a package migration"),
    )
    return state


def run(state, ticket, callback=None):
    return helper.prepare_existing_relational_database(
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


def preserved(state):
    with sqlite3.connect(state.database) as db:
        assert db.execute("SELECT value FROM business").fetchall() == [("preserved",)]
        assert db.execute("SELECT COUNT(*) FROM three_mm_outbox").fetchone() == (1,)
        assert db.execute(
            "SELECT revision FROM three_mm_schema_migrations"
        ).fetchone() == (state.validated.application_extension.storage.schema_revision,)
    assert (
        ApplicationFileStorage(state.data, mode="read").get("example_txt").content
        == b"preserved"
    )


@ROOT_ONLY
def test_real_helper_publishes_fixed_metadata_preserving_data_and_leaves_disabled(
    prepared_paths,
):
    state = prepared_paths
    ticket = issue(state)
    result = run(state, ticket)
    assert result["outcome"] == "prepared_not_started"
    assert _prepared(state.instance, SECRET) == prepared_lifecycle(ticket, SECRET)
    assert not list(state.instance.glob(".activation-*.rollback"))
    assert (state.instance / "relational.json").stat().st_uid == 0
    assert state.database.stat().st_uid == 1200
    assert action(state, ticket)["state"] == "prepared"
    assert state.calls == [("stop", state.instance.name)]
    preserved(state)
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        checkpoint(state, ticket, "authorize")
    with pytest.raises(ApplicationActivationError, match="not implemented"):
        activate_application_package(
            state.archive, state.validated.sha256, root=state.runtime
        )
    with Session(state.engine) as db:
        assert not db.get(Installation, 1).enabled


@ROOT_ONLY
@pytest.mark.parametrize(
    "problem",
    [
        "missing_db",
        "schema",
        "partial_receipt",
        "partial_record",
        "key",
        "data_link",
        "wheel_link",
    ],
)
def test_invalid_existing_state_is_not_created_repaired_or_started(
    prepared_paths, problem
):
    state = prepared_paths
    ticket = issue(state)
    if problem == "missing_db":
        state.database.unlink()
    elif problem in {"schema", "partial_receipt"}:
        with sqlite3.connect(state.database) as db:
            db.execute(
                "UPDATE three_mm_schema_migrations SET revision='wrong'"
                if problem == "schema"
                else "CREATE TABLE three_mm_relational_commits(fake TEXT)"
            )
    elif problem == "partial_record":
        (state.instance / "relational.json").write_text("{}")
    elif problem == "key":
        (state.transport_keys / (state.instance.name + ".key")).write_bytes(b"x" * 32)
    elif problem == "data_link":
        state.data.rename(state.instance / "old-data")
        state.data.symlink_to(state.instance / "old-data", target_is_directory=True)
    else:
        release = state.instance / "releases" / state.validated.sha256
        release.mkdir(mode=0o750)
        (release / "service.whl").symlink_to(state.archive)
    with pytest.raises((helper.RelationalPreparationError, ValueError, OSError)):
        run(state, ticket)
    assert (state.instance / "active.json").read_bytes() == state.previous
    if problem == "missing_db":
        assert not state.database.exists()
    assert all(call[0] == "stop" for call in state.calls)


@ROOT_ONLY
def test_publication_failure_restores_preimage_but_retains_review_marker(
    prepared_paths, monkeypatch
):
    state = prepared_paths
    ticket = issue(state)
    original = helper._write_atomic

    def fail_record(path, *args):
        if path.name == "relational.json":
            raise OSError("publication failed")
        return original(path, *args)

    monkeypatch.setattr(helper, "_write_atomic", fail_record)
    with pytest.raises(helper.RelationalPreparationError, match="recovery review"):
        run(state, ticket)
    preserved(state)
    assert (state.instance / "active.json").read_bytes() == state.previous
    assert not (state.instance / "relational.json").exists()
    with sqlite3.connect(state.database) as db:
        assert (
            db.execute(
                "SELECT name FROM sqlite_schema WHERE name='three_mm_relational_lineage'"
            ).fetchone()
            is None
        )
    marker = next(state.instance.glob(".activation-*.rollback"))
    assert (
        json.loads((marker / "activation.json").read_bytes())["phase"]
        == "restored_not_started"
    )
    assert action(state, ticket)["state"] == "execution_unconfirmed"


@ROOT_ONLY
def test_lost_finish_ack_retains_candidate_and_snapshot_without_rollback_or_retry(
    prepared_paths,
):
    state = prepared_paths
    ticket = issue(state)

    def lose_ack(*args, **kwargs):
        result = checkpoint(state, *args, **kwargs)
        if args[1] == "finish":
            raise OSError("lost response after Core commit")
        return result

    with pytest.raises(helper.RelationalPreparationError, match="recovery review"):
        run(state, ticket, lose_ack)
    assert action(state, ticket)["state"] == "prepared"
    assert json.loads(
        (state.instance / "relational.json").read_bytes()
    ) == prepared_lifecycle(ticket, SECRET)
    marker = next(state.instance.glob(".activation-*.rollback"))
    assert (marker / "database.json").is_file() and (marker / "state.sqlite3").is_file()
    assert (
        json.loads((marker / "activation.json").read_bytes())["phase"]
        == "completion_unconfirmed"
    )
    with pytest.raises(ValueError, match="recovery is pending"):
        _prepared(state.instance, SECRET)
    with pytest.raises(ApplicationActivationError, match="unfinished rollback"):
        run(state, ticket)
    assert state.calls == [("stop", state.instance.name)]
    preserved(state)


@ROOT_ONLY
def test_revoke_before_publication_restores_metadata_and_never_starts(prepared_paths):
    state = prepared_paths
    ticket = issue(state)

    def revoke(*args, **kwargs):
        if args[1] == "check":
            state.manager.revoke(
                1,
                actor_token=state.token,
                request_id=identity(),
                expected_revision=state.manager.inspect(1)["grant_record_revision"],
            )
        return checkpoint(state, *args, **kwargs)

    with pytest.raises(helper.RelationalPreparationError):
        run(state, ticket, revoke)
    assert (state.instance / "active.json").read_bytes() == state.previous
    assert not (state.instance / "relational.json").exists()
    preserved(state)


@ROOT_ONLY
def test_core_checkpoints_never_hold_an_application_sql_write_lock(prepared_paths):
    state = prepared_paths
    ticket = issue(state)

    def probe(*args, **kwargs):
        with sqlite3.connect(state.database, timeout=0) as db:
            db.execute("BEGIN IMMEDIATE")
            db.rollback()
        return checkpoint(state, *args, **kwargs)

    run(state, ticket, probe)
    assert action(state, ticket)["state"] == "prepared"


@ROOT_ONLY
def test_unconfirmed_stop_keeps_evidence_and_never_runs_sdk_sql(
    prepared_paths, monkeypatch
):
    state = prepared_paths
    ticket = issue(state)

    def fail_stop(_instance):
        raise OSError("stop unconfirmed")

    monkeypatch.setattr(state.supervisor, "stop", fail_stop)
    monkeypatch.setattr(
        helper,
        "_prepare_receipt_metadata",
        lambda *a, **kw: pytest.fail("SQL before confirmed stop"),
    )
    with pytest.raises(helper.RelationalPreparationError, match="recovery review"):
        run(state, ticket)
    assert action(state, ticket)["state"] == "recorded"
    assert (state.instance / "active.json").read_bytes() == state.previous
    assert list(state.instance.glob(".activation-*.rollback"))
    preserved(state)


@ROOT_ONLY
def test_existing_helper_locks_exclude_overlapping_preparation(prepared_paths):
    state = prepared_paths
    ticket = issue(state)
    with locks._release_lock():
        with pytest.raises(BlockingIOError):
            run(state, ticket)
    assert not state.calls and not list(state.instance.glob(".activation-*.rollback"))
