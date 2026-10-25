"""Exact Core start consent + actual non-root prepared host, no live services."""
from three_mm_platform_wire import COMPATIBILITY_ACTIONS

import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.config import ApplicationRuntimeSettings
from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ModulePackage
from backend.db.session import UserSession
from backend.services import application_authority_management as authority
from backend.services import application_relational_activation as coordinator
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_extensions import ApplicationGatewayError
from backend.services.application_platform import ApplicationPlatformServer
from backend.services.application_policy_reviews import PolicyReviewStoreError
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_relational_migrations import (
    migratable,
    migration_ticket,
    run,
)
from backend.tests.test_application_relational_preparation import (
    ROOT_ONLY,
    SECRET,
    apply,
)
from backend.tests.test_application_relational_preparation import (
    checkpoint as preparation_checkpoint,
)
from backend.tests.test_application_relational_preparation import (
    identity,
)
from backend.tests.test_application_relational_preparation import (
    issue as issue_preparation,
)
from backend.tests.test_application_relational_preparation import (
    managed_installed,
    native,
    prepared_paths,
    source_installed,
    source_subject,
    stopped,
)
from backend.tests.test_application_relational_registration import (
    approve as approve_registration,
)
from backend.tests.test_application_relational_registration import (
    fresh as registration_catalog,
)
from backend.tests.test_application_relational_registration import (
    register,
)
from backend.tests.test_application_relational_runtime import SERVICE, invoke, package
from three_mm_application_sdk import ApplicationStorage
from three_mm_application_sdk.relational_wire import (
    _preparation_ticket,
    _RelationalActivationResult,
    _RelationalActivationTicket,
    canonical,
    prepared_lifecycle,
    sign_metadata,
)
from three_mm_runtime import application_lifecycle as locks
from three_mm_runtime import application_relational_activation as helper
from three_mm_runtime.application_activation import activate_application_package
from three_mm_runtime.application_relational_installation import (
    prepare_fresh_relational_installation,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real POSIX keys/clock")


def issue(state, source, **changes):
    return coordinator.issue_prepared_activation(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "source_preparation_id": source["preparation_id"],
            "expected_grant_record_revision": state.manager.inspect(1)[
                "grant_record_revision"
            ],
            "confirm_start_prepared_service": True,
            "transport_secret": getattr(state, "activation_secret", SECRET),
            "service_uid": 1200,
            "service_gid": 1201,
            "coordinator_uid": 1202,
            **changes,
        },
    )


def checkpoint(state, ticket, phase, **changes):
    return coordinator.activation_checkpoint(
        state.manager,
        1,
        ticket,
        phase,
        **{
            "actor_token": state.token,
            "transport_secret": getattr(state, "activation_secret", SECRET),
            "runtime_root": (
                state.runtime if hasattr(state, "runtime") else Path("/trusted/runtime")
            ),
            **changes,
        },
    )


def receipt(ticket, **changes):
    return sign_metadata(
        SECRET,
        "activation_result",
        {
            "version": 1,
            "preparation_id": ticket["preparation_id"],
            "lifecycle_sha256": ticket["prepared_lifecycle_sha256"],
            "outcome": "active_review_required",
            **changes,
        },
    )


def journal(state, ticket):
    with state.keys.locked() as key, Session(state.engine) as db:
        return authority._load(
            db,
            key,
            "action",
            db.get(Action, ticket["preparation_id"]),
            ticket["preparation_id"],
        )


@pytest.fixture
def prepared(stopped):
    # Core contract fixture: authenticated metadata callback, no assertion that
    # this unit fixture prepared/started a physical database. Root cases below do.
    state = stopped
    source = issue_preparation(state)
    preparation_checkpoint(state, source, "begin")
    preparation_checkpoint(
        state,
        source,
        "finish",
        receipt=sign_metadata(
            SECRET,
            "preparation_result",
            {
                "version": 1,
                "preparation_id": source["preparation_id"],
                "lifecycle_sha256": hashlib.sha256(
                    canonical(prepared_lifecycle(source, SECRET))
                ).hexdigest(),
                "outcome": "prepared_not_started",
            },
        ),
    )
    state.source = source
    return state


def test_begin_fences_old_grant_before_start_and_finish_never_restores_it(prepared):
    state = prepared
    ticket = issue(state, state.source)
    assert ticket["database_lineage"] == state.source["database_lineage"]
    assert checkpoint(state, ticket, "authorize") == {"state": "authorized_not_started"}
    with Session(state.engine) as db:
        old_grant = db.get(Grant, 1).payload
        old_epoch = db.get(Installation, 1).authority_epoch
    checkpoint(state, ticket, "begin")
    with state.keys.locked() as key, Session(state.engine) as db:
        row = db.get(Installation, 1)
        assert (
            row.authority_mode == "review_required" and row.authority_epoch != old_epoch
        )
        assert not row.enabled and row.status == "disabled"
        assert db.get(Grant, 1).payload == old_grant
        with pytest.raises(
            authority.AuthorityManagementError, match="grant_not_current"
        ):
            state.manager._require_grant(
                db, key, 1, state.manager._prepare(1), "storage:relational_read"
            )
    assert checkpoint(state, ticket, "check") == {"state": "execution_unconfirmed"}
    assert checkpoint(state, ticket, "finish", receipt=receipt(ticket)) == {
        "state": "active_review_required"
    }
    with Session(state.engine) as db:
        row = db.get(Installation, 1)
        assert row.enabled and row.status == "active"
        assert row.active_version == state.validated.application_extension.version
        assert row.authority_mode == "review_required"
        assert row.socket_path == str(
            Path("/trusted/runtime") / ticket["instance_id"] / "run/service.sock"
        )
        assert db.get(Grant, 1).payload == old_grant
    assert not state.manager.inspect(1)["grant_effective"]
    assert (
        checkpoint(state, ticket, "finish", receipt=receipt(ticket))["historical"]
        is True
    )
    apply(state, state.native_id)
    with state.keys.locked() as key, Session(state.engine) as db:
        state.manager._require_grant(
            db, key, 1, state.manager._prepare(1), "storage:relational_read"
        )
    assert journal(state, ticket)["state"] == "activated"


def test_new_permission_review_between_preparation_and_start_preserves_lineage(
    prepared,
):
    state = prepared
    apply(state, state.native_id)
    ticket = issue(state, state.source)
    assert ticket["authority_epoch"] != state.source["authority_epoch"]
    assert ticket["database_lineage"] == state.source["database_lineage"]
    checkpoint(state, ticket, "begin")
    checkpoint(state, ticket, "finish", receipt=receipt(ticket))


@pytest.fixture
def checkpoint_prepared(stopped, request):
    """Real v6/v7 sealed review; helper receipts remain the existing unit fixture."""
    from dataclasses import replace

    from backend.tests.test_application_relational_review_api import store_package
    from three_mm_protocol.tests.test_application_checkpoints import checkpoint_request

    state = stopped
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["checkpoints"] = [checkpoint_request()]
    version = getattr(request, "param", 6)
    if version == 7:
        definition["platform_permissions"] = ["installation.identity.read"]
        manifest = state.validated.manifest.model_dump(mode="json")
        manifest["permissions"].append("installation.identity.read")
        state.validated = replace(
            state.validated,
            manifest=type(state.validated.manifest).model_validate(manifest),
        )
    store_package(state, definition)
    proof = native(state)
    apply(state, proof["native_review_id"])
    state.native_id = proof["native_review_id"]
    source = issue_preparation(state)
    preparation_checkpoint(state, source, "begin")
    preparation_checkpoint(
        state,
        source,
        "finish",
        receipt=sign_metadata(
            SECRET,
            "preparation_result",
            {
                "version": 1,
                "preparation_id": source["preparation_id"],
                "lifecycle_sha256": hashlib.sha256(
                    canonical(prepared_lifecycle(source, SECRET))
                ).hexdigest(),
                "outcome": "prepared_not_started",
            },
        ),
    )
    state.source = source
    state.subject_version = version
    return state


@pytest.mark.parametrize("checkpoint_prepared", [6, 7], indirect=True)
@pytest.mark.parametrize(
    "drift", ["none", "checkpoint_bound", "policy_scope", "future", "boolean", "string"]
)
def test_mixed_checkpoint_grant_preserves_exact_historical_start_consent(
    checkpoint_prepared, drift
):
    state = checkpoint_prepared
    ticket = issue(state, state.source)
    checkpoint(state, ticket, "begin")
    with state.keys.locked() as key, Session(state.engine) as db, db.begin():
        row = db.get(Grant, 1)
        value = authority._load(db, key, "grant", row, 1)
        assert value["data"]["subject"]["subject_version"] == state.subject_version
        if drift == "checkpoint_bound":
            for scope in value["data"]["subject"]["checkpoints"]:
                scope["declaration"]["max_value_bytes"] += 1
        elif drift == "policy_scope":
            value["data"]["policy"]["allowed_scopes"].append("checkpoint:foreign:read")
        elif drift != "none":
            value["data"]["subject"]["subject_version"] = {
                "future": 8, "boolean": True, "string": str(state.subject_version)
            }[drift]
        if drift != "none":
            # Deliberately authenticated malformed metadata in a disposable DB:
            # parsing and exact comparison must reject it even with a valid seal.
            authority._save(db, key, "grant", row, value)
    if drift != "none":
        with pytest.raises((authority.AuthorityManagementError, ValueError)):
            checkpoint(state, ticket, "check")
        assert journal(state, ticket)["state"] == "execution_unconfirmed"
        with Session(state.engine) as db:
            installation = db.get(Installation, 1)
            assert not installation.enabled and installation.authority_mode == "review_required"
        return
    assert checkpoint(state, ticket, "check") == {"state": "execution_unconfirmed"}
    assert checkpoint(state, ticket, "finish", receipt=receipt(ticket)) == {
        "state": "active_review_required"
    }
    assert not state.manager.inspect(1)["grant_effective"]


@pytest.mark.parametrize(
    "changes",
    [
        {"confirm_start_prepared_service": False},
        {"confirm_start_prepared_service": 1},
        {"expected_grant_record_revision": "f" * 32},
        {"service_uid": 0},
        {"service_gid": 0},
        {"coordinator_uid": 1200},
        {"actor_token": "invalid"},
        {"transport_secret": b"x" * 32},
        {"source_preparation_id": "f" * 32},
    ],
)
def test_bad_consent_or_source_is_atomic_and_does_not_reserve_preparation(
    prepared, changes
):
    state = prepared
    with pytest.raises((authority.AuthorityManagementError, ValueError, KeyError)):
        issue(state, state.source, **changes)
    assert "activation_id" not in journal(state, state.source)["data"]
    with Session(state.engine) as db:
        assert db.get(Installation, 1).authority_mode == "enforced"


def test_ticket_and_prepared_source_are_one_use_even_before_begin(prepared):
    state = prepared
    ticket = issue(state, state.source)
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        issue(state, state.source, request_id=ticket["preparation_id"])
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        issue(state, state.source)
    checkpoint(state, ticket, "begin")
    with pytest.raises(authority.AuthorityManagementError):
        checkpoint(state, ticket, "begin")
    checkpoint(state, ticket, "abort")
    assert journal(state, ticket)["state"] == "activation_unconfirmed"
    apply(state, state.native_id)
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        issue(state, state.source)


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
        "enable",
        "new_grant",
        "source_seal",
        "source_reservation",
        "expired",
        "boot",
    ],
)
def test_each_post_begin_phase_rechecks_current_actor_and_exact_consent(
    prepared, drift, monkeypatch
):
    state = prepared
    ticket = issue(state, state.source)
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
    elif drift == "source_reservation":
        with state.keys.locked() as key, Session(state.engine) as db, db.begin():
            row = db.get(Action, state.source["preparation_id"])
            value = authority._load(db, key, "action", row, row.request_id)
            value["data"]["activation_id"] = identity()
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
                    .where(Action.request_id == state.source["preparation_id"])
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
                            "enable": {"enabled": True, "status": "active"},
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
    # Changed key/generation correctly makes seals unreadable. Read only the
    # stored state to prove neither refused phase wrote a completion; do not
    # interpret this unsigned diagnostic read as authority.
    with Session(state.engine) as db:
        assert (
            json.loads(db.get(Action, ticket["preparation_id"]).payload)["state"]
            == "execution_unconfirmed"
        )


@pytest.mark.parametrize(
    "change",
    [
        {"database_path": "/foreign"},
        {"version": True},
        {"service_uid": True},
        {"action": "prepare_migrated_schema"},
        {"deadline_ms": 9007199254740990},
    ],
)
def test_closed_activation_wire_rejects_ambiguous_or_unbounded_fields(prepared, change):
    ticket = issue(prepared, prepared.source)
    with pytest.raises(ValidationError):
        _RelationalActivationTicket.model_validate(dict(ticket, **change))


def test_activation_is_not_preparation_or_business_sql_authority(prepared):
    ticket = issue(prepared, prepared.source)
    with pytest.raises(ValidationError):
        _preparation_ticket(ticket)
    with pytest.raises(ValidationError):
        _RelationalActivationResult.model_validate(
            sign_metadata(
                SECRET,
                "activation_result",
                dict(receipt(ticket), outcome="prepared_not_started"),
            )
        )
    with pytest.raises(authority.AuthorityManagementError):
        checkpoint(prepared, ticket, "finish", receipt=receipt(ticket))
    checkpoint(prepared, ticket, "begin")
    with pytest.raises(authority.AuthorityManagementError, match="receipt_changed"):
        checkpoint(
            prepared,
            ticket,
            "finish",
            receipt=receipt(ticket, lifecycle_sha256="0" * 64),
        )


def test_failed_begin_write_rolls_back_epoch_and_mode_together(prepared, monkeypatch):
    state = prepared
    ticket = issue(state, state.source)
    with Session(state.engine) as db:
        epoch = db.get(Installation, 1).authority_epoch
    original = authority._save

    def fail(db, key, kind, row, value):
        if value["record_id"] == ticket["preparation_id"]:
            raise OSError("Durable begin failed")
        return original(db, key, kind, row, value)

    with monkeypatch.context() as patch:
        patch.setattr(authority, "_save", fail)
        with pytest.raises((OSError, AuthorityReviewKeyError)):
            checkpoint(state, ticket, "begin")
    with Session(state.engine) as db:
        row = db.get(Installation, 1)
        assert (row.authority_epoch, row.authority_mode, row.enabled) == (
            epoch,
            "enforced",
            False,
        )
    assert journal(state, ticket)["state"] == "recorded"


@pytest.mark.parametrize("running", [False, True])
@pytest.mark.parametrize(
    "problem",
    [
        "none",
        "root",
        "wrong_group",
        "enabled",
        "job",
        "inactive",
        "missing",
        "process_root",
    ],
)
def test_systemd_adapter_checks_fixed_unit_and_kernel_identity(
    monkeypatch, running, problem
):
    fields = {
        "User": "1200",
        "Group": "1201",
        "MainPID": "42" if running else "0",
        "LoadState": "loaded",
        "ActiveState": "active" if running else "inactive",
        "UnitFileState": "disabled",
        "Job": "0",
    }
    changes = {
        "root": {"User": "0"},
        "wrong_group": {"Group": "0"},
        "enabled": {"UnitFileState": "enabled"},
        "job": {"Job": "scheduled"},
        "inactive": {"ActiveState": "inactive" if running else "active"},
        "missing": {"LoadState": "not-found"},
    }
    fields.update(changes.get(problem, {}))
    monkeypatch.setattr(
        helper.subprocess,
        "run",
        lambda argv, **kw: (
            SimpleNamespace(
                stdout="\n".join(name + "=" + value for name, value in fields.items())
            )
            if argv[:2] == ["/usr/bin/systemctl", "show"]
            and "3mm-application-extension@aaaaaaaaaaaaaaaaaaaaaaaa.service" in argv
            else pytest.fail("Unexpected service command")
        ),
    )
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *a, **kw: "Uid:\t"
        + ("0 0 0 0" if problem == "process_root" else "1200 1200 1200 1200")
        + "\nGid:\t1201 1201 1201 1201\n",
    )
    supervisor = helper.PreparedServiceSupervisor()
    if problem == "none" or (problem == "process_root" and not running):
        supervisor.verify_identity("a" * 24, 1200, 1201, running=running)
    else:
        with pytest.raises(helper.RelationalActivationError):
            supervisor.verify_identity("a" * 24, 1200, 1201, running=running)


def test_systemd_start_does_not_enable_or_restart(monkeypatch):
    calls = []
    supervisor = helper.PreparedServiceSupervisor()
    monkeypatch.setattr(
        supervisor, "_run", lambda args, identifier: calls.append((args, identifier))
    )
    supervisor.start("a" * 24)
    assert calls == [(["start"], "a" * 24)]


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(prefix="3mm-ac-") as directory:
        yield Path(directory)


class ProcessSupervisor:
    """Disposable actual process, no systemd/live unit/account modifications."""

    def __init__(self, state):
        self.state, self.process, self.starts = state, None, 0

    def recover_disabled(self, instance):
        assert instance == self.state.instance.name
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.communicate(timeout=3)
            self.process = None

    def verify_identity(self, instance, uid, gid, *, running):
        assert instance == self.state.instance.name and (uid, gid) == (1200, 1201)
        if not running:
            assert self.process is None
            return
        assert self.process.poll() is None
        status = Path(f"/proc/{self.process.pid}/status").read_text()
        values = {
            line.split(":")[0]: tuple(int(x) for x in line.split(":")[1].split())
            for line in status.splitlines()
            if line.startswith(("Uid:", "Gid:"))
        }
        assert values == {"Uid": (1200,) * 4, "Gid": (1201,) * 4}

    def start(self, instance):
        state = self.state
        assert instance == state.instance.name and self.starts == 0
        with Session(state.engine) as db:
            row = db.get(Installation, 1)
            assert not row.enabled and row.authority_mode == "review_required"
        self.starts += 1
        sdk_root = Path(__file__).resolve().parents[2]
        launch = (
            "import sys; sys.path.insert(0," + repr(str(sdk_root)) + "); "
            "from pathlib import Path; from three_mm_runtime.application_host import serve; "
            "serve("
            + repr(instance)
            + ",Path("
            + repr(str(state.runtime))
            + "),Path("
            + repr(str(state.transport_keys))
            + "),1201)"
        )
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-c", launch],
            user=1200,
            group=1201,
            extra_groups=[],
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=state.data,
            env={"PATH": "/usr/bin:/bin"},
        )
        deadline = time.monotonic() + 10
        while not (state.instance / "run/service.sock").is_socket():
            if self.process.poll() is not None:
                raise AssertionError(self.process.communicate(timeout=2)[1].decode())
            assert time.monotonic() < deadline
            time.sleep(0.05)


@pytest.fixture
def physical(migratable, monkeypatch):
    state = migratable
    monkeypatch.setenv("THREE_MM_PLATFORM_RUNTIME_SOCKET", str(state.runtime / "platform/platform.sock"))
    package(state, "read_write")
    state.source = migration_ticket(state)
    run(state, state.source)  # Actual non-root migrations, signed prepared record.
    for path in (state.runtime, state.transport_keys):
        os.chown(path, 0, 1201)
        path.chmod(0o750)
    os.chown(state.transport_keys / (state.instance.name + ".key"), 0, 1201)
    state.platform = state.runtime / "platform"
    state.platform.mkdir()
    os.chown(state.platform, 0, 1201)
    state.platform.chmod(0o750)
    import backend.database

    monkeypatch.setattr(
        backend.database, "SessionLocal", sessionmaker(bind=state.engine)
    )
    state.server = ApplicationPlatformServer(
        state.platform / "platform.sock", state.transport_keys
    , allowed_actions=COMPATIBILITY_ACTIONS)
    state.server.start()
    os.chown(state.server.socket_path, 0, 1201)
    state.settings = ApplicationRuntimeSettings(
        root=state.runtime,
        key_root=state.transport_keys,
        helper_socket=state.runtime / "unused.sock",
    )
    state.actual_supervisor = ProcessSupervisor(state)
    try:
        yield state
    finally:
        state.actual_supervisor.recover_disabled(state.instance.name)
        state.server.stop()


def start(state, ticket, **changes):
    return helper.activate_prepared_relational_service(
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


@ROOT_ONLY
def test_real_nonroot_activation_without_replay_rekey_or_fake_active_version(
    physical, monkeypatch
):
    state = physical
    ticket = issue(state, state.source)
    before = {
        path: path.read_bytes()
        for path in (
            state.database,
            state.instance / "relational.json",
            state.instance / "active.json",
            state.data / "migration-imported",
            state.transport_keys / (state.instance.name + ".key"),
        )
    }
    monkeypatch.setattr(
        ApplicationStorage,
        "migrate",
        lambda *a: pytest.fail("Activation imported migrations as Root"),
    )
    result = start(state, ticket)
    assert result["outcome"] == "active_review_required"
    assert state.actual_supervisor.starts == 1
    assert json.loads((state.data / "factory.json").read_text()) == {
        "uid": 1200,
        "denied": [True, True, True],
    }
    assert all(path.read_bytes() == payload for path, payload in before.items())
    with pytest.raises(ApplicationGatewayError):
        invoke(state, "inspect")  # Health/factory success did not grant SQL.
    apply(state, state.native_id)
    assert invoke(state, "inspect") == {"values": ["preserved"]}
    assert invoke(state, "mutate", {"value": "after fresh review"}) == {
        "value": "after fresh review"
    }
    assert invoke(state, "inspect") == {"values": ["after fresh review"]}
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
@pytest.mark.parametrize("lost_phase", ["begin", "finish"])
def test_lost_ack_preserves_witness_fences_rights_and_never_restarts(
    physical, lost_phase
):
    state = physical
    ticket = issue(state, state.source)
    before = (state.instance / "relational.json").read_bytes()

    def lose(ticket, phase, **kw):
        result = checkpoint(state, ticket, phase, **kw)
        if phase == lost_phase:
            raise OSError("ACK lost AFTER durable Core commit")
        return result

    with pytest.raises(helper.RelationalActivationError, match="unconfirmed"):
        start(state, ticket, checkpoint=lose)
    assert state.actual_supervisor.starts == (0 if lost_phase == "begin" else 1)
    assert state.actual_supervisor.process is None
    assert (state.instance / "relational.json").read_bytes() == before
    marker = state.helper_state / (
        "relational-activation-" + state.instance.name + ".json"
    )
    assert marker.is_file() and marker.stat().st_mode & 0o777 == 0o600
    assert (
        SECRET.hex() not in marker.read_text() and state.token not in marker.read_text()
    )
    assert journal(state, ticket)["state"] == "activation_unconfirmed"
    with Session(state.engine) as db:
        row = db.get(Installation, 1)
        assert not row.enabled and row.authority_mode == "review_required"
    with pytest.raises(helper.RelationalActivationError, match="recovery review"):
        start(state, ticket)


@ROOT_ONLY
@pytest.mark.parametrize(
    "problem", ["key", "wheel", "configuration", "owner", "pending", "key_traversal"]
)
def test_root_refuses_changed_preparation_before_any_start_or_epoch_change(
    physical, problem
):
    state = physical
    ticket = issue(state, state.source)
    if problem == "key":
        (state.transport_keys / (state.instance.name + ".key")).write_bytes(b"x" * 32)
    elif problem == "wheel":
        (
            state.instance / "releases" / ticket["package_sha256"] / "service.whl"
        ).write_bytes(b"changed")
    elif problem == "configuration":
        active = state.instance / "active.json"
        value = json.loads(active.read_text())
        value["entrypoint"] = "unreviewed.service:create_service"
        active.write_text(json.dumps(value))
    elif problem == "owner":
        os.chown(state.database, 0, 1201)
    elif problem == "key_traversal":
        state.transport_keys.chmod(0o700)
    else:
        (state.instance / ".database-uncertain.rollback").mkdir()
    with pytest.raises((helper.RelationalActivationError, ValueError)):
        start(state, ticket)
    assert state.actual_supervisor.starts == 0
    assert journal(state, ticket)["state"] == "recorded"
    with Session(state.engine) as db:
        assert db.get(Installation, 1).authority_mode == "enforced"


@ROOT_ONLY
def test_generic_activation_stays_denied_even_for_a_prepared_database(physical):
    from three_mm_runtime.application_activation import ApplicationActivationError

    with pytest.raises(ApplicationActivationError, match="relational"):
        activate_application_package(
            physical.archive,
            physical.validated.sha256,
            root=physical.runtime,
            key_root=physical.transport_keys,
            configuration=physical.configuration,
        )
    assert physical.actual_supervisor.starts == 0


@ROOT_ONLY
@pytest.mark.parametrize("problem", ["health", "revoked", "abort_ack", "stop_ack"])
def test_failed_start_health_or_revocation_retains_evidence_without_sql_rollback(
    physical, monkeypatch, problem
):
    state = physical
    ticket = issue(state, state.source)
    database_before = state.database.read_bytes()
    original_stop = state.actual_supervisor.recover_disabled
    stops = []

    def stop(instance):
        stops.append(instance)
        if problem == "stop_ack" and len(stops) > 1:
            raise OSError("Stop outcome unavailable")
        return original_stop(instance)

    def health(*a, **kw):
        if problem == "revoked":
            state.manager.revoke(
                1,
                actor_token=state.token,
                request_id=identity(),
                expected_revision=ticket["grant_record_revision"],
            )
        else:
            raise helper.RelationalActivationError("Health failed")

    def uncertain(ticket, phase, **kw):
        if problem == "abort_ack" and phase == "abort":
            raise OSError("Core abort outcome unavailable")
        return checkpoint(state, ticket, phase, **kw)

    monkeypatch.setattr(state.actual_supervisor, "recover_disabled", stop)
    monkeypatch.setattr(helper, "_wait_for_health", health)
    with pytest.raises(helper.RelationalActivationError, match="unconfirmed"):
        start(state, ticket, checkpoint=uncertain)
    assert state.actual_supervisor.starts == 1
    assert state.database.read_bytes() == database_before
    assert (
        state.helper_state / ("relational-activation-" + state.instance.name + ".json")
    ).is_file()
    with Session(state.engine) as db:
        row = db.get(Installation, 1)
        assert (
            not row.enabled
            and row.status == "disabled"
            and row.authority_mode == "review_required"
        )
    assert journal(state, ticket)["state"] == (
        "execution_unconfirmed"
        if problem in {"abort_ack", "revoked"}
        else "activation_unconfirmed"
    )
    # Even an unconfirmed live stop does not make a disabled grant effective.
    if problem == "stop_ack":
        assert state.actual_supervisor.process is not None
        apply(state, state.native_id)
        assert not state.manager.inspect(1)["grant_effective"]
    monkeypatch.setattr(state.actual_supervisor, "recover_disabled", original_stop)


@ROOT_ONLY
def test_real_from_absence_registration_preparation_activation_without_sql_enable(
    registration_catalog, tmp_path, monkeypatch
):
    state = registration_catalog
    # TemporaryDirectory starts 0700. Make only this disposable test parent
    # traversable to the actual application UID, as the installer layout is.
    tmp_path.chmod(0o755)
    definition = state.validated.application_extension.model_dump(mode="json")
    manifest = state.validated.manifest.model_dump(mode="json")
    # Build the test service BEFORE registration/review/preparation, not by
    # mutating protected metadata or the reviewed wheel after preparation.
    with zipfile.ZipFile(state.archive) as archive:
        old_wheel = archive.read(definition["service"]["artifact"])
    wheel = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(old_wheel)) as old,
        zipfile.ZipFile(wheel, "w") as target,
    ):
        for entry in old.namelist():
            target.writestr(
                entry, SERVICE if entry.endswith("/service.py") else old.read(entry)
            )
    definition["service"]["artifact_sha256"] = hashlib.sha256(
        wheel.getvalue()
    ).hexdigest()
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("application-extension.json", json.dumps(definition))
        archive.writestr(definition["service"]["artifact"], wheel.getvalue())
    state.validated = validate_module_package(blob.getvalue())
    state.archive = state.root / "modules" / (state.validated.sha256 + ".zip")
    state.archive.write_bytes(blob.getvalue())
    with state.engine.begin() as db:
        db.execute(
            update(ModulePackage).values(
                sha256=state.validated.sha256,
                manifest=manifest,
                size_bytes=len(blob.getvalue()),
            )
        )
    registered = register(state)
    assert registered["active_version"] is None and registered["installation_id"] == 1
    approve_registration(state, 1)
    state.native_id = state.manager.inspect(1)["native_reviews"][0]["native_review_id"]
    state.runtime, state.transport_keys, state.helper_state = [
        tmp_path / name for name in ("runtime", "keys", "helper-state")
    ]
    for path in (state.runtime, state.transport_keys, state.helper_state):
        path.mkdir(mode=0o750)
    os.chown(state.runtime, 0, 1201)
    os.chown(state.transport_keys, 0, 1201)
    monkeypatch.setattr(locks, "RELEASE_MUTATION_LOCK", tmp_path / "release.lock")
    expected = state.manager.inspect(1)["grant_record_revision"]

    def issue_namespace(**kw):
        from backend.services.application_relational_lifecycle import (
            issue_namespace_preparation,
        )

        return issue_namespace_preparation(
            state.manager,
            1,
            actor_token=state.token,
            expected_grant_record_revision=expected,
            confirm_fresh_owned_namespace=True,
            service_uid=1200,
            service_gid=1201,
            coordinator_uid=1202,
            **kw,
        )

    def issue_migration(**kw):
        from backend.services.application_relational_lifecycle import (
            issue_migrated_schema_preparation,
        )

        state.source = issue_migrated_schema_preparation(
            state.manager,
            1,
            actor_token=state.token,
            expected_grant_record_revision=expected,
            confirm_owned_business_migrations=True,
            **kw,
        )
        return state.source

    def prepared_checkpoint(ticket, phase, **kw):
        from backend.services.application_relational_lifecycle import (
            preparation_checkpoint,
        )

        return preparation_checkpoint(
            state.manager, 1, ticket, phase, actor_token=state.token, **kw
        )

    class Stopped:
        def stop(self, instance):
            pass  # Disposable absence: no unit or process exists yet.

    prepare_fresh_relational_installation(
        state.archive,
        configuration={},
        root=state.runtime,
        key_root=state.transport_keys,
        state_root=state.helper_state,
        service_uid=1200,
        service_gid=1201,
        coordinator_uid=1202,
        confirm_fresh_owned_namespace=True,
        confirm_owned_business_migrations=True,
        issue_namespace=issue_namespace,
        issue_migration=issue_migration,
        checkpoint=prepared_checkpoint,
        supervisor=Stopped(),
    )
    with Session(state.engine) as db:
        row = db.get(Installation, 1)
        assert row.active_version is None and not row.enabled
        state.instance = state.runtime / row.instance_id
    state.data = state.instance / "data"
    state.database = state.data / "state.sqlite3"
    state.configuration = {}
    state.activation_secret = (
        state.transport_keys / (state.instance.name + ".key")
    ).read_bytes()
    state.actual_supervisor = ProcessSupervisor(state)
    prepared_bytes = (state.instance / "relational.json").read_bytes()
    try:
        ticket = issue(state, state.source)
        assert start(state, ticket)["outcome"] == "active_review_required"
        with Session(state.engine) as db:
            row = db.get(Installation, 1)
            assert row.active_version == definition["version"] and row.enabled
            assert row.authority_mode == "review_required"
        assert (state.instance / "relational.json").read_bytes() == prepared_bytes
        assert json.loads((state.data / "factory.json").read_text())["uid"] == 1200
        assert state.actual_supervisor.starts == 1
    finally:
        state.actual_supervisor.recover_disabled(state.instance.name)
