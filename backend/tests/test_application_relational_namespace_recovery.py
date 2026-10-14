"""Fresh Core human consent + actual root empty-bootstrap recovery, no SQL.

Only disposable paths/keys. No live grants, startup or production changes.
"""

import hashlib
import json
import os
import stat

import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.session import UserSession
from backend.services import application_authority_management as authority
from backend.services import application_relational_namespace_recovery as coordinator
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_policy_reviews import PolicyReviewStoreError
from backend.tests.test_application_relational_namespace import (
    ROOT_ONLY,
    SECRET,
    absent_paths,
    action,
    checkpoint,
    identity,
    managed_installed,
    namespace_ticket,
)
from backend.tests.test_application_relational_namespace import run as create
from backend.tests.test_application_relational_namespace import (
    source_installed,
    source_subject,
    stopped,
)
from three_mm_application_sdk.relational_wire import (
    _RelationalNamespacePreparationTicket,
    canonical,
    prepared_lifecycle,
    sign_metadata,
)
from three_mm_runtime import application_lifecycle as locks
from three_mm_runtime import application_relational_namespace as creation
from three_mm_runtime import application_relational_namespace_recovery as helper
from three_mm_runtime.application_activation import (
    ApplicationActivationError,
    _require_no_pending_rollback,
)

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Real POSIX bootstrap recovery"
)


def ticket(state, source, **changes):
    return coordinator.issue_namespace_recovery(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "source_preparation_id": source["preparation_id"],
            "expected_grant_record_revision": state.manager.inspect(1)[
                "grant_record_revision"
            ],
            "choice": "confirm",
            "confirm_empty_bootstrap_reviewed": True,
            "transport_secret": SECRET,
            **changes,
        },
    )


def check(state, value, phase, **kwargs):
    return coordinator.namespace_recovery_checkpoint(
        state.manager,
        1,
        value,
        phase,
        actor_token=state.token,
        transport_secret=SECRET,
        **kwargs,
    )


def recover(state, value, source, callback=None, **changes):
    return helper.reconcile_empty_relational_namespace(
        state.archive,
        value,
        source,
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
            "checkpoint": callback or (lambda *a, **kw: check(state, *a, **kw)),
            **changes,
        },
    )


def interrupted(state, monkeypatch, failure="finish_before"):
    source = namespace_ticket(state)
    original = creation._exclusive_file

    def failed_key(path, content, mode, gid):
        if path == state.key_path:
            if failure == "partial_key":
                original(path, content[:8], mode, gid)
            raise OSError("injected key failure")
        return original(path, content, mode, gid)

    def failed_checkpoint(*args, **kwargs):
        if args[1] == "finish" and failure == "finish_before":
            raise OSError("finish not delivered")
        result = checkpoint(state, *args, **kwargs)
        if args[1] == "finish" and failure == "finish_after":
            raise OSError("finish response lost")
        return result

    with monkeypatch.context() as patch:
        if failure in {"partial_key", "missing_key"}:
            patch.setattr(creation, "_exclusive_file", failed_key)
        with pytest.raises(creation.RelationalPreparationError):
            create(state, source, failed_checkpoint)
    return source


@pytest.mark.parametrize(
    "problem",
    ["confirmation", "choice", "actor", "source", "grant", "not_started", "key"],
)
def test_recovery_requires_explicit_current_local_authority(stopped, problem):
    state = stopped
    source = namespace_ticket(state)
    if problem != "not_started":
        checkpoint(state, source, "begin")
    changes = {
        "confirmation": {"confirm_empty_bootstrap_reviewed": False},
        "choice": {"choice": "retry"},
        "actor": {"actor_token": state.user_token},
        "source": {"source_preparation_id": identity()},
        "grant": {"expected_grant_record_revision": identity()},
        "key": {"transport_secret": b"x" * 32},
        "not_started": {},
    }[problem]
    with pytest.raises(authority.AuthorityManagementError):
        ticket(state, source, **changes)
    assert "namespace_recovery_id" not in action(state, source)["data"]


def test_fresh_choice_supersedes_creation_and_older_recovery_without_forging_outcome(
    stopped,
):
    state = stopped
    source = namespace_ticket(state)
    checkpoint(state, source, "begin")
    first = ticket(state, source)
    assert action(state, source)["state"] == "execution_unconfirmed"
    assert "receipt" not in action(state, source)["data"]
    with pytest.raises(authority.AuthorityManagementError, match="superseded"):
        checkpoint(state, source, "check")
    check(state, first, "begin")
    second = ticket(state, source, choice="quarantine")
    with pytest.raises(authority.AuthorityManagementError, match="superseded"):
        check(state, first, "check")
    assert check(state, second, "authorize") == {"state": "authorized_not_started"}
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        ticket(state, source, request_id=second["preparation_id"], choice="quarantine")


def test_recovery_ticket_is_not_creation_sql_or_migration_authority(stopped):
    source = namespace_ticket(stopped)
    checkpoint(stopped, source, "begin")
    value = ticket(stopped, source)
    with pytest.raises(ValidationError):
        _RelationalNamespacePreparationTicket.model_validate(value)
    with pytest.raises(ValidationError):
        prepared_lifecycle(value, SECRET)
    with pytest.raises(ValueError, match="signature"):
        check(stopped, sign_metadata(SECRET, "namespace_preparation", value), "begin")


@ROOT_ONLY
@pytest.mark.parametrize("failure", ["finish_before", "finish_after"])
def test_complete_creation_can_be_confirmed_without_replay_rekey_or_data_writes(
    absent_paths, monkeypatch, failure
):
    state = absent_paths
    source = interrupted(state, monkeypatch, failure)
    original_witness = state.marker.read_bytes()
    old_state = action(state, source)["state"]
    value = ticket(state, source)
    result = recover(state, value, source)
    assert result["outcome"] == "namespace_confirmed_not_started"
    assert state.key_path.read_bytes() == SECRET
    assert state.marker.read_bytes() == original_witness
    assert action(state, source)["state"] == old_state
    assert action(state, value)["state"] == "confirmed"
    assert not state.database.exists()
    assert not (state.instance / "active.json").exists()
    assert not list(state.instance.glob(".activation-*.rollback"))
    assert len(list(state.instance.glob(".namespace-evidence-*"))) == 2
    with Session(state.engine) as db:
        assert not db.get(Installation, 1).enabled
    assert check(state, value, "finish", receipt=result) == {
        "state": result["outcome"],
        "historical": True,
    }
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        recover(state, value, source)


@ROOT_ONLY
@pytest.mark.parametrize(
    "failure", ["partial_key", "missing_key", "finish_before", "witness_only"]
)
def test_known_empty_partial_bootstrap_is_quarantined_preserved_then_explicit_fresh_setup(
    absent_paths, monkeypatch, failure
):
    state = absent_paths
    if failure == "witness_only":
        source = namespace_ticket(state)
        checkpoint(state, source, "begin")
        creation._exclusive_file(
            state.marker, canonical(helper._creation_evidence(source)), 0o600, 0
        )
    else:
        source = interrupted(state, monkeypatch, failure)
    before = state.key_path.read_bytes() if state.key_path.exists() else None
    witness = state.marker.read_bytes()
    value = ticket(state, source, choice="quarantine")
    result = recover(state, value, source)
    assert result["outcome"] == "namespace_quarantined_not_started"
    suffix = state.instance.name + "-" + source["preparation_id"]
    archive = state.transport_keys / (".namespace-evidence-" + suffix + ".key")
    assert (archive.read_bytes() if archive.exists() else None) == before
    if archive.exists():
        info = archive.stat()
        assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 0, 0o600)
    archived_instance = state.runtime / (".namespace-evidence-" + suffix)
    if archived_instance.exists():
        info = archived_instance.stat()
        assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 0, 0o700)
    assert (
        state.helper_state / (".namespace-evidence-" + suffix + ".json")
    ).read_bytes() == witness
    assert (
        not state.instance.exists()
        and not state.key_path.exists()
        and not state.marker.exists()
    )
    assert action(state, source)["state"] == "execution_unconfirmed"
    fresh_secret = b"n" * 32
    fresh = namespace_ticket(state, transport_secret=fresh_secret)
    from backend.services.application_relational_lifecycle import preparation_checkpoint

    create(
        state,
        fresh,
        transport_secret=fresh_secret,
        callback=lambda *a, **kw: preparation_checkpoint(
            state.manager,
            1,
            *a,
            actor_token=state.token,
            transport_secret=fresh_secret,
            **kw,
        ),
    )
    assert state.key_path.read_bytes() == fresh_secret
    assert (archive.read_bytes() if archive.exists() else None) == before


@ROOT_ONLY
@pytest.mark.parametrize(
    "problem",
    [
        "database",
        "business_file",
        "wheel",
        "active",
        "link",
        "foreign_key",
        "wrong_witness",
        "unknown_marker",
        "hardlink",
        "writable_key",
        "missing_dir",
        "foreign_group",
        "unknown_directory_mode",
    ],
)
def test_reconciliation_refuses_unknown_or_nonempty_state_without_replacing_it(
    absent_paths, monkeypatch, problem
):
    state = absent_paths
    source = interrupted(state, monkeypatch)
    if problem == "database":
        state.database.write_bytes(b"preserve database")
    elif problem == "business_file":
        (state.data / "business").write_bytes(b"preserve")
    elif problem == "wheel":
        (state.instance / "releases" / "candidate").mkdir()
    elif problem == "active":
        (state.instance / "active.json").write_bytes(b"preserve")
    elif problem == "link":
        (state.data / "outside").symlink_to(state.archive)
    elif problem == "foreign_key":
        state.key_path.write_bytes(b"x" * 32)
    elif problem == "wrong_witness":
        state.marker.write_bytes(b"{}")
    elif problem == "unknown_marker":
        (state.instance / (".activation-" + identity() + ".rollback")).mkdir()
    elif problem == "hardlink":
        os.link(state.key_path, state.transport_keys / "foreign")
    elif problem == "writable_key":
        state.key_path.chmod(0o660)
    elif problem == "foreign_group":
        os.chown(state.instance, 0, 1299)
    elif problem == "unknown_directory_mode":
        (state.instance / "releases").chmod(0o755)
    else:
        (state.instance / "run").rmdir()
    key = state.key_path.read_bytes()
    witness = state.marker.read_bytes()
    for choice in (
        ("confirm", "quarantine") if problem != "missing_dir" else ("confirm",)
    ):
        value = ticket(state, source, choice=choice)
        with pytest.raises((ValueError, helper.RelationalPreparationError)):
            recover(state, value, source)
        assert action(state, value)["state"] == "recorded"
        assert state.instance.exists()
        assert (
            state.key_path.read_bytes() == key and state.marker.read_bytes() == witness
        )


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
def test_recovery_checkpoint_rechecks_all_current_authority(
    stopped, monkeypatch, drift
):
    state = stopped
    source = namespace_ticket(state)
    checkpoint(state, source, "begin")
    value = ticket(state, source)
    check(state, value, "begin")
    with Session(state.engine) as db:
        row = db.get(Action, value["preparation_id"])
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
                    value["boot_id"]
                    if drift == "deadline"
                    else "00000000-0000-0000-0000-000000000001"
                ),
                value["deadline_ms"] if drift == "deadline" else value["issued_at_ms"],
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
        check(state, value, "check")
    with Session(state.engine) as db:
        row = db.get(Action, value["preparation_id"])
        assert (row.payload, row.key_id, row.seal) == before


@ROOT_ONLY
@pytest.mark.parametrize("failure", ["before", "after"])
@pytest.mark.parametrize("choice", ["confirm", "quarantine"])
def test_lost_finish_requires_fresh_human_ticket_and_preserves_blocking_evidence(
    absent_paths, monkeypatch, failure, choice
):
    state = absent_paths
    source = interrupted(state, monkeypatch)
    value = ticket(state, source, choice=choice)

    def lost(*a, **kw):
        if a[1] == "finish" and failure == "before":
            raise OSError("request lost")
        result = check(state, *a, **kw)
        if a[1] == "finish" and failure == "after":
            raise OSError("response lost")
        return result

    with pytest.raises(helper.RelationalPreparationError, match="evidence retained"):
        recover(state, value, source, lost)
    assert state.marker.exists()
    if choice == "confirm":
        with pytest.raises(ApplicationActivationError):
            _require_no_pending_rollback(state.instance)
    with pytest.raises((authority.AuthorityManagementError, ValueError)):
        recover(state, value, source)
    fresh = ticket(state, source, choice=choice)
    assert recover(state, fresh, source)["outcome"] == (
        "namespace_confirmed_not_started"
        if choice == "confirm"
        else "namespace_quarantined_not_started"
    )
    assert action(state, source)["state"] == "execution_unconfirmed"


@ROOT_ONLY
def test_partial_quarantine_move_is_reconciled_only_by_new_choice(
    absent_paths, monkeypatch
):
    state = absent_paths
    source = interrupted(state, monkeypatch)
    value = ticket(state, source, choice="quarantine")
    original = helper._move

    def fail_key(path, archive):
        if path == state.key_path:
            raise OSError("injected key move failure")
        return original(path, archive)

    with monkeypatch.context() as patch:
        patch.setattr(helper, "_move", fail_key)
        with pytest.raises(helper.RelationalPreparationError):
            recover(state, value, source)
    assert state.marker.exists() and state.key_path.read_bytes() == SECRET
    assert not state.instance.exists()
    fresh = ticket(state, source, choice="quarantine")
    recover(state, fresh, source)
    assert not state.key_path.exists() and not state.marker.exists()


@ROOT_ONLY
@pytest.mark.parametrize("kind", ["release", "runtime"])
def test_recovery_uses_existing_shared_mutation_locks(absent_paths, monkeypatch, kind):
    state = absent_paths
    source = interrupted(state, monkeypatch)
    value = ticket(state, source)
    lock = (
        locks._release_lock()
        if kind == "release"
        else locks._runtime_lock(state.helper_state)
    )
    with lock:
        with pytest.raises(BlockingIOError):
            recover(state, value, source)
    assert action(state, value)["state"] == "recorded"


@ROOT_ONLY
def test_actual_nonroot_process_cannot_reconcile_namespace(absent_paths, monkeypatch):
    state = absent_paths
    source = interrupted(state, monkeypatch)
    value = ticket(state, source)
    child = os.fork()
    if child == 0:
        try:
            os.setgroups([])
            os.setgid(1201)
            os.setuid(1200)
            try:
                recover(state, value, source)
            except helper.RelationalPreparationError:
                os._exit(0)
            os._exit(2)
        except BaseException:
            os._exit(3)
    _, status = os.waitpid(child, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    assert action(state, value)["state"] == "recorded"


@ROOT_ONLY
def test_checkpoint_budget_refuses_before_consuming_or_creating_another_marker(
    absent_paths, monkeypatch
):
    state = absent_paths
    source = interrupted(state, monkeypatch)
    monkeypatch.setattr(helper, "MAX_MARKERS", 1)
    value = ticket(state, source)
    with pytest.raises(ValueError, match="budget exceeded"):
        recover(state, value, source)
    assert len(list(state.instance.glob(".activation-*.rollback"))) == 1
    assert action(state, value)["state"] == "recorded"
