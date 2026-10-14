"""Fresh enable-only authority + actual disposable non-root prepared host.

Systemd enable is an adapter, not live boot acceptance. No fake active version,
SQL grant fabrication, live unit/account changes or automatic start fallback.
"""

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.session import UserSession
from backend.services import application_authority_management as authority
from backend.services import application_relational_boot as coordinator
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_extensions import ApplicationGatewayError
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
from backend.tests.test_application_relational_activation_recovery import (
    issue as issue_stop,
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
from backend.tests.test_application_relational_reactivation import (
    actually_stopped,
)
from backend.tests.test_application_relational_reactivation import (
    issue as issue_restart,
)
from backend.tests.test_application_relational_reactivation import (
    receipt as restart_receipt,
)
from backend.tests.test_application_relational_reactivation import (
    stopped_again,
)
from backend.tests.test_application_relational_runtime import invoke
from three_mm_application_sdk import ApplicationStorage
from three_mm_application_sdk.relational_wire import (
    _activation_recovery_ticket,
    _activation_ticket,
    _preparation_ticket,
    _RelationalBootEnableResult,
    _RelationalBootEnableTicket,
    canonical,
    sign_metadata,
)
from three_mm_runtime import application_relational_activation as start_helper
from three_mm_runtime import application_relational_boot as helper
from three_mm_runtime.application_activation import ApplicationActivationError

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Actual POSIX clock/keys")


def issue(state, source=None, **changes):
    source = state.started if source is None else source
    return coordinator.issue_boot_enable(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "source_activation_id": source["preparation_id"],
            "expected_activation_revision": journal(state, source)["revision"],
            "expected_grant_record_revision": state.manager.inspect(1)[
                "grant_record_revision"
            ],
            "confirm_enable_prepared_boot": True,
            "transport_secret": SECRET,
            "service_uid": 1200,
            "service_gid": 1201,
            "coordinator_uid": 1202,
            "runtime_root": (
                state.runtime if hasattr(state, "runtime") else Path("/trusted/runtime")
            ),
            **changes,
        },
    )


def checkpoint(state, ticket, phase, **changes):
    return coordinator.boot_enable_checkpoint(
        state.manager,
        1,
        ticket,
        phase,
        **{
            "actor_token": state.token,
            "transport_secret": SECRET,
            "runtime_root": (
                state.runtime if hasattr(state, "runtime") else Path("/trusted/runtime")
            ),
            **changes,
        },
    )


def receipt(ticket, **changes):
    return sign_metadata(
        SECRET,
        "boot_enable_result",
        {
            "version": 1,
            "preparation_id": ticket["preparation_id"],
            "ticket_sha256": hashlib.sha256(canonical(ticket)).hexdigest(),
            "source_activation_id": ticket["source_activation_id"],
            "lifecycle_sha256": ticket["prepared_lifecycle_sha256"],
            "witness_sha256": "d" * 64,
            "outcome": "boot_enabled_not_started",
            **changes,
        },
    )


@pytest.fixture(params=["initial", "repeated"])
def activated(request):
    # Core contracts only: genuine sealed callbacks, not physical health claims.
    state = request.getfixturevalue(
        "prepared" if request.param == "initial" else "stopped_again"
    )
    state.started = (
        issue_start(state, state.source)
        if request.param == "initial"
        else issue_restart(state, state.stop)
    )
    start_checkpoint(state, state.started, "begin")
    start_checkpoint(
        state,
        state.started,
        "finish",
        receipt=(
            start_receipt(state.started)
            if request.param == "initial"
            else restart_receipt(state.started)
        ),
    )
    return state


@pytest.fixture
def approved(activated):
    apply(activated, activated.native_id)
    return activated


def unchanged_authority(state):
    with Session(state.engine) as db:
        row = db.get(Installation, 1)
        return (
            row.enabled,
            row.status,
            row.authority_mode,
            row.authority_epoch,
            row.active_version,
            row.socket_path,
            db.get(Grant, 1).payload,
        )


def test_start_success_alone_is_not_boot_or_sql_consent(activated):
    before = journal(activated, activated.started)
    with pytest.raises(authority.AuthorityManagementError):
        issue(activated)
    assert journal(activated, activated.started) == before


def test_fresh_boot_action_preserves_current_grant_epoch_and_source_receipt(approved):
    state = approved
    before = unchanged_authority(state)
    original = journal(state, state.started)
    ticket = issue(state)
    assert ticket["source_activation_revision"] != original["revision"]
    assert ticket["grant_record_revision"] != state.started["grant_record_revision"]
    assert (
        ticket["source_ticket_sha256"]
        == hashlib.sha256(canonical(state.started)).hexdigest()
    )
    assert checkpoint(state, ticket, "authorize") == {"state": "authorized_enable_only"}
    checkpoint(state, ticket, "begin")
    checkpoint(state, ticket, "check")
    assert checkpoint(state, ticket, "finish", receipt=receipt(ticket)) == {
        "state": "boot_enabled_not_started"
    }
    assert unchanged_authority(state) == before
    after = journal(state, state.started)
    assert after["data"]["result"] == original["data"]["result"]
    assert after["data"]["receipt"] == original["data"]["receipt"]
    assert after["data"]["boot_enable_id"] == ticket["preparation_id"]
    with pytest.raises(authority.AuthorityManagementError):
        checkpoint(state, ticket, "finish", receipt=receipt(ticket))


@pytest.mark.parametrize(
    "changes",
    [
        {"confirm_enable_prepared_boot": False},
        {"confirm_enable_prepared_boot": 1},
        {"expected_activation_revision": "f" * 32},
        {"expected_grant_record_revision": "f" * 32},
        {"actor_token": "invalid"},
        {"transport_secret": b"x" * 32},
        {"service_uid": True},
        {"service_gid": 0},
        {"coordinator_uid": 1200},
        {"runtime_root": Path("/foreign/runtime")},
        {"runtime_root": Path("relative/runtime")},
    ],
)
def test_bad_boot_consent_is_atomic_without_source_reservation(approved, changes):
    before = journal(approved, approved.started), unchanged_authority(approved)
    with pytest.raises((authority.AuthorityManagementError, ValueError)):
        issue(approved, **changes)
    assert (
        journal(approved, approved.started),
        unchanged_authority(approved),
    ) == before


def test_boot_ticket_and_source_stay_one_use_even_when_issue_ack_is_lost(approved):
    state = approved
    ticket = issue(state)
    for changes in ({}, {"request_id": ticket["preparation_id"]}):
        with pytest.raises(authority.AuthorityManagementError):
            issue(state, **changes)
    checkpoint(state, ticket, "begin")
    with pytest.raises(authority.AuthorityManagementError):
        checkpoint(state, ticket, "begin")


@pytest.mark.parametrize(
    "drift",
    [
        "revoke",
        "native",
        "actor",
        "key",
        "generation",
        "epoch",
        "config",
        "disabled",
        "socket",
        "new_grant",
        "source_seal",
        "source_reservation",
        "stop",
        "expired",
        "boot",
    ],
)
def test_every_checkpoint_rechecks_current_actor_grant_source_and_clock(
    approved, drift, monkeypatch
):
    state = approved
    ticket = issue(state)
    checkpoint(state, ticket, "begin")
    if drift == "revoke":
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
    elif drift == "key":
        state.keys.rotate(expected_key_id=state.keys.identity().key_id)
    elif drift == "new_grant":
        apply(state, state.native_id)
    elif drift == "stop":
        issue_stop(
            state, state.started
        )  # Real metadata fence, not fabricated SQL mode.
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
    elif drift == "source_reservation":
        with state.keys.locked() as key, Session(state.engine) as db, db.begin():
            row = db.get(Action, state.started["preparation_id"])
            value = authority._load(db, key, "action", row, row.request_id)
            value["data"]["boot_enable_id"] = identity()
            authority._save(db, key, "action", row, value)
    else:
        with state.engine.begin() as db:
            if drift == "actor":
                db.execute(
                    update(UserSession)
                    .where(UserSession.id == 1)
                    .values(is_active=False)
                )
            elif drift == "generation":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            elif drift == "source_seal":
                db.execute(
                    update(Action)
                    .where(Action.request_id == state.started["preparation_id"])
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
                            "disabled": {"enabled": False, "status": "disabled"},
                            "socket": {"socket_path": "/foreign/run/service.sock"},
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


def test_boot_action_is_never_start_stop_migration_or_sql_wire(approved):
    ticket = issue(approved)
    for parser in (
        _activation_ticket,
        _activation_recovery_ticket,
        _preparation_ticket,
    ):
        with pytest.raises(ValidationError):
            parser(ticket)
    for changes in (
        {"unit": "foreign.service"},
        {"action": "activate_prepared_service"},
        {"version": True},
        {"deadline_ms": 9007199254740990},
    ):
        with pytest.raises(ValidationError):
            _RelationalBootEnableTicket.model_validate(dict(ticket, **changes))
    with pytest.raises(ValidationError):
        _RelationalBootEnableResult.model_validate(
            dict(receipt(ticket), outcome="active_review_required")
        )
    checkpoint(approved, ticket, "begin")
    with pytest.raises(authority.AuthorityManagementError):
        checkpoint(
            approved,
            ticket,
            "finish",
            receipt=receipt(ticket, source_activation_id=identity()),
        )
    with pytest.raises(ValueError):
        checkpoint(
            approved,
            ticket,
            "finish",
            receipt=sign_metadata(SECRET, "activation_result", receipt(ticket)),
        )


def test_failed_issue_and_finish_are_atomic(approved, monkeypatch):
    state = approved
    before = journal(state, state.started), unchanged_authority(state)
    original = authority._save

    def fail(db, key, kind, row, value):
        if value["data"].get("operation") == coordinator.OPERATION:
            raise OSError("Durable metadata unavailable")
        return original(db, key, kind, row, value)

    with monkeypatch.context() as patch:
        patch.setattr(authority, "_save", fail)
        with pytest.raises(authority.AuthorityManagementError):
            issue(state)
    assert (journal(state, state.started), unchanged_authority(state)) == before
    ticket = issue(state)
    checkpoint(state, ticket, "begin")
    with monkeypatch.context() as patch:
        patch.setattr(authority, "_save", fail)
        with pytest.raises((OSError, AuthorityReviewKeyError)):
            checkpoint(state, ticket, "finish", receipt=receipt(ticket))
    assert journal(state, ticket)["state"] == "execution_unconfirmed"
    assert unchanged_authority(state) == before[1]


def test_action_budget_does_not_prune_or_reserve_source(approved, monkeypatch):
    before = journal(approved, approved.started)
    monkeypatch.setattr(coordinator.preparation, "MAX_PREPARATION_ACTIONS", 1)
    with pytest.raises(authority.AuthorityManagementError):
        issue(approved)
    assert journal(approved, approved.started) == before


@pytest.mark.parametrize(
    "change",
    [
        {"service_uid": True},
        {"service_gid": True},
        {"coordinator_uid": True},
        {"service_uid": 0},
        {"service_gid": -1},
        {"coordinator_uid": 2147483648},
    ],
)
def test_strict_helper_principals_refused_before_any_metadata_access(change):
    # A bool must not match a real UID/GID of 1 by Python's True == 1 rule.
    manager = SimpleNamespace(
        _prepare=lambda *a: pytest.fail("Invalid principal reached metadata")
    )
    with pytest.raises(
        authority.AuthorityManagementError, match="invalid_boot_enable_principal"
    ):
        coordinator.issue_boot_enable(
            manager,
            1,
            **{
                "actor_token": "unused",
                "request_id": "a" * 32,
                "source_activation_id": "b" * 32,
                "expected_activation_revision": "c" * 32,
                "expected_grant_record_revision": "d" * 32,
                "confirm_enable_prepared_boot": True,
                "transport_secret": SECRET,
                "service_uid": 1,
                "service_gid": 1,
                "coordinator_uid": 2,
                "runtime_root": Path("/trusted/runtime"),
                **change,
            },
        )


class BootProcessAdapter:
    """Real process credentials/health; disposable enable-state, NOT systemd."""

    def __init__(self, process):
        self.process, self.enabled, self.enables, self.disables = process, False, 0, 0

    def verify_boot_identity(self, instance, uid, gid, *, enabled):
        assert self.enabled == enabled
        self.process.verify_identity(instance, uid, gid, running=True)
        pid = self.process.process.pid
        return pid, int(
            Path(f"/proc/{pid}/stat").read_text().rpartition(") ")[2].split()[19]
        )

    def enable_boot(self, instance):
        assert instance == self.process.state.instance.name and not self.enabled
        self.enabled, self.enables = True, self.enables + 1

    def disable_boot(self, instance):
        assert instance == self.process.state.instance.name
        self.enabled, self.disables = False, self.disables + 1


@pytest.fixture
def running(physical):
    state = physical
    state.started = issue_start(state, state.source)
    start(state, state.started)  # Actual one-shot non-root host + protected witness.
    apply(state, state.native_id)
    state.boot_supervisor = BootProcessAdapter(state.actual_supervisor)
    return state


def enable(state, ticket, **changes):
    return helper.enable_prepared_relational_boot(
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
            "supervisor": state.boot_supervisor,
            **changes,
        },
    )


@ROOT_ONLY
def test_real_healthy_process_enabled_without_start_migration_rekey_or_grant_change(
    running, monkeypatch
):
    state = running
    pid = state.actual_supervisor.process.pid
    before = unchanged_authority(state)
    files = {
        path: path.read_bytes()
        for path in (
            state.database,
            state.instance / "relational.json",
            state.instance / "active.json",
            state.transport_keys / (state.instance.name + ".key"),
            *state.helper_state.glob("relational-activation-*.json"),
        )
    }
    monkeypatch.setattr(
        ApplicationStorage,
        "migrate",
        lambda *a: pytest.fail("Boot imported migrations"),
    )
    ticket = issue(state)
    result = enable(state, ticket)
    assert result["outcome"] == "boot_enabled_not_started"
    assert state.boot_supervisor.enabled and state.boot_supervisor.enables == 1
    assert (
        state.actual_supervisor.starts == 1
        and state.actual_supervisor.process.pid == pid
    )
    assert unchanged_authority(state) == before
    assert all(path.read_bytes() == body for path, body in files.items())
    assert invoke(state, "inspect") == {"values": ["preserved"]}
    state.manager.revoke(
        1,
        actor_token=state.token,
        request_id=identity(),
        expected_revision=ticket["grant_record_revision"],
    )
    with pytest.raises(ApplicationGatewayError):
        invoke(state, "inspect")  # Boot flag is not SQL access.
    with pytest.raises(
        (helper.RelationalBootEnableError, authority.AuthorityManagementError)
    ):
        enable(state, ticket)
    assert state.boot_supervisor.enables == 1


@ROOT_ONLY
def test_repeated_successful_start_uses_its_own_protected_witness(actually_stopped):
    state = actually_stopped
    state.started = issue_restart(state, state.stop)
    start(state, state.started)
    apply(state, state.native_id)
    state.boot_supervisor = BootProcessAdapter(state.actual_supervisor)
    ticket = issue(state)
    assert ticket["source_activation_action"] == "reactivate_prepared_service"
    assert enable(state, ticket)["outcome"] == "boot_enabled_not_started"
    with pytest.raises(authority.AuthorityManagementError):
        issue(state, state.first_start)  # Historical healthy/same version cannot win.
    assert state.actual_supervisor.starts == 1


@ROOT_ONLY
def test_root_evidence_budget_is_bounded_and_never_pruned(running):
    state = running
    ticket = issue(state)
    for index in range(32):
        path = (
            state.helper_state
            / f"relational-boot-{state.instance.name}-{index:032x}.json"
        )
        path.write_bytes(b"retained unknown evidence")
        path.chmod(0o600)
    before = {
        path: path.read_bytes() for path in state.helper_state.glob("relational-*.json")
    }
    with pytest.raises(helper.RelationalBootEnableError, match="evidence review"):
        enable(state, ticket)
    assert state.boot_supervisor.enables == 0
    assert journal(state, ticket)["state"] == "recorded"
    assert all(path.read_bytes() == payload for path, payload in before.items())


@ROOT_ONLY
@pytest.mark.parametrize("phase", ["begin", "check", "finish", "enable", "cleanup"])
def test_lost_ack_never_retries_or_claims_boot_enabled(running, phase, monkeypatch):
    state = running
    ticket = issue(state)
    before = unchanged_authority(state)
    pid = state.actual_supervisor.process.pid
    original_enable = state.boot_supervisor.enable_boot

    def lose(value, current, **kw):
        result = checkpoint(state, value, current, **kw)
        if current == phase or (phase == "cleanup" and current == "finish"):
            raise OSError("ACK lost AFTER durable write")
        return result

    def bad_enable(instance):
        original_enable(instance)
        raise OSError("Unit enable ACK lost")

    if phase == "enable":
        monkeypatch.setattr(state.boot_supervisor, "enable_boot", bad_enable)
    if phase == "cleanup":
        monkeypatch.setattr(
            state.boot_supervisor,
            "disable_boot",
            lambda *a: (_ for _ in ()).throw(OSError("Disable unknown")),
        )
    with pytest.raises(helper.RelationalBootEnableError, match="unconfirmed"):
        enable(state, ticket, checkpoint=lose)
    assert (
        state.actual_supervisor.process.pid == pid
        and state.actual_supervisor.starts == 1
    )
    assert unchanged_authority(state) == before
    assert state.boot_supervisor.enables == (0 if phase in {"begin", "check"} else 1)
    assert state.boot_supervisor.enabled == (phase == "cleanup")
    marker = next(state.helper_state.glob("relational-boot-*.json"))
    assert json.loads(marker.read_text())["phase"] in {
        "enable_unconfirmed",
        "enabled_unconfirmed",
    }
    assert marker.stat().st_mode & 0o777 == 0o600
    assert (
        state.token not in marker.read_text() and SECRET.hex() not in marker.read_text()
    )
    with pytest.raises(helper.RelationalBootEnableError):
        enable(state, ticket)
    assert state.boot_supervisor.enables == (0 if phase in {"begin", "check"} else 1)


@ROOT_ONLY
@pytest.mark.parametrize(
    "problem",
    [
        "pending",
        "missing",
        "changed",
        "symlink",
        "owner",
        "oversized",
        "duplicate",
        "wheel",
        "key",
        "metadata",
        "namespace",
    ],
)
def test_changed_protected_start_or_prepared_state_refused_before_any_enable(
    running, problem
):
    state = running
    ticket = issue(state)
    path = next(state.helper_state.glob("relational-activation-*-*.json"))
    if problem == "pending":
        (
            state.helper_state
            / ("relational-activation-" + state.instance.name + ".json")
        ).write_bytes(path.read_bytes())
    elif problem == "missing":
        path.unlink()  # Only disposable test evidence, never production cleanup.
    elif problem == "changed":
        value = json.loads(path.read_text())
        value["ticket_sha256"] = "0" * 64
        path.write_text(json.dumps(value))
    elif problem == "symlink":
        other = path.with_suffix(".source")
        path.rename(other)
        path.symlink_to(other)
    elif problem == "owner":
        os.chown(path, 1200, 1201)
    elif problem == "oversized":
        path.write_bytes(b" " * 8193)
    elif problem == "duplicate":
        path.write_bytes(b'{"version":1,"version":1}')
    elif problem == "wheel":
        (
            state.instance / "releases" / ticket["package_sha256"] / "service.whl"
        ).write_bytes(b"changed")
    elif problem == "key":
        (state.transport_keys / (state.instance.name + ".key")).write_bytes(b"x" * 32)
    elif problem == "metadata":
        (state.instance / "active.json").write_text("{}")
    else:
        os.chown(state.database, 0, 1201)
    with pytest.raises((helper.RelationalBootEnableError, ValueError, OSError)):
        enable(state, ticket)
    assert state.boot_supervisor.enables == 0
    assert journal(state, ticket)["state"] == "recorded"


@ROOT_ONLY
@pytest.mark.parametrize(
    "drift", ["health", "revoke_before", "revoke_after", "process", "witness"]
)
def test_changes_during_enable_retain_evidence_and_do_not_restart(
    running, drift, monkeypatch
):
    state = running
    ticket = issue(state)
    original_enable = state.boot_supervisor.enable_boot

    def revoke():
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=ticket["grant_record_revision"],
        )

    def health(*a, **kw):
        if drift == "health":
            raise OSError("Health unavailable")
        if drift == "revoke_before":
            revoke()

    def mutate(instance):
        original_enable(instance)
        if drift == "revoke_after":
            revoke()
        elif drift == "witness":
            next(state.helper_state.glob("relational-activation-*-*.json")).write_text(
                "{}"
            )

    original_identity = state.boot_supervisor.verify_boot_identity

    def recycled(*a, **kw):
        pid, began = original_identity(*a, **kw)
        return pid, began + int(drift == "process" and kw["enabled"])

    monkeypatch.setattr(helper, "_wait_for_health", health)
    monkeypatch.setattr(state.boot_supervisor, "enable_boot", mutate)
    monkeypatch.setattr(state.boot_supervisor, "verify_boot_identity", recycled)
    with pytest.raises(helper.RelationalBootEnableError):
        enable(state, ticket)
    assert not state.boot_supervisor.enabled and state.actual_supervisor.starts == 1
    assert state.boot_supervisor.enables == (
        0 if drift in {"health", "revoke_before"} else 1
    )
    assert journal(state, ticket)["state"] == "execution_unconfirmed"


def test_systemd_boot_commands_never_start_stop_restart_or_use_now(monkeypatch):
    supervisor = helper.PreparedBootSupervisor()
    calls = []
    monkeypatch.setattr(
        supervisor, "_run", lambda args, instance: calls.append((args, instance))
    )
    supervisor.enable_boot("a" * 24)
    supervisor.disable_boot("a" * 24)
    assert calls == [(["enable"], "a" * 24), (["disable"], "a" * 24)]
    for value in ("foreign.service", "../../other", "a" * 23):
        with pytest.raises(ApplicationActivationError):
            supervisor.enable_boot(value)
    assert len(calls) == 2


@pytest.mark.parametrize("enabled", [False, True])
def test_boot_adapter_checks_fixed_unit_kernel_principal_and_incarnation(
    monkeypatch, enabled
):
    fields = {
        "User": "1200",
        "Group": "1201",
        "MainPID": "42",
        "LoadState": "loaded",
        "ActiveState": "active",
        "UnitFileState": "enabled" if enabled else "disabled",
        "Job": "0",
    }
    monkeypatch.setattr(
        start_helper.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            stdout="\n".join(f"{k}={v}" for k, v in fields.items())
        ),
    )

    def kernel(path, **kw):
        if path.name == "status":
            return "Uid: 1200 1200 1200 1200\nGid: 1201 1201 1201 1201\n"
        return "42 (reviewed worker) " + " ".join(["S"] + ["0"] * 18 + ["123"])

    monkeypatch.setattr(Path, "read_text", kernel)
    supervisor = helper.PreparedBootSupervisor()
    assert supervisor.verify_boot_identity("a" * 24, 1200, 1201, enabled=enabled) == (
        42,
        123,
    )
    fields["UnitFileState"] = "enabled" if not enabled else "disabled"
    with pytest.raises(start_helper.RelationalActivationError):
        supervisor.verify_boot_identity("a" * 24, 1200, 1201, enabled=enabled)
