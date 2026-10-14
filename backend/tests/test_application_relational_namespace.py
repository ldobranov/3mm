"""Exact signed Core consent -> root-owned absent namespace, never auto-start.

All roots are disposable. Root-only cases do real ownership changes and the
integration runs the existing migration child with actual UID/GID 1200/1201.
"""

import hashlib
import json
import os
import stat

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.session import UserSession
from backend.services import application_authority_management as authority
from backend.services import application_relational_lifecycle as coordinator
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_policy_reviews import PolicyReviewStoreError
from backend.tests.test_application_relational_preparation import (
    ROOT_ONLY,
    SECRET,
    action,
    checkpoint,
    identity,
    issue,
    managed_installed,
    source_installed,
    source_subject,
    stopped,
)
from three_mm_application_sdk.relational_wire import (
    _RelationalMigrationPreparationTicket,
    _RelationalNamespacePreparationTicket,
    _RelationalPreparationTicket,
    canonical,
    prepared_lifecycle,
    sign_metadata,
)
from three_mm_runtime import application_lifecycle as locks
from three_mm_runtime import application_relational_namespace as helper
from three_mm_runtime.application_activation import (
    ApplicationActivationError,
    _require_no_pending_rollback,
    application_instance_id,
)

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Real POSIX namespace authority"
)


def namespace_ticket(state, **changes):
    return coordinator.issue_namespace_preparation(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "expected_grant_record_revision": state.manager.inspect(1)[
                "grant_record_revision"
            ],
            "confirm_fresh_owned_namespace": True,
            "transport_secret": SECRET,
            "service_uid": 1200,
            "service_gid": 1201,
            "coordinator_uid": 1202,
            **changes,
        },
    )


@pytest.fixture
def absent_paths(stopped, tmp_path, monkeypatch):
    state = stopped
    state.runtime = tmp_path / "runtime"
    state.transport_keys = tmp_path / "transport-keys"
    state.helper_state = tmp_path / "helper-state"
    for path in (state.runtime, state.transport_keys, state.helper_state):
        path.mkdir(mode=0o750)
    if os.geteuid() == 0:
        os.chown(state.runtime, 0, 1201)
    state.instance = state.runtime / application_instance_id(
        state.validated.manifest.module_id
    )
    state.data = state.instance / "data"
    state.database = state.data / "state.sqlite3"
    state.key_path = state.transport_keys / (state.instance.name + ".key")
    state.marker = state.helper_state / (
        "relational-namespace-" + state.instance.name + ".json"
    )
    state.calls = []

    class Supervisor:
        def stop(self, identifier):
            state.calls.append(("stop", identifier))

        def restart(self, _identifier):
            pytest.fail("Namespace setup enabled/restarted an application")

    state.supervisor = Supervisor()
    monkeypatch.setattr(locks, "RELEASE_MUTATION_LOCK", tmp_path / "release.lock")
    return state


def run(state, ticket, callback=None, **changes):
    return helper.create_fresh_relational_namespace(
        state.archive,
        ticket,
        **{
            "configuration": state.configuration,
            "transport_secret": SECRET,
            "root": state.runtime,
            "key_root": state.transport_keys,
            "state_root": state.helper_state,
            "service_uid": 1200,
            "service_gid": 1201,
            "coordinator_uid": 1202,
            "supervisor": state.supervisor,
            "checkpoint": callback or (lambda *a, **kw: checkpoint(state, *a, **kw)),
            **changes,
        },
    )


def test_explicit_confirmation_current_admin_and_grant_are_required(stopped):
    for changes in (
        {"confirm_fresh_owned_namespace": False},
        {"actor_token": stopped.user_token},
        {"expected_grant_record_revision": identity()},
    ):
        with pytest.raises(authority.AuthorityManagementError):
            namespace_ticket(stopped, **changes)
    ticket = namespace_ticket(stopped)
    assert action(stopped, ticket)["state"] == "recorded"
    assert ticket["transport_key_sha256"] == hashlib.sha256(SECRET).hexdigest()
    assert SECRET.decode() not in canonical(ticket).decode()
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        namespace_ticket(stopped, request_id=ticket["preparation_id"])


@pytest.mark.parametrize(
    "changes",
    [
        {"service_uid": 0},
        {"service_gid": 0},
        {"service_uid": True},
        {"service_gid": -1},
        {"service_uid": 2147483648},
        {"coordinator_uid": 0},
        {"coordinator_uid": True},
        {"coordinator_uid": 1200},
    ],
)
def test_root_or_malformed_credentials_are_not_signed(stopped, changes):
    with Session(stopped.engine) as db:
        before = db.scalar(select(func.count()).select_from(Action))
    with pytest.raises(authority.AuthorityManagementError):
        namespace_ticket(stopped, **changes)
    with Session(stopped.engine) as db:
        assert db.scalar(select(func.count()).select_from(Action)) == before
    ticket = namespace_ticket(stopped)
    malformed = sign_metadata(SECRET, "namespace_preparation", {**ticket, **changes})
    with pytest.raises(ValidationError):
        _RelationalNamespacePreparationTicket.model_validate(malformed)


@pytest.mark.parametrize(
    "drift",
    [
        "revoke",
        "native",
        "epoch",
        "enable",
        "recovery",
        "actor",
        "key",
        "configuration",
        "deadline",
        "boot",
    ],
)
def test_namespace_checkpoint_rechecks_each_current_binding(
    stopped, monkeypatch, drift
):
    state = stopped
    ticket = namespace_ticket(state)
    checkpoint(state, ticket, "begin")
    assert action(state, ticket)["state"] == "execution_unconfirmed"
    with Session(state.engine) as db:
        row = db.get(Action, ticket["preparation_id"])
        before = (row.payload, row.key_id, row.seal)
    if drift == "revoke":
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=state.manager.inspect(1)["grant_record_revision"],
        )
    elif drift == "native":
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
            elif drift == "recovery":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            else:
                db.execute(
                    update(Installation).values(
                        **{
                            "epoch": {"authority_epoch": identity()},
                            "enable": {"enabled": True, "status": "active"},
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
    with Session(state.engine) as db:
        row = db.get(Action, ticket["preparation_id"])
        assert (row.payload, row.key_id, row.seal) == before


def test_namespace_ticket_cannot_prepare_a_database_or_run_migrations(stopped):
    ticket = namespace_ticket(stopped)
    for model in (_RelationalPreparationTicket, _RelationalMigrationPreparationTicket):
        with pytest.raises(ValidationError):
            model.model_validate(ticket)
    with pytest.raises(ValueError, match="not database lifecycle"):
        prepared_lifecycle(ticket, SECRET)
    with pytest.raises(ValidationError):
        _RelationalNamespacePreparationTicket.model_validate(issue(stopped))
    with pytest.raises(ValueError, match="signature"):
        checkpoint(stopped, sign_metadata(SECRET, "preparation", ticket), "begin")
    malformed = sign_metadata(
        SECRET, "namespace_preparation", {**ticket, "path": "/foreign"}
    )
    with pytest.raises(ValidationError):
        _RelationalNamespacePreparationTicket.model_validate(malformed)


@ROOT_ONLY
def test_fresh_namespace_has_exact_owners_key_and_no_db_package_code_or_activation(
    absent_paths,
):
    state = absent_paths
    ticket = namespace_ticket(state)
    result = run(state, ticket)
    assert result["outcome"] == "namespace_created_not_started"
    assert state.key_path.read_bytes() == SECRET
    info = state.key_path.stat()
    assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 1201, 0o640)
    for name, uid in (("releases", 0), ("data", 1200), ("run", 1200)):
        path = state.instance / name
        info = path.stat()
        assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (
            uid,
            1201,
            0o750,
        )
        assert not list(path.iterdir())
    assert not state.database.exists()
    assert not (state.instance / "active.json").exists()
    assert not (state.instance / "relational.json").exists()
    assert not list(state.instance.glob(".activation-*.rollback"))
    witness = json.loads(state.marker.read_bytes())
    assert witness["phase"] == result["outcome"]
    assert witness["receipt"] == result
    assert SECRET.decode() not in state.marker.read_text()
    assert action(state, ticket)["state"] == "prepared"
    assert state.calls == [("stop", state.instance.name)]
    assert checkpoint(state, ticket, "finish", receipt=result) == {
        "state": result["outcome"],
        "historical": True,
    }
    with Session(state.engine) as db:
        assert not db.get(Installation, 1).enabled
    with pytest.raises(helper.RelationalPreparationError, match="already exists"):
        run(state, ticket)
    assert state.key_path.read_bytes() == SECRET


@ROOT_ONLY
@pytest.mark.parametrize(
    "collision", ["instance", "instance_link", "key", "key_link", "marker"]
)
def test_existing_namespace_key_or_marker_is_preserved_without_effects(
    absent_paths, collision
):
    state = absent_paths
    ticket = namespace_ticket(state)
    sentinel = state.helper_state / "sentinel"
    sentinel.write_bytes(b"do not replace")
    if collision == "instance":
        state.instance.mkdir()
        (state.instance / "preserved").write_bytes(b"preserved")
    elif collision == "instance_link":
        state.instance.symlink_to(state.helper_state, target_is_directory=True)
    elif collision == "key":
        state.key_path.write_bytes(b"existing secret")
    elif collision == "key_link":
        state.key_path.symlink_to(sentinel)
    else:
        state.marker.write_bytes(b"pending evidence")
    with pytest.raises(helper.RelationalPreparationError, match="already exists"):
        run(state, ticket)
    assert sentinel.read_bytes() == b"do not replace"
    assert not state.calls
    assert action(state, ticket)["state"] == "recorded"
    if collision == "key":
        assert state.key_path.read_bytes() == b"existing secret"
    elif collision == "marker":
        assert state.marker.read_bytes() == b"pending evidence"


@ROOT_ONLY
@pytest.mark.parametrize(
    "changes",
    [
        {"transport_secret": b"x" * 32},
        {"service_uid": 1202},
        {"service_gid": 1202},
        {"service_uid": True},
        {"coordinator_uid": 1203},
    ],
)
def test_changed_helper_dependencies_refuse_before_namespace_effects(
    absent_paths, changes
):
    with pytest.raises((ValueError, helper.RelationalPreparationError)):
        run(absent_paths, namespace_ticket(absent_paths), **changes)
    assert not absent_paths.instance.exists() and not absent_paths.key_path.exists()
    assert not absent_paths.calls


@ROOT_ONLY
@pytest.mark.parametrize(
    "problem",
    ["writable_root", "symlink_root", "overlap", "parent_link", "application_parent"],
)
def test_unprotected_or_aliased_roots_refuse_without_creation(absent_paths, problem):
    state = absent_paths
    ticket = namespace_ticket(state)
    changes = {}
    if problem == "writable_root":
        state.runtime.chmod(0o770)
    elif problem == "application_parent":
        os.chown(state.runtime.parent, 1200, 1201)
    elif problem == "symlink_root":
        link = state.helper_state.parent / "runtime-link"
        link.symlink_to(state.runtime, target_is_directory=True)
        changes["root"] = link
    elif problem == "parent_link":
        link = state.helper_state.parent / "parent-link"
        link.symlink_to(state.runtime.parent, target_is_directory=True)
        changes["root"] = link / state.runtime.name
    else:
        nested = state.runtime / "keys"
        nested.mkdir(mode=0o750)
        changes["key_root"] = nested
    with pytest.raises(ValueError):
        run(state, ticket, **changes)
    assert not state.instance.exists() and not state.key_path.exists()
    assert not state.calls


@ROOT_ONLY
def test_core_owned_search_only_parent_matches_installer_without_chmod(absent_paths):
    state = absent_paths
    ticket = namespace_ticket(state)
    # Keep the authority-key fixture's own ancestry unchanged: that store is
    # exercised by actual root here, while production callbacks run as Core.
    parent = state.runtime.parent / "core-owned-data"
    parent.mkdir(mode=0o710)
    for name, attribute in (
        ("runtime", "runtime"),
        ("keys", "transport_keys"),
        ("helper", "helper_state"),
    ):
        path = parent / name
        path.mkdir(mode=0o750)
        os.chown(path, 0, 1201)
        setattr(state, attribute, path)
    state.instance = state.runtime / ticket["instance_id"]
    state.key_path = state.transport_keys / (state.instance.name + ".key")
    state.marker = state.helper_state / (
        "relational-namespace-" + state.instance.name + ".json"
    )
    os.chown(parent, 1202, 1201)
    parent.chmod(0o710)
    result = run(state, ticket)
    assert result["outcome"] == "namespace_created_not_started"
    info = parent.stat()
    assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (1202, 1201, 0o710)
    assert state.key_path.read_bytes() == SECRET


@ROOT_ONLY
@pytest.mark.parametrize(
    "failure",
    [
        "key_write",
        "revoke",
        "key_drift",
        "unexpected_file",
        "finish_before_commit",
        "finish_after_commit",
    ],
)
def test_partial_creation_or_unknown_finish_preserves_and_blocks_replay(
    absent_paths, monkeypatch, failure
):
    state = absent_paths
    ticket = namespace_ticket(state)
    original = helper._exclusive_file

    def fail_key(path, *args):
        if path == state.key_path:
            raise OSError("key write failed")
        return original(path, *args)

    if failure == "key_write":
        monkeypatch.setattr(helper, "_exclusive_file", fail_key)

    def fail_checkpoint(*args, **kwargs):
        phase = args[1]
        if phase == "check":
            if failure == "revoke":
                state.manager.revoke(
                    1,
                    actor_token=state.token,
                    request_id=identity(),
                    expected_revision=state.manager.inspect(1)["grant_record_revision"],
                )
            elif failure == "key_drift":
                state.key_path.write_bytes(b"x" * 32)
            elif failure == "unexpected_file":
                (state.data / "unexpected").write_bytes(b"preserve")
        if phase == "finish" and failure == "finish_before_commit":
            raise OSError("finish was not delivered")
        result = checkpoint(state, *args, **kwargs)
        if phase == "finish" and failure == "finish_after_commit":
            raise OSError("lost committed finish response")
        return result

    with pytest.raises(helper.RelationalPreparationError, match="preserve evidence"):
        run(state, ticket, fail_checkpoint)
    assert state.marker.is_file()
    assert state.instance.is_dir()
    assert state.calls == [("stop", state.instance.name)]
    assert not state.database.exists() and not (state.instance / "active.json").exists()
    assert action(state, ticket)["state"] == (
        "prepared" if failure == "finish_after_commit" else "execution_unconfirmed"
    )
    with pytest.raises(ApplicationActivationError, match="unfinished rollback"):
        _require_no_pending_rollback(state.instance)
    before = state.key_path.read_bytes() if state.key_path.exists() else None
    with pytest.raises(helper.RelationalPreparationError, match="already exists"):
        run(state, ticket)
    assert (state.key_path.read_bytes() if state.key_path.exists() else None) == before
    assert state.calls == [("stop", state.instance.name)]


@ROOT_ONLY
def test_stop_or_lost_begin_ack_produces_no_filesystem_effects(absent_paths):
    state = absent_paths
    ticket = namespace_ticket(state)

    def lost_begin(*args, **kwargs):
        result = checkpoint(state, *args, **kwargs)
        if args[1] == "begin":
            raise OSError("lost begin ACK")
        return result

    with pytest.raises(OSError, match="lost begin"):
        run(state, ticket, lost_begin)
    assert (
        not state.instance.exists()
        and not state.key_path.exists()
        and not state.marker.exists()
    )
    assert action(state, ticket)["state"] == "execution_unconfirmed"
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        run(state, ticket)
    assert len(state.calls) == 1


@ROOT_ONLY
def test_unconfirmed_stop_does_not_consume_ticket_or_create_state(
    absent_paths, monkeypatch
):
    state = absent_paths
    ticket = namespace_ticket(state)

    def fail_stop(_identifier):
        raise OSError("stop not confirmed")

    monkeypatch.setattr(state.supervisor, "stop", fail_stop)
    with pytest.raises(OSError, match="stop not confirmed"):
        run(state, ticket)
    assert action(state, ticket)["state"] == "recorded"
    assert (
        not state.instance.exists()
        and not state.key_path.exists()
        and not state.marker.exists()
    )


@ROOT_ONLY
def test_actual_nonroot_process_cannot_create_namespace(absent_paths):
    state = absent_paths
    ticket = namespace_ticket(state)
    child = os.fork()
    if child == 0:
        try:
            os.setgroups([])
            os.setgid(1201)
            os.setuid(1200)
            try:
                run(state, ticket)
            except helper.RelationalPreparationError as exc:
                os._exit(0 if "helper unavailable" in str(exc) else 2)
            os._exit(3)
        except BaseException:
            os._exit(4)
    _, status = os.waitpid(child, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    assert (
        not state.instance.exists() and not state.key_path.exists() and not state.calls
    )
    assert action(state, ticket)["state"] == "recorded"


@ROOT_ONLY
@pytest.mark.parametrize("kind", ["release", "runtime"])
def test_shared_mutation_locks_exclude_overlapping_namespace_work(absent_paths, kind):
    state = absent_paths
    ticket = namespace_ticket(state)
    lock = (
        locks._release_lock()
        if kind == "release"
        else locks._runtime_lock(state.helper_state)
    )
    with lock:
        with pytest.raises(BlockingIOError):
            run(state, ticket)
    assert (
        not state.instance.exists() and not state.key_path.exists() and not state.calls
    )


@ROOT_ONLY
def test_namespace_feeds_existing_real_nonroot_migration_worker(absent_paths, tmp_path):
    import sqlite3

    from backend.tests.test_application_relational_migrations import (
        candidate,
        migration_ticket,
        script,
    )
    from three_mm_runtime.application_relational_preparation import (
        prepare_migrated_relational_database,
    )
    from three_mm_runtime.application_relational_session import _prepared

    state = absent_paths
    for directory in (tmp_path, tmp_path.parent, tmp_path.parent.parent):
        directory.chmod(directory.stat().st_mode | 0o111)
    candidate(state, script())
    ticket = namespace_ticket(state)
    run(state, ticket)
    assert not state.database.exists()
    migration = migration_ticket(state)
    result = prepare_migrated_relational_database(
        state.archive,
        migration,
        configuration=state.configuration,
        root=state.runtime,
        key_root=state.transport_keys,
        state_root=state.helper_state,
        service_uid=1200,
        service_gid=1201,
        supervisor=state.supervisor,
        checkpoint=lambda *a, **kw: checkpoint(state, *a, **kw),
    )
    assert result["outcome"] == "prepared_not_started"
    assert _prepared(state.instance, SECRET) == prepared_lifecycle(migration, SECRET)
    with sqlite3.connect(state.database) as db:
        assert db.execute(
            "SELECT revision FROM three_mm_schema_migrations"
        ).fetchall() == [("0001",), ("0002",)]
        assert db.execute("SELECT migrated FROM business").fetchall() == []
    assert state.database.stat().st_uid == 1200
    assert not list(state.instance.glob(".activation-*.rollback"))
    assert len(state.calls) == 2
    with Session(state.engine) as db:
        assert not db.get(Installation, 1).enabled
