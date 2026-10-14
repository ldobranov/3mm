"""Fresh start after proven stop; real disposable non-root host, no live units.

Core-only fixtures prove sealed metadata, not physical stop. Root fixtures run
the actual prepare/start/crash/stop/review/restart chain, never SQL-enable it.
"""

import hashlib
import json
import os
import sqlite3

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
from backend.services import application_relational_reactivation as coordinator
from backend.services.application_extensions import ApplicationGatewayError
from backend.services.application_policy_reviews import PolicyReviewStoreError
from backend.tests.test_application_relational_activation import (
    ProcessSupervisor,
    checkpoint,
)
from backend.tests.test_application_relational_activation import issue as issue_start
from backend.tests.test_application_relational_activation import (
    journal,
    migratable,
    physical,
    prepared,
    prepared_paths,
    start,
    tmp_path,
)
from backend.tests.test_application_relational_activation_recovery import (
    Crash,
)
from backend.tests.test_application_relational_activation_recovery import (
    checkpoint as recovery_checkpoint,
)
from backend.tests.test_application_relational_activation_recovery import (
    crash_start,
)
from backend.tests.test_application_relational_activation_recovery import (
    issue as issue_recovery,
)
from backend.tests.test_application_relational_activation_recovery import (
    preserved,
)
from backend.tests.test_application_relational_activation_recovery import (
    receipt as stop_receipt,
)
from backend.tests.test_application_relational_activation_recovery import (
    recover,
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
from backend.tests.test_application_relational_runtime import invoke
from three_mm_application_sdk import ApplicationStorage
from three_mm_application_sdk.relational_wire import (
    _preparation_ticket,
    _RelationalActivationRecoveryTicket,
    _RelationalActivationTicket,
    _RelationalReactivationTicket,
    canonical,
    sign_metadata,
    verify_metadata,
)
from three_mm_runtime import application_relational_activation as helper
from three_mm_runtime.application_relational_preparation import (
    RelationalPreparationError,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Actual POSIX clock/keys")


def issue(state, source, **changes):
    grant_revision = (
        changes["expected_grant_record_revision"]
        if "expected_grant_record_revision" in changes
        else state.manager.inspect(1)["grant_record_revision"]
    )
    return coordinator.issue_prepared_reactivation(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "source_recovery_id": source["preparation_id"],
            "expected_recovery_revision": journal(state, source)["revision"],
            "expected_grant_record_revision": grant_revision,
            "confirm_restart_stopped_prepared_service": True,
            "transport_secret": SECRET,
            "service_uid": 1200,
            "service_gid": 1201,
            "coordinator_uid": 1202,
            **changes,
        },
    )


def receipt(ticket, **changes):
    return sign_metadata(
        SECRET,
        "reactivation_result",
        {
            "version": 1,
            "preparation_id": ticket["preparation_id"],
            "lifecycle_sha256": ticket["prepared_lifecycle_sha256"],
            "outcome": "active_review_required",
            **changes,
        },
    )


@pytest.fixture
def stopped_again(prepared):
    state = prepared
    state.first_start = issue_start(state, state.source)
    checkpoint(state, state.first_start, "begin")
    state.stop = issue_recovery(state, state.first_start)
    recovery_checkpoint(state, state.stop, "begin")
    recovery_checkpoint(state, state.stop, "finish", receipt=stop_receipt(state.stop))
    apply(
        state, state.native_id
    )  # Actual new human review/approve/apply while disabled.
    return state


def test_exact_confirmed_stop_consumed_once_and_old_callbacks_fenced(stopped_again):
    state = stopped_again
    original_preparation = journal(state, state.source)
    original_start = journal(state, state.first_start)
    original_stop = journal(state, state.stop)
    ticket = issue(state, state.stop)
    assert journal(state, state.source) == original_preparation
    for source, before in (
        (state.first_start, original_start),
        (state.stop, original_stop),
    ):
        after = journal(state, source)
        assert after["state"] == before["state"]
        assert after["data"]["result"] == before["data"]["result"]
        assert after["data"].get("receipt") == before["data"].get("receipt")
        assert after["data"]["reactivation_id"] == ticket["preparation_id"]
    assert ticket["origin_activation_id"] == state.first_start["preparation_id"]
    for changes in ({}, {"request_id": ticket["preparation_id"]}):
        with pytest.raises(authority.AuthorityManagementError):
            issue(state, state.stop, **changes)
    with pytest.raises(authority.AuthorityManagementError):
        issue_recovery(state, state.first_start)
    with pytest.raises(authority.AuthorityManagementError):
        recovery_checkpoint(
            state, state.stop, "finish", receipt=stop_receipt(state.stop)
        )
    checkpoint(state, ticket, "begin")
    checkpoint(state, ticket, "finish", receipt=receipt(ticket))
    assert not state.manager.inspect(1)["grant_effective"]
    assert checkpoint(state, ticket, "finish", receipt=receipt(ticket))["historical"]


@pytest.mark.parametrize(
    "changes",
    [
        {"confirm_restart_stopped_prepared_service": False},
        {"confirm_restart_stopped_prepared_service": 1},
        {"expected_recovery_revision": "f" * 32},
        {"expected_grant_record_revision": "f" * 32},
        {"actor_token": "invalid"},
        {"transport_secret": b"x" * 32},
        {"service_uid": 0},
        {"service_uid": True},
        {"service_gid": 0},
        {"coordinator_uid": 1200},
        {"source_recovery_id": "f" * 32},
    ],
)
def test_bad_consent_is_atomic_and_does_not_consume_stop(stopped_again, changes):
    state = stopped_again
    before = journal(state, state.stop), journal(state, state.first_start)
    with pytest.raises((authority.AuthorityManagementError, ValueError, KeyError)):
        issue(state, state.stop, **changes)
    assert (journal(state, state.stop), journal(state, state.first_start)) == before


@pytest.mark.parametrize("phase", ["recorded", "execution_unconfirmed"])
def test_unknown_stop_cannot_authorize_reactivation(prepared, phase):
    state = prepared
    source = issue_start(state, state.source)
    recovery = issue_recovery(state, source)
    if phase == "execution_unconfirmed":
        recovery_checkpoint(state, recovery, "begin")
    apply(state, state.native_id)
    with pytest.raises((authority.AuthorityManagementError, KeyError)):
        issue(state, recovery)
    assert "reactivation_id" not in journal(state, recovery)["data"]


def test_stop_alone_never_creates_current_start_rights(prepared):
    state = prepared
    source = issue_start(state, state.source)
    recovery = issue_recovery(state, source)
    recovery_checkpoint(state, recovery, "begin")
    recovery_checkpoint(state, recovery, "finish", receipt=stop_receipt(recovery))
    with pytest.raises(authority.AuthorityManagementError):
        issue(state, recovery)
    assert not state.manager.inspect(1)["grant_effective"]


def test_failed_issue_rolls_back_both_source_reservations(stopped_again, monkeypatch):
    state = stopped_again
    before = journal(state, state.stop), journal(state, state.first_start)
    original = authority._save

    def fail(db, key, kind, row, value):
        if value["data"].get("operation") == coordinator.OPERATION:
            raise OSError("Lost durable issuance")
        return original(db, key, kind, row, value)

    monkeypatch.setattr(authority, "_save", fail)
    with pytest.raises(authority.AuthorityManagementError):
        issue(state, state.stop)
    assert (journal(state, state.stop), journal(state, state.first_start)) == before


def test_newer_confirmed_stop_supersedes_old_restart_source(stopped_again):
    state = stopped_again
    newer = issue_recovery(state, state.first_start)
    recovery_checkpoint(state, newer, "begin")
    recovery_checkpoint(state, newer, "finish", receipt=stop_receipt(newer))
    apply(state, state.native_id)
    with pytest.raises(authority.AuthorityManagementError):
        issue(state, state.stop)
    assert issue(state, newer)["source_recovery_id"] == newer["preparation_id"]


def test_bounded_action_journal_refuses_issue_atomically(stopped_again, monkeypatch):
    state = stopped_again
    before = journal(state, state.stop), journal(state, state.first_start)
    monkeypatch.setattr(coordinator.preparation, "MAX_PREPARATION_ACTIONS", 1)
    with pytest.raises(authority.AuthorityManagementError):
        issue(state, state.stop)
    assert (journal(state, state.stop), journal(state, state.first_start)) == before


@pytest.mark.parametrize("drift", ["version", "status", "incarnation"])
def test_final_pin_recheck_refuses_post_package_read_race(
    stopped_again, monkeypatch, drift
):
    state = stopped_again
    original = state.manager._prepare
    before = journal(state, state.stop)
    grant_revision = state.manager.inspect(1)["grant_record_revision"]

    def stale(identifier):
        prepared_value = original(identifier)
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
        return prepared_value

    monkeypatch.setattr(state.manager, "_prepare", stale)
    with pytest.raises(authority.AuthorityManagementError):
        issue(state, state.stop, expected_grant_record_revision=grant_revision)
    assert journal(state, state.stop) == before


@pytest.mark.parametrize(
    "drift",
    [
        "grant",
        "native",
        "actor",
        "epoch",
        "generation",
        "configuration",
        "new_grant",
        "expired",
        "boot",
        "stop_seal",
        "origin_seal",
    ],
)
def test_post_begin_rechecks_fresh_consent_and_source(
    stopped_again, monkeypatch, drift
):
    state = stopped_again
    ticket = issue(state, state.stop)
    checkpoint(state, ticket, "begin")
    if drift == "grant":
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=ticket["grant_record_revision"],
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
    elif drift == "new_grant":
        apply(state, state.native_id)
    elif drift in {"expired", "boot"}:
        monkeypatch.setattr(
            authority,
            "_clock",
            lambda: (
                (
                    "ffffffff-ffff-ffff-ffff-ffffffffffff"
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
            elif drift.endswith("seal"):
                target = state.stop if drift == "stop_seal" else state.first_start
                db.execute(
                    update(Action)
                    .where(Action.request_id == target["preparation_id"])
                    .values(seal="0" * 64)
                )
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
                        }[drift]
                    )
                )
    for phase in ("check", "finish"):
        with pytest.raises(
            (authority.AuthorityManagementError, PolicyReviewStoreError, ValueError)
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


def test_restart_contract_is_distinct_from_start_stop_preparation_and_sql(
    stopped_again,
):
    ticket = issue(stopped_again, stopped_again.stop)
    for model in (_RelationalActivationTicket, _RelationalActivationRecoveryTicket):
        with pytest.raises(ValidationError):
            model.model_validate(ticket)
    with pytest.raises(ValidationError):
        _preparation_ticket(ticket)
    with pytest.raises(ValueError):
        verify_metadata(SECRET, "activation", ticket)
    with pytest.raises(ValidationError):
        _RelationalReactivationTicket.model_validate(
            dict(ticket, database_path="/foreign")
        )
    checkpoint(stopped_again, ticket, "begin")
    with pytest.raises(ValueError):
        checkpoint(
            stopped_again,
            ticket,
            "finish",
            receipt=sign_metadata(SECRET, "activation_result", receipt(ticket)),
        )


@pytest.fixture
def actually_stopped(physical):
    state = physical
    state.first_start = crash_start(state, "check")  # Real live non-root process.
    state.stop = issue_recovery(state, state.first_start)
    recover(state, state.stop)
    assert state.actual_supervisor.process is None
    apply(state, state.native_id)
    # New launch adapter = distinct actual process, exactly one start per action.
    state.actual_supervisor = ProcessSupervisor(state)
    return state


@ROOT_ONLY
def test_real_restart_keeps_data_key_history_and_requires_new_runtime_review(
    actually_stopped, monkeypatch
):
    state = actually_stopped
    before = preserved(state)
    witnesses = {
        path: path.read_bytes() for path in state.helper_state.glob("relational-*.json")
    }
    with Session(state.engine) as db:
        old_grant = db.get(Grant, 1).payload
    ticket = issue(state, state.stop)
    monkeypatch.setattr(
        ApplicationStorage,
        "migrate",
        lambda *a: pytest.fail("Restart reran migrations as Root"),
    )
    result = start(state, ticket)
    assert result["outcome"] == "active_review_required"
    assert state.actual_supervisor.starts == 1
    state.actual_supervisor.verify_identity(
        state.instance.name, 1200, 1201, running=True
    )
    assert preserved(state) == before
    assert all(path.read_bytes() == value for path, value in witnesses.items())
    with Session(state.engine) as db:
        assert db.get(Grant, 1).payload == old_grant
    with pytest.raises(ApplicationGatewayError):
        invoke(state, "inspect")
    apply(state, state.native_id)
    assert invoke(state, "inspect") == {"values": ["preserved"]}
    assert invoke(state, "mutate", {"value": "after confirmed restart"}) == {
        "value": "after confirmed restart"
    }
    with sqlite3.connect(state.database) as db:
        assert db.execute(
            "SELECT revision FROM three_mm_schema_migrations"
        ).fetchall() == [("0001",), ("0002",)]
    with pytest.raises(
        (helper.RelationalActivationError, authority.AuthorityManagementError)
    ):
        start(state, ticket)
    assert state.actual_supervisor.starts == 1


@ROOT_ONLY
@pytest.mark.parametrize("phase", ["issue", "begin", "check", "finish"])
def test_second_interrupted_start_can_be_freshly_stopped_and_started_again(
    actually_stopped, phase
):
    state = actually_stopped
    before = preserved(state)
    ticket = issue(state, state.stop)
    if phase != "issue":

        def crash(value, at, **kw):
            result = checkpoint(state, value, at, **kw)
            if at == phase:
                raise Crash()
            return result

        with pytest.raises(Crash):
            start(state, ticket, checkpoint=crash)
    recovery = issue_recovery(state, ticket)
    assert recovery["action"] == "reconcile_reactivated_start"
    recover(state, recovery)
    assert state.actual_supervisor.process is None
    assert preserved(state) == before
    apply(state, state.native_id)
    new_ticket = issue(state, recovery)
    assert new_ticket["origin_activation_id"] == state.first_start["preparation_id"]
    state.actual_supervisor = ProcessSupervisor(state)
    start(state, new_ticket)
    assert state.actual_supervisor.starts == 1
    assert preserved(state) == before


@ROOT_ONLY
@pytest.mark.parametrize("phase", ["begin", "finish"])
def test_lost_restart_ack_never_retries_and_preserves_witness(actually_stopped, phase):
    state = actually_stopped
    ticket = issue(state, state.stop)
    before = preserved(state)

    def lost(value, at, **kw):
        result = checkpoint(state, value, at, **kw)
        if at == phase:
            raise OSError("ACK lost after durable commit")
        return result

    with pytest.raises(helper.RelationalActivationError, match="unconfirmed"):
        start(state, ticket, checkpoint=lost)
    assert state.actual_supervisor.starts == (0 if phase == "begin" else 1)
    assert state.actual_supervisor.process is None
    marker = state.helper_state / (
        "relational-reactivation-"
        + state.instance.name
        + "-"
        + ticket["preparation_id"]
        + ".pending.json"
    )
    saved = marker.read_bytes()
    with pytest.raises(helper.RelationalActivationError):
        start(state, ticket)
    recover(state, issue_recovery(state, ticket))
    assert marker.read_bytes() == saved and preserved(state) == before


@ROOT_ONLY
def test_retained_restart_witness_budget_denies_without_pruning(actually_stopped):
    state = actually_stopped
    ticket = issue(state, state.stop)
    records = []
    for number in range(32):
        path = state.helper_state / (
            "relational-reactivation-"
            + state.instance.name
            + "-"
            + format(number, "032x")
            + ".json"
        )
        path.write_bytes(b"retained unknown evidence")
        path.chmod(0o600)
        records.append(path)
    with pytest.raises(helper.RelationalActivationError, match="recovery review"):
        start(state, ticket)
    assert state.actual_supervisor.starts == 0
    assert all(path.read_bytes() == b"retained unknown evidence" for path in records)


@ROOT_ONLY
@pytest.mark.parametrize(
    "problem",
    [
        "stop_missing",
        "stop_unknown",
        "stop_mode",
        "stop_owner",
        "stop_link",
        "stop_duplicate",
        "stop_receipt",
        "source_witness",
        "database_owner",
        "key",
        "wheel",
    ],
)
def test_root_refuses_changed_stop_or_prepared_evidence_before_process_effect(
    actually_stopped, monkeypatch, problem
):
    state = actually_stopped
    ticket = issue(state, state.stop)
    path = state.helper_state / (
        "relational-start-recovery-"
        + state.instance.name
        + "-"
        + state.stop["preparation_id"]
        + ".json"
    )
    if problem == "stop_missing":
        path.unlink()
    elif problem == "stop_mode":
        path.chmod(0o640)
    elif problem == "stop_owner":
        os.chown(path, 1200, 1201)
    elif problem == "stop_link":
        os.link(path, state.helper_state / "duplicate-link")
    elif problem == "stop_duplicate":
        path.write_bytes(b'{"version":1,"version":1}')
    elif problem in {"stop_unknown", "stop_receipt"}:
        value = json.loads(path.read_text())
        if problem == "stop_unknown":
            value["phase"] = "stopped_unconfirmed"
        else:
            value["receipt"]["witness_sha256"] = "0" * 64
        path.write_bytes(canonical(value))
    elif problem == "source_witness":
        (
            state.helper_state
            / ("relational-activation-" + state.instance.name + ".json")
        ).write_bytes(b"changed")
    elif problem == "database_owner":
        os.chown(state.database, 0, 1201)
    elif problem == "key":
        (state.transport_keys / (state.instance.name + ".key")).write_bytes(b"x" * 32)
    else:
        (
            state.instance / "releases" / ticket["package_sha256"] / "service.whl"
        ).write_bytes(b"changed")
    with monkeypatch.context() as patch:
        patch.setattr(
            state.actual_supervisor,
            "recover_disabled",
            lambda *a: pytest.fail("Bad evidence attempted process effect"),
        )
        with pytest.raises(
            (
                ValueError,
                OSError,
                helper.RelationalActivationError,
                RelationalPreparationError,
            )
        ):
            start(state, ticket)
    assert state.actual_supervisor.starts == 0
    assert not tuple(state.helper_state.glob("relational-reactivation-*.json"))
