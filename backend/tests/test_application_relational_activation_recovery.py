"""Fresh stop-only consent + actual disposable non-root crash recovery.

No live units/accounts/releases, no fabricated grants, no migration replay.
"""

import hashlib
import json
import os

import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ModulePackage
from backend.db.session import UserSession
from backend.services import application_authority_management as authority
from backend.services import application_relational_activation_recovery as coordinator
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_policy_reviews import PolicyReviewStoreError
from backend.tests.test_application_relational_activation import (
    checkpoint as start_checkpoint,
)
from backend.tests.test_application_relational_activation import issue as issue_start
from backend.tests.test_application_relational_activation import (
    journal,
    migratable,
    physical,
    prepared,
    prepared_paths,
)
from backend.tests.test_application_relational_activation import (
    receipt as start_receipt,
)
from backend.tests.test_application_relational_activation import (
    start,
    tmp_path,
)
from backend.tests.test_application_relational_preparation import (
    ROOT_ONLY,
    SECRET,
    apply,
    identity,
    managed_installed,
    native,
    source_installed,
    source_subject,
    stopped,
)
from three_mm_application_sdk import ApplicationStorage
from three_mm_application_sdk.relational_wire import (
    _preparation_ticket,
    _RelationalActivationRecoveryResult,
    _RelationalActivationRecoveryTicket,
    _RelationalActivationTicket,
    canonical,
    sign_metadata,
)
from three_mm_runtime import application_relational_activation as start_helper
from three_mm_runtime import application_relational_activation_recovery as helper

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Actual POSIX clock/principals"
)


def issue(state, source, **changes):
    return coordinator.issue_activation_recovery(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "source_activation_id": source["preparation_id"],
            "expected_activation_revision": journal(state, source)["revision"],
            "confirm_stop_preserve_prepared_state": True,
            "transport_secret": SECRET,
            "service_uid": 1200,
            "service_gid": 1201,
            "coordinator_uid": 1202,
            **changes,
        },
    )


def checkpoint(state, ticket, phase, **changes):
    return coordinator.activation_recovery_checkpoint(
        state.manager,
        1,
        ticket,
        phase,
        **{
            "actor_token": state.token,
            "transport_secret": SECRET,
            **changes,
        },
    )


def receipt(ticket, **changes):
    return sign_metadata(
        SECRET,
        "activation_recovery_result",
        {
            "version": 1,
            "preparation_id": ticket["preparation_id"],
            "ticket_sha256": hashlib.sha256(canonical(ticket)).hexdigest(),
            "source_activation_id": ticket["source_activation_id"],
            "lifecycle_sha256": ticket["prepared_lifecycle_sha256"],
            "witness_sha256": "a" * 64,
            "outcome": "stopped_review_required",
            **changes,
        },
    )


def recover(state, ticket, **changes):
    return helper.reconcile_interrupted_relational_start(
        state.archive,
        ticket,
        **{
            "configuration": state.configuration,
            "root": state.runtime,
            "key_root": state.transport_keys,
            "state_root": state.helper_state,
            "service_uid": 1200,
            "service_gid": 1201,
            "coordinator_uid": 1202,
            "checkpoint": lambda *a, **kw: checkpoint(state, *a, **kw),
            "supervisor": state.actual_supervisor,
            **changes,
        },
    )


@pytest.mark.parametrize(
    "source_state",
    ["recorded", "execution_unconfirmed", "activation_unconfirmed", "activated"],
)
def test_fresh_recovery_fences_old_start_preserves_history_and_grant(
    prepared, source_state
):
    state = prepared
    source = issue_start(state, state.source)
    if source_state != "recorded":
        start_checkpoint(state, source, "begin")
        if source_state == "activated":
            start_checkpoint(state, source, "finish", receipt=start_receipt(source))
        elif source_state == "activation_unconfirmed":
            start_checkpoint(state, source, "abort")
    before = journal(state, source)
    with Session(state.engine) as db:
        grant = db.get(Grant, 1).payload
        epoch = db.get(Installation, 1).authority_epoch
    ticket = issue(state, source)
    after = journal(state, source)
    assert after["state"] == before["state"] == source_state
    assert after["data"]["result"] == before["data"]["result"]
    assert after["data"].get("receipt") == before["data"].get("receipt")
    assert after["data"]["activation_recovery_id"] == ticket["preparation_id"]
    with Session(state.engine) as db:
        row = db.get(Installation, 1)
        assert not row.enabled and row.status == "disabled"
        assert row.authority_mode == "review_required" and row.authority_epoch != epoch
        assert db.get(Grant, 1).payload == grant
    for phase in ("authorize", "begin", "check", "abort", "finish"):
        with pytest.raises(authority.AuthorityManagementError):
            start_checkpoint(
                state,
                source,
                phase,
                **({"receipt": start_receipt(source)} if phase == "finish" else {}),
            )
    assert checkpoint(state, ticket, "authorize") == {"state": "authorized_stop_only"}
    checkpoint(state, ticket, "begin")
    checkpoint(state, ticket, "check")
    result = receipt(ticket)
    assert checkpoint(state, ticket, "finish", receipt=result) == {
        "state": "stopped_review_required"
    }
    assert checkpoint(state, ticket, "finish", receipt=result)["historical"] is True
    assert journal(state, ticket)["state"] == "confirmed"
    with pytest.raises(authority.AuthorityManagementError):
        issue(
            state,
            source,
            request_id=ticket["preparation_id"],
            expected_activation_revision=before["revision"],
        )
    with pytest.raises(authority.AuthorityManagementError):
        checkpoint(state, ticket, "begin")


@pytest.mark.parametrize("revoked", ["grant", "native"])
def test_revoked_trust_or_permissions_do_not_require_regrant_to_stop(prepared, revoked):
    state = prepared
    source = issue_start(state, state.source)
    start_checkpoint(state, source, "begin")
    if revoked == "grant":
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=source["grant_record_revision"],
        )
    else:
        proof = state.manager.inspect(1)["native_reviews"][0]
        state.manager.revoke_native_review(
            1,
            actor_token=state.token,
            request_id=identity(),
            native_review_id=proof["native_review_id"],
            expected_revision=proof["revision"],
        )
    with Session(state.engine) as db:
        grant = db.get(Grant, 1).payload
    ticket = issue(state, source)
    checkpoint(state, ticket, "begin")
    checkpoint(state, ticket, "finish", receipt=receipt(ticket))
    with state.keys.locked() as key, Session(state.engine) as db:
        assert db.get(Grant, 1).payload == grant
        with pytest.raises(authority.AuthorityManagementError):
            state.manager._require_grant(
                db, key, 1, state.manager._prepare(1), "storage:relational_read"
            )


@pytest.mark.parametrize(
    "change",
    [
        {"confirm_stop_preserve_prepared_state": False},
        {"confirm_stop_preserve_prepared_state": 1},
        {"actor_token": "invalid"},
        {"expected_activation_revision": "f" * 32},
        {"transport_secret": b"x" * 32},
        {"service_uid": 0},
        {"coordinator_uid": 1200},
        {"source_activation_id": "f" * 32},
    ],
)
def test_bad_recovery_consent_is_atomic(prepared, change):
    source = issue_start(prepared, prepared.source)
    before = journal(prepared, source)
    with Session(prepared.engine) as db:
        epoch = db.get(Installation, 1).authority_epoch
    with pytest.raises((authority.AuthorityManagementError, ValueError, KeyError)):
        issue(prepared, source, **change)
    assert journal(prepared, source) == before
    with Session(prepared.engine) as db:
        assert db.get(Installation, 1).authority_epoch == epoch


def test_failed_recovery_write_rolls_back_fence_and_reservation(prepared, monkeypatch):
    source = issue_start(prepared, prepared.source)
    before = journal(prepared, source)
    with Session(prepared.engine) as db:
        epoch = db.get(Installation, 1).authority_epoch
    original = authority._save

    def fail(db, key, kind, row, value):
        if value["data"].get("operation") == coordinator.OPERATION:
            raise OSError("Durable recovery issuance failed")
        return original(db, key, kind, row, value)

    with monkeypatch.context() as patch:
        patch.setattr(authority, "_save", fail)
        with pytest.raises(authority.AuthorityManagementError):
            issue(prepared, source)
    assert journal(prepared, source) == before
    with Session(prepared.engine) as db:
        assert db.get(Installation, 1).authority_epoch == epoch


@pytest.mark.parametrize("drift", ["version", "status", "incarnation"])
def test_artifact_pin_is_rechecked_under_final_metadata_transaction(
    prepared, monkeypatch, drift
):
    state = prepared
    source = issue_start(state, state.source)
    before = journal(state, source)
    original = state.manager._prepare

    def stale(identifier):
        candidate = original(identifier)
        with state.engine.begin() as db:
            if drift == "version":
                db.execute(update(ModulePackage).values(version="99.0.0"))
            else:
                db.execute(
                    update(Installation).values(
                        **{
                            "status": {"status": "failed"},
                            "incarnation": {"authority_incarnation": identity()},
                        }[drift]
                    )
                )
        return candidate

    monkeypatch.setattr(state.manager, "_prepare", stale)
    with pytest.raises(authority.AuthorityManagementError):
        issue(state, source)
    assert journal(state, source) == before


@pytest.mark.parametrize(
    "drift",
    [
        "actor",
        "epoch",
        "generation",
        "config",
        "source_seal",
        "superseded",
        "new_grant",
        "expired",
        "boot",
        "enabled",
    ],
)
def test_each_recovery_phase_rechecks_current_exact_authority(
    prepared, drift, monkeypatch
):
    state = prepared
    source = issue_start(state, state.source)
    ticket = issue(state, source)
    checkpoint(state, ticket, "begin")
    if drift == "superseded":
        fresh = issue(state, source)
        assert fresh["authority_epoch"] != ticket["authority_epoch"]
    elif drift == "new_grant":
        apply(state, state.native_id)
    elif drift in {"expired", "boot"}:
        monkeypatch.setattr(
            authority,
            "_clock",
            lambda: (
                (
                    "f" * 8
                    + "-"
                    + "f" * 4
                    + "-"
                    + "f" * 4
                    + "-"
                    + "f" * 4
                    + "-"
                    + "f" * 12
                    if drift == "boot"
                    else ticket["boot_id"]
                ),
                ticket["deadline_ms"] if drift == "expired" else ticket["issued_at_ms"],
            ),
        )
    else:
        with state.engine.begin() as db:
            if drift == "actor":
                db.execute(update(UserSession).values(is_active=False))
            elif drift == "generation":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            elif drift == "source_seal":
                db.execute(
                    update(Action)
                    .where(Action.request_id == source["preparation_id"])
                    .values(seal="0" * 64)
                )
            else:
                db.execute(
                    update(Installation).values(
                        **{
                            "epoch": {"authority_epoch": identity()},
                            "config": {
                                "configuration": {
                                    **state.configuration,
                                    "PRIVATE_NOTE": "changed",
                                }
                            },
                            "enabled": {"enabled": True, "status": "active"},
                        }[drift]
                    )
                )
    for phase in ("check", "finish"):
        with pytest.raises(
            (
                authority.AuthorityManagementError,
                AuthorityReviewKeyError,
                PolicyReviewStoreError,
                ValueError,
            )
        ):
            checkpoint(
                state,
                ticket,
                phase,
                **({"receipt": receipt(ticket)} if phase == "finish" else {}),
            )
    with Session(state.engine) as db:
        assert (
            json.loads(db.get(Action, ticket["preparation_id"]).payload)["state"]
            == "execution_unconfirmed"
        )


def test_recovery_purpose_cannot_be_used_as_start_preparation_or_sql(prepared):
    source = issue_start(prepared, prepared.source)
    ticket = issue(prepared, source)
    for model in (_RelationalActivationTicket,):
        with pytest.raises(ValidationError):
            model.model_validate(ticket)
    with pytest.raises(ValidationError):
        _preparation_ticket(ticket)
    with pytest.raises(ValidationError):
        _RelationalActivationRecoveryTicket.model_validate(
            dict(ticket, database_path="/foreign")
        )
    checkpoint(prepared, ticket, "begin")
    for changes in (
        {"preparation_id": identity()},
        {"source_activation_id": identity()},
        {"lifecycle_sha256": "0" * 64},
        {"ticket_sha256": "0" * 64},
    ):
        with pytest.raises(authority.AuthorityManagementError):
            checkpoint(prepared, ticket, "finish", receipt=receipt(ticket, **changes))
    with pytest.raises(ValidationError):
        _RelationalActivationRecoveryResult.model_validate(
            receipt(ticket, outcome="active_review_required")
        )


def test_expired_old_start_can_be_stopped_only_with_fresh_budget(prepared, monkeypatch):
    source = issue_start(prepared, prepared.source)
    boot = "f" * 8 + "-" + "f" * 4 + "-" + "f" * 4 + "-" + "f" * 4 + "-" + "f" * 12
    monkeypatch.setattr(authority, "_clock", lambda: (boot, source["deadline_ms"] + 1))
    ticket = issue(prepared, source)
    assert ticket["boot_id"] != source["boot_id"]
    assert ticket["issued_at_ms"] > source["deadline_ms"]
    assert journal(prepared, source)["data"]["result"]["ticket"] == source
    checkpoint(prepared, ticket, "begin")
    checkpoint(prepared, ticket, "finish", receipt=receipt(ticket))
    with pytest.raises(authority.AuthorityManagementError):
        start_checkpoint(prepared, source, "begin")


class Crash(BaseException):
    """Simulates coordinator disappearance without running its exception handler."""


def crash_start(state, phase):
    source = issue_start(state, state.source)

    def crash(ticket, at, **kw):
        result = start_checkpoint(state, ticket, at, **kw)
        if at == phase:
            raise Crash()
        return result

    with pytest.raises(Crash):
        start(state, source, checkpoint=crash)
    return source


def preserved(state):
    return {
        path: path.read_bytes()
        for path in (
            state.database,
            state.instance / "relational.json",
            state.instance / "active.json",
            state.data / "migration-imported",
            state.transport_keys / (state.instance.name + ".key"),
        )
    }


@ROOT_ONLY
@pytest.mark.parametrize("phase", ["issue", "begin", "check", "finish"])
def test_real_interrupted_start_recovery_preserves_prepared_state_and_never_starts(
    physical, monkeypatch, phase
):
    state = physical
    before = preserved(state)
    source = (
        issue_start(state, state.source)
        if phase == "issue"
        else crash_start(state, phase)
    )
    source_state = journal(state, source)["state"]
    marker = state.helper_state / (
        "relational-activation-" + state.instance.name + ".json"
    )
    witness = marker.read_bytes() if marker.exists() else None
    starts = state.actual_supervisor.starts
    with Session(state.engine) as db:
        grant = db.get(Grant, 1).payload
    ticket = issue(state, source)
    monkeypatch.setattr(
        ApplicationStorage,
        "migrate",
        lambda *a: pytest.fail("Recovery reran migrations"),
    )
    result = recover(state, ticket)
    assert result["outcome"] == "stopped_review_required"
    assert state.actual_supervisor.starts == starts
    assert state.actual_supervisor.process is None
    assert preserved(state) == before
    assert (marker.read_bytes() if marker.exists() else None) == witness
    assert journal(state, source)["state"] == source_state
    assert journal(state, ticket)["state"] == "confirmed"
    with Session(state.engine) as db:
        row = db.get(Installation, 1)
        assert (
            not row.enabled
            and row.status == "disabled"
            and row.authority_mode == "review_required"
        )
        assert db.get(Grant, 1).payload == grant
    evidence = next(state.helper_state.glob("relational-start-recovery-*.json"))
    assert evidence.stat().st_mode & 0o777 == 0o600
    assert (
        SECRET.hex() not in evidence.read_text()
        and state.token not in evidence.read_text()
    )
    with pytest.raises(helper.RelationalActivationRecoveryError):
        recover(state, ticket)


@ROOT_ONLY
@pytest.mark.parametrize("lost_phase", ["begin", "finish"])
def test_lost_recovery_ack_retains_evidence_and_requires_new_human_ticket(
    physical, lost_phase
):
    state = physical
    source = crash_start(state, "check")
    before = preserved(state)
    ticket = issue(state, source)

    def lost(ticket, phase, **kw):
        result = checkpoint(state, ticket, phase, **kw)
        if phase == lost_phase:
            raise OSError("ACK lost AFTER durable commit")
        return result

    with pytest.raises(helper.RelationalActivationRecoveryError, match="unconfirmed"):
        recover(state, ticket, checkpoint=lost)
    evidence = next(state.helper_state.glob("relational-start-recovery-*.json"))
    saved = evidence.read_bytes()
    assert journal(state, ticket)["state"] == (
        "confirmed" if lost_phase == "finish" else "execution_unconfirmed"
    )
    with pytest.raises(helper.RelationalActivationRecoveryError):
        recover(state, ticket)
    fresh = issue(state, source)
    recover(state, fresh)
    assert evidence.read_bytes() == saved
    assert preserved(state) == before
    assert (
        state.actual_supervisor.process is None and state.actual_supervisor.starts == 1
    )
    with pytest.raises(authority.AuthorityManagementError):
        checkpoint(state, ticket, "finish", receipt=receipt(ticket))


@ROOT_ONLY
def test_unknown_stop_does_not_confirm_or_erase_evidence(physical, monkeypatch):
    state = physical
    source = crash_start(state, "check")
    ticket = issue(state, source)
    with monkeypatch.context() as patch:
        patch.setattr(
            state.actual_supervisor,
            "recover_disabled",
            lambda *a: (_ for _ in ()).throw(OSError("Stop unconfirmed")),
        )
        with pytest.raises(
            helper.RelationalActivationRecoveryError, match="unconfirmed"
        ):
            recover(state, ticket)
    assert state.actual_supervisor.process is not None
    assert journal(state, ticket)["state"] == "execution_unconfirmed"
    assert next(state.helper_state.glob("relational-start-recovery-*.json")).is_file()
    recover(state, issue(state, source))
    assert (
        state.actual_supervisor.process is None and state.actual_supervisor.starts == 1
    )


@ROOT_ONLY
@pytest.mark.parametrize("lost_sync", [False, True])
def test_archived_completion_after_lost_reply_or_sync_can_be_explicitly_stopped(
    physical, monkeypatch, lost_sync
):
    state = physical
    before = preserved(state)
    source = issue_start(state, state.source)
    history = state.helper_state / (
        "relational-activation-"
        + state.instance.name
        + "-"
        + source["preparation_id"]
        + ".json"
    )
    if lost_sync:
        with monkeypatch.context() as patch:
            original = start_helper._sync_directory

            def fail(path):
                if history.exists():
                    raise OSError("Publication directory ACK lost")
                original(path)

            patch.setattr(start_helper, "_sync_directory", fail)
            with pytest.raises(start_helper.RelationalActivationError):
                start(state, source)
    else:
        start(state, source)  # Success with a hypothetically lost outer helper reply.
    payload = history.read_bytes()
    source_state = journal(state, source)["state"]
    assert source_state == ("activation_unconfirmed" if lost_sync else "activated")
    result = recover(state, issue(state, source))
    assert result["outcome"] == "stopped_review_required"
    assert history.read_bytes() == payload and preserved(state) == before
    assert journal(state, source)["state"] == source_state
    assert (
        state.actual_supervisor.process is None and state.actual_supervisor.starts == 1
    )


@ROOT_ONLY
@pytest.mark.parametrize(
    "problem",
    [
        "key",
        "db_owner",
        "run_owner",
        "wheel",
        "active",
        "pending_db",
        "witness_drift",
        "stop_identity",
    ],
)
def test_no_completion_when_prepared_identity_or_verified_stop_changes(
    physical, monkeypatch, problem
):
    state = physical
    source = crash_start(state, "check")
    ticket = issue(state, source)
    if problem == "key":
        (state.transport_keys / (state.instance.name + ".key")).write_bytes(b"x" * 32)
    elif problem == "db_owner":
        os.chown(state.database, 0, 1201)
    elif problem == "run_owner":
        os.chown(state.instance / "run", 0, 1201)
    elif problem == "wheel":
        (
            state.instance / "releases" / ticket["package_sha256"] / "service.whl"
        ).write_bytes(b"unreviewed")
    elif problem == "active":
        active = state.instance / "active.json"
        value = json.loads(active.read_text())
        value["entrypoint"] = "foreign.service:create_service"
        active.write_bytes(canonical(value))
    elif problem == "pending_db":
        (state.instance / ".database-unknown.rollback").mkdir()
    elif problem == "witness_drift":
        original = state.actual_supervisor.recover_disabled

        def changed(identifier):
            original(identifier)
            marker = state.helper_state / (
                "relational-activation-" + state.instance.name + ".json"
            )
            marker.write_bytes(b"changed witness")

        monkeypatch.setattr(state.actual_supervisor, "recover_disabled", changed)
    else:
        monkeypatch.setattr(
            state.actual_supervisor,
            "verify_identity",
            lambda *a, **kw: (_ for _ in ()).throw(ValueError("Process still alive")),
        )
    with pytest.raises((ValueError, helper.RelationalActivationRecoveryError)):
        recover(state, ticket)
    assert journal(state, ticket)["state"] != "confirmed"
    assert state.actual_supervisor.starts == 1


@ROOT_ONLY
@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "mode",
        "owner",
        "hardlink",
        "symlink",
        "wrong_id",
        "duplicate",
        "oversize",
        "archived",
    ],
)
def test_root_refuses_ambiguous_start_witness_without_stop_or_repair(
    physical, monkeypatch, problem
):
    state = physical
    source = crash_start(state, "check")
    marker = state.helper_state / (
        "relational-activation-" + state.instance.name + ".json"
    )
    if problem == "missing":
        marker.unlink()
    elif problem == "mode":
        marker.chmod(0o640)
    elif problem == "owner":
        os.chown(marker, 1200, 1201)
    elif problem == "hardlink":
        os.link(marker, state.helper_state / "linked-evidence")
    elif problem == "symlink":
        target = state.helper_state / "old-evidence"
        marker.rename(target)
        marker.symlink_to(target)
    elif problem == "wrong_id":
        value = json.loads(marker.read_text())
        value["activation_id"] = identity()
        marker.write_bytes(canonical(value))
    elif problem == "duplicate":
        marker.write_bytes(b'{"version":1,"version":1}')
    elif problem == "oversize":
        marker.write_bytes(b" " * 8193)
    else:
        marker.rename(
            state.helper_state
            / (
                "relational-activation-"
                + state.instance.name
                + "-"
                + source["preparation_id"]
                + ".json"
            )
        )
    with monkeypatch.context() as patch:
        patch.setattr(
            state.actual_supervisor,
            "recover_disabled",
            lambda *a: pytest.fail("Invalid witness attempted stop"),
        )
        with pytest.raises(ValueError):
            recover(state, issue(state, source))
    assert state.actual_supervisor.process is not None
    assert not tuple(state.helper_state.glob("relational-start-recovery-*.json"))
