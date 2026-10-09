"""Actual helper ticket checks/receipts, with systemd effects replaced in tests."""

from contextlib import nullcontext
from functools import partial
import json
import os
import sqlite3
from types import SimpleNamespace

import pytest

from three_mm_runtime import application_activation, application_lifecycle as fencing, update_helper
from three_mm_runtime.update_helper_client import UpdateHelperClient


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    database = tmp_path / "core.db"
    state = tmp_path / "helper"
    state.mkdir(mode=0o700)
    with sqlite3.connect(database) as db:
        db.executescript("""
            CREATE TABLE core_authority_guard(singleton_id INTEGER PRIMARY KEY, generation TEXT, revision INTEGER);
            CREATE TABLE module_packages(id INTEGER PRIMARY KEY, sha256 TEXT);
            CREATE TABLE application_extension_installations(
                id INTEGER PRIMARY KEY, module_package_id INTEGER, module_id TEXT,
                instance_id TEXT, authority_incarnation TEXT, authority_epoch TEXT,
                status TEXT, enabled INTEGER, configuration TEXT);
        """)
        db.execute("INSERT INTO core_authority_guard VALUES (1, ?, 1)", ("f" * 32,))
        db.execute("INSERT INTO module_packages VALUES (1, ?)", ("a" * 64,))
        db.execute("INSERT INTO application_extension_installations VALUES (1, 1, ?, ?, ?, ?, ?, 0, ?)",
            ("org.example.app", "b" * 24, "c" * 32, "d" * 32, "activating", '{"PRIVATE":"do-not-record"}'))
    payload = dict(action="activate_application_extension", sha256="a" * 64,
        requested_by_user_id=7, configuration={"PRIVATE": "do-not-record"},
        lifecycle=dict(installation_id=1, module_id="org.example.app", instance_id="b" * 24,
                       incarnation="c" * 32, epoch="d" * 32, guard_generation="f" * 32))
    # Only native locking is substituted on Windows. Linux CI uses real flock,
    # including busy/restart fencing; temp fixtures need not be owned by root.
    if os.name != "posix":
        monkeypatch.setattr(fencing, "_runtime_lock", lambda *_a, **_kw: nullcontext())
        monkeypatch.setattr(fencing, "_release_lock", lambda **_kw: nullcontext())
    monkeypatch.setattr(fencing, "RELEASE_MUTATION_LOCK", tmp_path / "release-mutation.lock")
    operation = partial(fencing.application_lifecycle_operation,
                        database=database, state_root=state, enforce_permissions=False)
    monkeypatch.setattr(update_helper, "application_lifecycle_operation",
        lambda value, **_kw: operation(value))
    common = dict(stage_root=tmp_path / "stage", state_root=state,
        allowlist=tmp_path / "allowlist", status_file=tmp_path / "status",
        application_database=database, application_root=tmp_path / "apps",
        application_key_root=tmp_path / "keys", application_upload_root=tmp_path / "uploads")
    return SimpleNamespace(database=database, state=state, payload=payload,
                           operation=operation, common=common)


@pytest.mark.parametrize("failure", [False, True])
def test_ticket_is_consumed_before_effect_and_never_replayed_after_restart(runtime, failure):
    s = runtime
    with pytest.raises(RuntimeError) if failure else nullcontext():
        with s.operation(s.payload):
            # The helper's read snapshot/connection must be closed before effects.
            with sqlite3.connect(s.database, timeout=0.1) as db:
                db.execute("UPDATE application_extension_installations SET enabled = enabled")
            receipt = next(s.state.glob("lifecycle-*.json")).read_text()
            assert "do-not-record" not in receipt and "PRIVATE" not in receipt
            assert json.loads(receipt)["epoch"] == s.payload["lifecycle"]["epoch"]
            if failure:
                raise RuntimeError("process failed after admission")
    # New context/connection emulates a new helper process, not an in-memory flag.
    with pytest.raises(fencing.ApplicationLifecycleError):
        with s.operation(s.payload):
            pytest.fail("replayed uncertain action")


@pytest.mark.parametrize("column,value", [
    ("authority_incarnation", "e" * 32), ("authority_epoch", "e" * 32),
    ("instance_id", "e" * 24), ("module_id", "org.example.other"),
    ("status", "recovering"), ("enabled", 1), ("configuration", '{}'),
])
def test_delayed_request_is_rejected_against_fresh_committed_state(runtime, column, value):
    s = runtime
    with sqlite3.connect(s.database) as db:
        db.execute(f"UPDATE application_extension_installations SET {column} = ?", (value,))
    with pytest.raises(fencing.ApplicationLifecycleError):
        with s.operation(s.payload):
            pytest.fail("stale request reached runtime")
    assert not list(s.state.glob("lifecycle-*.json"))


def test_request_digest_cannot_turn_same_ticket_into_another_operation(runtime):
    s = runtime
    with s.operation(s.payload):
        pass
    with sqlite3.connect(s.database) as db:
        db.execute("UPDATE application_extension_installations SET status = 'disabling'")
    payload = dict(action="disable_application_extension", instance_id="b" * 24,
                   requested_by_user_id=7, lifecycle=s.payload["lifecycle"])
    with pytest.raises(fencing.ApplicationLifecycleError):
        with s.operation(payload):
            pytest.fail("ticket reused for another action")


@pytest.mark.parametrize("statement", ["DELETE FROM core_authority_guard",
    "UPDATE core_authority_guard SET generation = 'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'"])
def test_missing_or_replaced_guard_rejects_pending_helper_ticket(runtime, statement):
    with sqlite3.connect(runtime.database) as db:
        db.execute(statement)
    with pytest.raises(fencing.ApplicationLifecycleError):
        with runtime.operation(runtime.payload):
            pytest.fail("accepted foreign guard")


def test_recovery_uses_new_ticket_and_old_queued_activation_cannot_follow_it(runtime, monkeypatch):
    s = runtime
    with s.operation(s.payload):
        pass
    with sqlite3.connect(s.database) as db:
        db.execute("UPDATE application_extension_installations SET status = 'recovering', authority_epoch = ?", ("e" * 32,))
    payload = dict(action="recover_application_extension", instance_id="b" * 24,
        requested_by_user_id=7, lifecycle=dict(s.payload["lifecycle"], epoch="e" * 32))
    commands = []

    def run(command, **kwargs):
        assert kwargs["check"] is True and "shell" not in kwargs
        commands.append(command)
        return SimpleNamespace(stdout="LoadState=loaded\nActiveState=inactive\nSubState=dead\nUnitFileState=disabled\nMainPID=0\nJob=\n")

    monkeypatch.setattr(application_activation.subprocess, "run", run)
    result = update_helper._handle_request(payload, **s.common)
    assert result == dict(ok=True, status="disabled", instance_id="b" * 24,
                          lifecycle=payload["lifecycle"], quiescent=True)
    assert commands[0] == ["/usr/bin/systemctl", "disable", "--now", "3mm-application-extension@" + "b" * 24 + ".service"]
    assert commands[1][1] == "show" and len(commands) == 2
    monkeypatch.setattr(update_helper, "_service_ids", lambda *_a: (1, 1))
    monkeypatch.setattr(update_helper, "activate_application_package", lambda *_a, **_kw: pytest.fail("late activation"))
    assert update_helper._handle_request(s.payload, **s.common)["ok"] is False
    assert len(commands) == 2


@pytest.mark.parametrize("line", ["ActiveState=active", "UnitFileState=enabled", "MainPID=42", "Job=123", "LoadState=not-found", "SubState=running"])
def test_systemd_recovery_requires_positive_quiescence_evidence(monkeypatch, line):
    good = dict(LoadState="loaded", ActiveState="inactive", SubState="dead", UnitFileState="disabled", MainPID="0", Job="")
    key, value = line.split("=", 1)
    good[key] = value
    monkeypatch.setattr(application_activation.subprocess, "run", lambda *_a, **_kw:
        SimpleNamespace(stdout="\n".join(f"{key}={value}" for key, value in good.items())))
    with pytest.raises(application_activation.ApplicationActivationError):
        application_activation.SystemdApplicationSupervisor().recover_disabled("b" * 24)


def test_missing_database_is_not_created(runtime):
    missing = runtime.database.with_name("missing.db")
    with pytest.raises(fencing.ApplicationLifecycleError):
        with runtime.operation(runtime.payload, database=missing):
            pytest.fail("initialized missing authority")
    assert not missing.exists()


def test_corrupt_receipt_fails_closed(runtime):
    (runtime.state / ("lifecycle-" + "b" * 24 + ".json")).write_text('{}')
    with pytest.raises(fencing.ApplicationLifecycleError):
        with runtime.operation(runtime.payload):
            pytest.fail("ignored corrupt receipt")


@pytest.mark.skipif(os.name != "posix", reason="Linux flock boundary")
def test_busy_native_helper_lock_prevents_overlapping_effect(runtime):
    import fcntl
    s = runtime
    path = s.state / "application-lifecycle.lock"
    with path.open("w") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(fencing.ApplicationLifecycleError):
            with s.operation(s.payload):
                pytest.fail("overlapping effect")
    assert not list(s.state.glob("lifecycle-*.json"))
    with s.operation(s.payload):
        pass


@pytest.mark.skipif(os.name != "posix", reason="Linux release flock boundary")
def test_release_restore_reset_lock_blocks_lifecycle_before_receipt(runtime):
    import fcntl

    with fencing.RELEASE_MUTATION_LOCK.open("w") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(fencing.ApplicationLifecycleError):
            with runtime.operation(runtime.payload):
                pytest.fail("lifecycle crossed offline recovery")
    assert not list(runtime.state.glob("lifecycle-*.json"))
    with runtime.operation(runtime.payload):
        with pytest.raises(BlockingIOError):
            with fencing.RELEASE_MUTATION_LOCK.open("r+") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_private_helper_rejects_unfenced_legacy_actions(runtime):
    payload = dict(runtime.payload)
    payload.pop("lifecycle")
    assert update_helper._handle_request(payload, **runtime.common)["ok"] is False


def test_disconnected_caller_does_not_kill_helper_or_repeat_work(monkeypatch):
    calls = []
    monkeypatch.setattr(update_helper, "_handle_request", lambda *_a, **_kw:
                        calls.append("effect") or dict(ok=True, status="disabled"))

    class Connection:
        def settimeout(self, value):
            assert value == 10
        def recv(self, _limit):
            return b'{"action":"test"}\n'
        def sendall(self, _value):
            raise BrokenPipeError()

    update_helper._serve_connection(Connection())
    assert calls == ["effect"]


def test_client_transports_private_ticket_and_recovery_evidence(monkeypatch, tmp_path):
    captured = []
    client = UpdateHelperClient(tmp_path / "unused.sock")
    context = {"epoch": "e" * 32}
    monkeypatch.setattr(client, "_request", lambda payload, **kwargs:
        captured.append((payload, kwargs)) or dict(status="disabled", lifecycle=context))
    result = client.recover_application_extension("b" * 24, 7, context)
    assert captured[0][0]["lifecycle"] == context
    assert captured[0][1] == {"expected_status": "disabled"}
    assert result["lifecycle"] == context
