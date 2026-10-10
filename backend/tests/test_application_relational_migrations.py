"""Real signed lifecycle -> non-root process -> own DB -> protected publication.

Disposable Linux paths only; no production enable/dispatch or fabricated grants.
"""

import hashlib
import io
import json
import os
import sqlite3
import time
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import update

from backend.db.module import ModulePackage
from backend.services import application_authority_management as authority
from backend.services import application_relational_lifecycle as coordinator
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_relational_preparation import (
    ROOT_ONLY,
    SECRET,
    action,
    apply,
    checkpoint,
    identity,
    issue,
    managed_installed,
    native,
    prepared_paths,
    source_installed,
    source_subject,
    stopped,
)
from three_mm_application_sdk.files import ApplicationFileStorage
from three_mm_application_sdk.relational_wire import (
    _RelationalMigrationPreparationTicket,
    _RelationalPreparationTicket,
    prepared_lifecycle,
    sign_metadata,
)
from three_mm_protocol.tests.test_application_relational_storage import (
    relational_request,
)
from three_mm_runtime import application_relational_migrations as worker
from three_mm_runtime import application_relational_preparation as helper
from three_mm_runtime.application_relational_session import _prepared

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Real POSIX authority/worker"
)


def migration_ticket(state, **changes):
    return coordinator.issue_migrated_schema_preparation(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "expected_grant_record_revision": state.manager.inspect(1)[
                "grant_record_revision"
            ],
            "confirm_owned_business_migrations": True,
            "transport_secret": SECRET,
            **changes,
        },
    )


def candidate(state, code, *, declaration=None, revision="0002", namespace=False):
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as output:
        if namespace:
            output.writestr("workflow_reference/", "")
        else:
            output.writestr("workflow_reference/__init__.py", "")
        output.writestr("workflow_reference/migrations.py", code)
        # A service factory MUST NOT be imported/executed by this lifecycle.
        output.writestr(
            "workflow_reference/service.py",
            "raise RuntimeError('SERVICE FACTORY WAS IMPORTED')",
        )
    manifest = state.validated.manifest.model_dump(mode="json")
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["service"]["artifact_sha256"] = hashlib.sha256(
        wheel.getvalue()
    ).hexdigest()
    definition["storage"]["schema_revision"] = revision
    if declaration:
        definition["storage"]["relational"].update(declaration)
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        output.writestr("application-extension.json", json.dumps(definition))
        output.writestr(definition["service"]["artifact"], wheel.getvalue())
    state.validated = validate_module_package(blob.getvalue())
    state.archive = state.root / "modules" / (state.validated.sha256 + ".zip")
    state.archive.write_bytes(blob.getvalue())
    with state.engine.begin() as db:
        db.execute(
            update(ModulePackage)
            .where(ModulePackage.id == 1)
            .values(
                sha256=state.validated.sha256,
                size_bytes=len(blob.getvalue()),
                manifest=manifest,
                file_path=str(state.archive),
            )
        )
    proof = native(state)
    apply(state, proof["native_review_id"])


def script(
    action="db.execute('ALTER TABLE business ADD COLUMN migrated INTEGER DEFAULT 1')",
    *,
    factory="",
    import_code="",
):
    return f"""import os
from three_mm_application_sdk import ApplicationMigration
{import_code}
def first(db):
    db.execute("CREATE TABLE business(value TEXT)")
def second(db):
    assert os.getuid() == os.geteuid() == 1200
    assert os.getgid() == os.getegid() == 1201
    assert not os.getgroups()
    assert not os.environ.get("AI_SETTINGS_MASTER_KEY")
    {action}
def get_migrations():
    {factory or "pass"}
    return [ApplicationMigration("0001", first), ApplicationMigration("0002", second)]
"""


@pytest.fixture
def migratable(prepared_paths, tmp_path):
    state = prepared_paths
    # Exact disposable ancestors must be traversable by the real worker UID.
    for directory in (tmp_path, tmp_path.parent, tmp_path.parent.parent):
        directory.chmod(directory.stat().st_mode | 0o111)
    for directory in (state.runtime, state.instance, state.instance / "releases"):
        os.chown(directory, 0, 1201)
    candidate(state, script())
    return state


def run(state, ticket, callback=None):
    return helper.prepare_migrated_relational_database(
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


def read(state, sql):
    with sqlite3.connect(state.database.as_uri() + "?mode=ro", uri=True) as connection:
        result = connection.execute(sql).fetchall()
    connection.close()
    return result


def marker(state):
    return next(state.instance.glob(".activation-*.rollback"))


def test_separate_confirmation_ticket_and_signing_purpose(stopped):
    for change in (
        {"confirm_owned_business_migrations": False},
        {"actor_token": stopped.user_token},
        {"expected_grant_record_revision": identity()},
    ):
        with pytest.raises(authority.AuthorityManagementError):
            migration_ticket(stopped, **change)
    ticket = migration_ticket(stopped)
    _RelationalMigrationPreparationTicket.model_validate(ticket)
    with pytest.raises(ValidationError):
        _RelationalPreparationTicket.model_validate(ticket)
    metadata_only = issue(stopped)
    with pytest.raises(ValidationError):
        _RelationalMigrationPreparationTicket.model_validate(metadata_only)
    forged = sign_metadata(SECRET, "preparation", ticket)
    with pytest.raises(ValueError, match="signature"):
        checkpoint(stopped, forged, "begin")
    with pytest.raises(authority.AuthorityManagementError):
        migration_ticket(stopped, request_id=ticket["preparation_id"])
    checkpoint(stopped, ticket, "begin")
    with pytest.raises(authority.AuthorityManagementError):
        checkpoint(stopped, ticket, "begin")


@pytest.mark.parametrize("drift", ["worker_profile", "deadline", "revoke"])
def test_migration_ticket_rechecks_profile_deadline_and_current_grant(
    stopped, monkeypatch, drift
):
    ticket = migration_ticket(stopped)
    if drift == "worker_profile":
        ticket = sign_metadata(
            SECRET,
            "migration_preparation",
            {**ticket, "worker_profile_sha256": "0" * 64},
        )
    elif drift == "deadline":
        monkeypatch.setattr(
            authority, "_clock", lambda: (ticket["boot_id"], ticket["deadline_ms"])
        )
    else:
        stopped.manager.revoke(
            1,
            actor_token=stopped.token,
            request_id=identity(),
            expected_revision=stopped.manager.inspect(1)["grant_record_revision"],
        )
    with pytest.raises(authority.AuthorityManagementError):
        checkpoint(stopped, ticket, "begin")


@ROOT_ONLY
@pytest.mark.parametrize("fresh", [False, True])
def test_real_non_root_forward_migration_and_initial_schema_publish(migratable, fresh):
    state = migratable
    if fresh:
        state.database.unlink()
    ticket = migration_ticket(state)

    def unlocked(*args, **kwargs):
        if state.database.exists():
            with sqlite3.connect(state.database, timeout=0) as db:
                db.execute("BEGIN IMMEDIATE")
                db.rollback()
        return checkpoint(state, *args, **kwargs)

    run(state, ticket, unlocked)
    assert action(state, ticket)["state"] == "prepared"
    assert _prepared(state.instance, SECRET) == prepared_lifecycle(ticket, SECRET)
    assert read(
        state, "SELECT revision FROM three_mm_schema_migrations ORDER BY rowid"
    ) == [("0001",), ("0002",)]
    assert read(state, "SELECT value,migrated FROM business") == (
        [] if fresh else [("preserved", 1)]
    )
    assert read(state, "SELECT COUNT(*) FROM three_mm_outbox") == [(0 if fresh else 1,)]
    assert state.database.stat().st_uid == 1200
    assert state.calls == [("stop", state.instance.name)]
    assert not list(state.instance.glob(".activation-*.rollback"))


@ROOT_ONLY
def test_real_worker_accepts_a_namespace_package_inside_the_pinned_wheel(migratable):
    state = migratable
    candidate(state, script(), namespace=True)
    ticket = migration_ticket(state)
    run(state, ticket)
    assert read(state, "SELECT value,migrated FROM business") == [("preserved", 1)]
    assert action(state, ticket)["state"] == "prepared"
    assert not list(state.instance.glob(".activation-*.rollback"))


@ROOT_ONLY
def test_metadata_only_ticket_cannot_start_worker(migratable, monkeypatch):
    ticket = issue(migratable)
    monkeypatch.setattr(
        helper,
        "run_business_migrations",
        lambda *a, **kw: pytest.fail("Worker ran without separate permission"),
    )
    with pytest.raises(ValidationError):
        run(migratable, ticket)
    assert not migratable.calls
    ticket = migration_ticket(migratable)
    with pytest.raises(ValidationError):
        helper.prepare_existing_relational_database(
            migratable.archive,
            ticket,
            configuration=migratable.configuration,
            root=migratable.runtime,
            key_root=migratable.transport_keys,
            state_root=migratable.helper_state,
            service_uid=1200,
            service_gid=1201,
            checkpoint=lambda *a: None,
        )


@ROOT_ONLY
@pytest.mark.parametrize(
    "action_sql",
    [
        "CREATE TABLE three_mm_stolen(x)",
        "DROP TABLE three_mm_outbox",
        "UPDATE three_mm_schema_migrations SET revision='fake'",
        "DELETE FROM three_mm_outbox",
        "ATTACH DATABASE ':memory:' AS other",
        "CREATE TEMP TABLE escape(x)",
        "CREATE VIRTUAL TABLE escape USING fts5(x)",
        "PRAGMA writable_schema=ON",
        "COMMIT",
        "SELECT load_extension('missing')",
        "ALTER TABLE business RENAME TO three_mm_escape",
        "CREATE TRIGGER corrupt AFTER UPDATE ON business BEGIN DELETE FROM three_mm_outbox; END",
    ],
)
def test_unsafe_migration_sql_and_caught_failures_do_not_commit(migratable, action_sql):
    state = migratable
    mutation = f"db.execute({action_sql!r})"
    if action_sql.startswith("CREATE TRIGGER"):
        mutation += "; db.execute(\"UPDATE business SET value='trigger'\")"
    candidate(state, script(mutation))
    ticket = migration_ticket(state)
    with pytest.raises(helper.RelationalPreparationError, match="recovery review"):
        run(state, ticket)
    assert read(state, "SELECT value FROM business") == [("preserved",)]
    assert read(state, "SELECT revision FROM three_mm_schema_migrations") == [("0001",)]
    assert read(state, "SELECT COUNT(*) FROM three_mm_outbox") == [(1,)]
    assert (state.instance / "active.json").read_bytes() == state.previous
    assert (
        json.loads((marker(state) / "activation.json").read_bytes())["phase"]
        == "restored_not_started"
    )
    assert action(state, ticket)["state"] == "execution_unconfirmed"


@ROOT_ONLY
@pytest.mark.parametrize("fresh", [False, True])
def test_package_failure_restores_data_files_and_original_absence(migratable, fresh):
    state = migratable
    if fresh:
        state.database.unlink()
    candidate(
        state,
        script(
            "db.execute(\"UPDATE business SET value='candidate'\"); raise RuntimeError('failed')"
        ),
    )
    ticket = migration_ticket(state)
    with pytest.raises(helper.RelationalPreparationError):
        run(state, ticket)
    assert state.database.exists() is not fresh
    if not fresh:
        assert read(state, "SELECT value FROM business") == [("preserved",)]
    assert (marker(state) / "candidate-state.sqlite3").is_file()
    if fresh:
        with sqlite3.connect(marker(state) / "candidate-state.sqlite3") as db:
            assert db.execute(
                "SELECT revision FROM three_mm_schema_migrations"
            ).fetchall() == [("0001",)]
    assert not (state.instance / "relational.json").exists()
    assert action(state, ticket)["state"] == "execution_unconfirmed"
    assert all(call[0] == "stop" for call in state.calls)


@ROOT_ONLY
def test_real_intermediate_commit_is_observed_before_coherent_rollback(
    migratable, monkeypatch
):
    """Adapt the external three-step scenario; import failure cannot pass it."""
    state = migratable
    candidate(
        state,
        """import json, os, sqlite3
from pathlib import Path
from three_mm_application_sdk import ApplicationMigration
def first(db):
    raise RuntimeError('Existing prefix must never run')
def second(db):
    db.execute('ALTER TABLE business ADD COLUMN marker TEXT')
    db.execute("UPDATE business SET marker='intermediate'")
def third(db):
    with sqlite3.connect('file:state.sqlite3?mode=ro', uri=True) as observer:
        values = observer.execute('SELECT value, marker FROM business').fetchall()
        history = observer.execute(
            'SELECT revision FROM three_mm_schema_migrations ORDER BY rowid'
        ).fetchall()
    assert values == [('preserved', 'intermediate')]
    assert history == [('0001',), ('0002',)]
    Path('intermediate-commit.json').write_text(json.dumps({
        'uid': os.geteuid(), 'gid': os.getegid(),
        'values': values, 'history': history,
    }))
    raise RuntimeError('Failure AFTER independently observed committed migration')
def get_migrations():
    return [ApplicationMigration('0001', first),
            ApplicationMigration('0002', second),
            ApplicationMigration('0003', third)]
""",
        revision="0003",
    )
    ticket = migration_ticket(state)
    original = helper.run_business_migrations
    entered = []

    def checked_worker(*args, **kwargs):
        assert action(state, ticket)["state"] == "execution_unconfirmed"
        entered.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(helper, "run_business_migrations", checked_worker)
    with pytest.raises(helper.RelationalPreparationError, match="recovery review"):
        run(state, ticket)
    assert entered == [True]
    assert json.loads((state.data / "intermediate-commit.json").read_bytes()) == {
        "uid": 1200,
        "gid": 1201,
        "values": [["preserved", "intermediate"]],
        "history": [["0001"], ["0002"]],
    }
    with sqlite3.connect(marker(state) / "candidate-state.sqlite3") as db:
        assert db.execute("SELECT value,marker FROM business").fetchall() == [
            ("preserved", "intermediate")
        ]
        assert db.execute(
            "SELECT revision FROM three_mm_schema_migrations ORDER BY rowid"
        ).fetchall() == [("0001",), ("0002",)]
    assert read(state, "SELECT value FROM business") == [("preserved",)]
    assert "marker" not in [
        row[1] for row in read(state, "PRAGMA table_info(business)")
    ]
    assert read(state, "SELECT revision FROM three_mm_schema_migrations") == [("0001",)]
    assert read(state, "SELECT COUNT(*) FROM three_mm_outbox") == [(1,)]
    assert (
        ApplicationFileStorage(state.data, mode="read").get("example_txt").content
        == b"preserved"
    )
    assert (state.instance / "active.json").read_bytes() == state.previous
    assert not (state.instance / "relational.json").exists()
    assert action(state, ticket)["state"] == "execution_unconfirmed"
    assert json.loads((marker(state) / "activation.json").read_bytes())["phase"] == (
        "restored_not_started"
    )
    assert all(call[0] == "stop" for call in state.calls)


@ROOT_ONLY
def test_file_attach_cannot_write_an_unapproved_database(migratable):
    state = migratable
    foreign = state.data / "unapproved.sqlite3"
    candidate(
        state,
        script(
            "db.execute('ATTACH DATABASE ? AS foreign_db', ('unapproved.sqlite3',)); "
            "db.execute('CREATE TABLE foreign_db.escape(value TEXT)')"
        ),
    )
    ticket = migration_ticket(state)
    with pytest.raises(helper.RelationalPreparationError, match="recovery review"):
        run(state, ticket)
    assert not foreign.exists()
    assert read(state, "SELECT value FROM business") == [("preserved",)]
    assert read(state, "SELECT revision FROM three_mm_schema_migrations") == [("0001",)]
    assert action(state, ticket)["state"] == "execution_unconfirmed"


def test_migration_factory_refuses_a_preloaded_module_outside_the_wheel():
    # json is a loaded Core dependency, not code in the signed application wheel.
    with pytest.raises(ValueError, match="pinned wheel"):
        worker._migration_factory(Path("/unused-wheel.whl"), "json:loads")


@ROOT_ONLY
def test_worker_timeout_in_factory_is_bounded_and_not_replayed(migratable, monkeypatch):
    state = migratable
    candidate(
        state,
        script(
            factory="from pathlib import Path; Path('factory-entered').touch(); import time; time.sleep(60)"
        ),
    )
    monkeypatch.setattr(worker, "MAX_WORKER_MS", 3000)
    ticket = migration_ticket(state)
    started = time.monotonic()
    with pytest.raises(helper.RelationalPreparationError):
        run(state, ticket)
    assert time.monotonic() - started < 12
    assert (state.data / "factory-entered").is_file()
    assert read(state, "SELECT value FROM business") == [("preserved",)]
    with pytest.raises(Exception, match="unfinished rollback"):
        run(state, ticket)


@ROOT_ONLY
def test_revoke_after_worker_before_sdk_metadata_restores_preimage(migratable):
    state = migratable
    ticket = migration_ticket(state)

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
    assert read(state, "SELECT value FROM business") == [("preserved",)]
    assert read(state, "SELECT revision FROM three_mm_schema_migrations") == [("0001",)]
    assert not (state.instance / "relational.json").exists()


@ROOT_ONLY
def test_lost_finish_ack_keeps_migrated_candidate_and_blocks_runtime(migratable):
    state = migratable
    ticket = migration_ticket(state)

    def lost(*args, **kwargs):
        result = checkpoint(state, *args, **kwargs)
        if args[1] == "finish":
            raise OSError("Lost ACK after Core recorded receipt")
        return result

    with pytest.raises(helper.RelationalPreparationError):
        run(state, ticket, lost)
    assert read(state, "SELECT value,migrated FROM business") == [("preserved", 1)]
    assert action(state, ticket)["state"] == "prepared"
    assert (marker(state) / "state.sqlite3").is_file()
    with pytest.raises(ValueError, match="recovery is pending"):
        _prepared(state.instance, SECRET)


@ROOT_ONLY
@pytest.mark.parametrize(
    "problem",
    ["caught_sql", "statement", "value", "rows", "busy", "divergent", "too_many"],
)
def test_migration_bounds_and_forward_history_do_not_become_legacy_fallback(
    migratable, problem
):
    state = migratable
    actions = {
        "caught_sql": "try:\n        db.execute('DROP TABLE three_mm_outbox')\n    except Exception:\n        pass",
        "statement": "db.execute('SELECT 1 ' + ' ' * 65536)",
        "value": "db.execute('UPDATE business SET value=?', ('x' * 262145,))",
        "rows": "db.execute('WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x WHERE n<1001) SELECT n FROM x').fetchall()",
        "busy": "db.execute(\"UPDATE business SET value='attempt'\")",
        "divergent": "pass",
        "too_many": "pass",
    }
    factory = {
        "divergent": "return [ApplicationMigration('wrong', first), ApplicationMigration('0002', second)]",
        "too_many": "return [ApplicationMigration(str(i), first) for i in range(129)]",
    }.get(problem, "")
    # The child cannot obtain a second write lock; bounded failure must unwind
    # even when the package catches the exception. Never native raw fallback.
    import_code = (
        "keeper = __import__('sqlite3').connect('state.sqlite3', timeout=0); keeper.execute('BEGIN IMMEDIATE')"
        if problem == "busy"
        else ""
    )
    candidate(state, script(actions[problem], factory=factory, import_code=import_code))
    ticket = migration_ticket(state)
    with pytest.raises(helper.RelationalPreparationError):
        run(state, ticket)
    assert read(state, "SELECT value FROM business") == [("preserved",)]
    assert read(state, "SELECT revision FROM three_mm_schema_migrations") == [("0001",)]
    assert action(state, ticket)["state"] == "execution_unconfirmed"


def test_worker_refuses_root_before_any_package_import():
    boot, now = worker._clock()
    plan = worker._WorkerPlan.model_validate(
        {
            "instance_root": "/nonexistent",
            "package_sha256": "1" * 64,
            "service_sha256": "2" * 64,
            "migration_entrypoint": "no_package:get_migrations",
            "schema_revision": "0001",
            "declaration": relational_request(),
            "database_present": False,
            "service_uid": 1200,
            "service_gid": 1201,
            "boot_id": boot,
            "issued_at_ms": now,
            "deadline_ms": now + 1000,
        }
    )
    if os.geteuid() == 1200:
        pytest.skip("Worker UID equals test UID")
    with pytest.raises(ValueError, match="non-root"):
        worker._worker(plan)


@ROOT_ONLY
def test_unconfirmed_worker_stop_never_restores_over_possible_live_writes(
    migratable, monkeypatch
):
    state = migratable
    ticket = migration_ticket(state)

    def unconfirmed(*args, **kwargs):
        with sqlite3.connect(state.database) as db:
            db.execute("UPDATE business SET value='possibly live worker'")
        raise worker.MigrationWorkerUnconfirmed("Stop not confirmed")

    monkeypatch.setattr(helper, "run_business_migrations", unconfirmed)
    with pytest.raises(helper.RelationalPreparationError):
        run(state, ticket)
    assert read(state, "SELECT value FROM business") == [("possibly live worker",)]
    with sqlite3.connect(marker(state) / "state.sqlite3") as db:
        assert db.execute("SELECT value FROM business").fetchall() == [("preserved",)]
    assert not (marker(state) / "candidate-state.sqlite3").exists()
    assert not (state.instance / "relational.json").exists()
    assert action(state, ticket)["state"] == "execution_unconfirmed"
    with pytest.raises(Exception, match="unfinished rollback"):
        run(state, ticket)


def test_worker_stop_has_no_unbounded_wait(monkeypatch):
    class Hung:
        pid = 123

        def wait(self, timeout):
            assert timeout == 2
            raise worker.subprocess.TimeoutExpired("worker", timeout)

    monkeypatch.setattr(worker.os, "killpg", lambda *a: None)
    with pytest.raises(worker.MigrationWorkerUnconfirmed, match="stop unconfirmed"):
        worker._stop_worker(Hung())


def test_worker_completion_does_not_reap_pid_before_group_cleanup(monkeypatch):
    from types import SimpleNamespace

    process = SimpleNamespace(pid=123)

    def status(kind, pid, flags):
        assert kind == os.P_PID and pid == process.pid
        assert flags & os.WNOWAIT  # Cleanup cannot target a reused foreign PID.
        return SimpleNamespace(si_status=0, si_code=os.CLD_EXITED)

    monkeypatch.setattr(worker, "_remaining", lambda plan: 1)
    monkeypatch.setattr(worker.os, "waitid", status)
    assert worker._wait_worker(process, None) == 0
