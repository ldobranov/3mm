"""Actual Core CLI/UID writer -> Root -> non-root repeated start and recovery.

Disposable roots only. No live accounts/units, SQL enable or fabricated grants.
"""

import json
import os
import socket
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from backend.services import application_authority_management as authority
from backend.services.application_relational_admin_worker import dispatch
from backend.tests.test_application_relational_activation import ProcessSupervisor
from backend.tests.test_application_relational_activation_control import (
    catalog,
    deployed,
    initial,
    managed_installed,
    original_production,
    prepared,
    source_installed,
    source_subject,
    tmp_path,
)
from backend.tests.test_application_relational_preparation import ROOT_ONLY, identity
from backend.tests.test_application_relational_recovery_control import (
    cli,
)
from backend.tests.test_application_relational_recovery_control import handle as stop
from backend.tests.test_application_relational_recovery_control import (
    inspect as inspect_start,
)
from backend.tests.test_application_relational_recovery_control import (
    interrupted,
    metadata_rows,
)
from backend.tests.test_application_relational_recovery_control import (
    request as stop_request,
)
from backend.tests.test_application_relational_recovery_control import (
    snapshot,
)
from three_mm_application_sdk.relational_wire import canonical
from three_mm_runtime import update_helper
from three_mm_runtime.application_relational_control import reactivation_request
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Actual Core/OS peer")


def inspect(state, token=None):
    process = cli(
        state,
        [
            "inspect-relational-recovery",
            "--installation-id",
            "1",
            "--source-recovery-id",
            state.recovery_id,
        ],
        token=token,
    )
    assert process.returncode == 0, process.stderr.decode()
    assert state.token.encode() not in process.stdout + process.stderr
    return json.loads(process.stdout)


def review(state):
    # Test-only invocation of NORMAL human review/approve/apply in the actual
    # Core UID. No SQL fabrication, extra production dialect or Root key access.
    script = """
import json, sys, uuid
from backend.database import engine
from backend.services.application_authority_management import configured_manager
manager = configured_manager(engine)
token = sys.stdin.buffer.readline().decode().strip()
status = manager.inspect(1)
plan = manager.create_review(1, actor_token=token, request_id=uuid.uuid4().hex,
    native_review_id=status['native_reviews'][0]['native_review_id'], scopes=status['scopes'])
for decision in ('approve', 'apply'):
    result = manager.decide(1, actor_token=token, request_id=uuid.uuid4().hex,
        plan_id=plan['plan_id'], expected_revision=plan['revision'],
        fingerprint=plan['fingerprint'], decision=decision)
    plan = {**plan, **result}
print(json.dumps(manager.inspect(1)))
"""
    process = subprocess.run(
        [sys.executable, "-c", script],
        input=state.token.encode() + b"\n",
        capture_output=True,
        timeout=30,
        user=1202,
        group=1203,
        extra_groups=(),
        start_new_session=True,
        env=state.environment,
    )
    assert process.returncode == 0, process.stderr.decode()
    assert state.token.encode() not in process.stdout + process.stderr
    return json.loads(process.stdout)


@pytest.fixture
def recovered(interrupted):
    state = interrupted
    value = stop_request(state)
    result = stop(state, value)
    assert result["status"] == "stopped_review_required", (result, state.frames)
    state.recovery_id = value["request_id"]
    state.recovery_revision = inspect(state)["source_revision"]
    assert state.supervisor.process is None
    state.supervisor = ProcessSupervisor(state)
    state.frames.clear()
    return state


@pytest.fixture
def reviewed(recovered):
    state = recovered
    state.expected_grant = review(state)["grant_record_revision"]
    state.frames.clear()
    return state


def request(state, **changes):
    return {
        "action": "reactivate_application_relational",
        "installation_id": 1,
        "actor_token": state.token,
        "source_recovery_id": state.recovery_id,
        "expected_recovery_revision": state.recovery_revision,
        "expected_grant_record_revision": state.expected_grant,
        "request_id": identity(),
        "confirm_restart_stopped_prepared_service": True,
        **changes,
    }


def handle(state, value=None, **changes):
    return update_helper._handle_request(
        value or request(state),
        **{
            "relational_peer_uid": 1202,
            **state.arguments,
            **changes,
        },
    )


def wire(**changes):
    return request(
        SimpleNamespace(
            token="unit-test-token",
            recovery_id="a" * 32,
            recovery_revision="b" * 32,
            expected_grant="c" * 32,
        ),
        **changes,
    )


@ROOT_ONLY
def test_human_status_is_metadata_only_without_key_grant_or_process_effect(recovered):
    state = recovered
    before, rows = snapshot(state), metadata_rows(state)
    held = state.key_path.with_suffix(".held")
    assert not held.exists()
    state.key_path.rename(held)
    try:
        result = inspect(state)
    finally:
        held.rename(state.key_path)
    assert result == {
        "installation_id": 1,
        "source_recovery_id": state.recovery_id,
        "source_revision": state.recovery_revision,
        "source_state": "confirmed",
        "recovered_activation_id": state.source_activation_id,
        "latest_reactivation_id": None,
        "metadata_only": True,
        "permission_approval": "not_evaluated",
    }
    assert snapshot(state) == before and metadata_rows(state) == rows
    assert state.supervisor.starts == 0 and not state.frames
    assert handle(state)["error"] == "relational_reactivation_unconfirmed"
    assert state.frames == ["inspect_reactivation"]  # Stop did not regrant start.


@ROOT_ONLY
def test_actual_cli_peer_core_writer_restart_preserves_state_and_requires_review(
    reviewed,
):
    state = reviewed
    before = snapshot(state)
    with state.engine.connect() as db:
        grant = db.exec_driver_sql(
            "SELECT payload FROM application_authority_grants WHERE installation_id=1"
        ).scalar_one()
    path = state.helper_state.parent / "reactivation.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    os.chown(path, 0, 1203)
    path.chmod(0o660)
    server.listen(1)
    server.settimeout(15)
    errors, observed = [], []
    original = state.metadata._run

    def observe(arguments, **kw):
        frame = json.loads(kw["input"])
        if frame["action"] == "reactivation_checkpoint":
            assert (
                frame["expected_recovery_revision"]
                == frame["ticket"]["source_recovery_revision"]
            )
            assert frame["expected_recovery_revision"] != state.recovery_revision
            observed.append(frame["phase"])
            stale = dict(frame, expected_recovery_revision=state.recovery_revision)
            with pytest.raises(
                authority.AuthorityManagementError, match="reactivation_frame_changed"
            ):
                dispatch(None, stale, application_root=state.runtime)
        return original(arguments, **kw)

    state.metadata._run = observe

    def serve():
        try:
            connection, _ = server.accept()
            with connection:
                update_helper._serve_connection(connection, **state.arguments)
        except BaseException as exc:
            errors.append(type(exc).__name__)

    thread = threading.Thread(target=serve)
    thread.start()
    request_id = identity()
    try:
        process = cli(
            state,
            [
                "reactivate-relational",
                "--installation-id",
                "1",
                "--source-recovery-id",
                state.recovery_id,
                "--expected-recovery-revision",
                state.recovery_revision,
                "--expected-grant-record-revision",
                state.expected_grant,
                "--request-id",
                request_id,
                "--confirm-restart-stopped-prepared-service",
            ],
            THREE_MM_APPLICATION_HELPER_SOCKET=str(path),
        )
    finally:
        thread.join(timeout=95)
        server.close()
        state.metadata._run = original
    assert not thread.is_alive() and not errors
    assert process.returncode == 0, (process.stderr.decode(), state.frames)
    result = json.loads(process.stdout)
    assert result["status"] == "active_review_required"
    assert result["reactivation"]["preparation_id"] == request_id
    assert (
        result["permission_approval"] == "not_evaluated"
        and not result["boot_autostart_enabled"]
    )
    assert state.token.encode() not in process.stdout + process.stderr
    assert (
        state.frames
        == ["inspect_reactivation", "issue_reactivation"]
        + ["reactivation_checkpoint"] * 4
    )
    assert observed == ["authorize", "begin", "check", "finish"]
    state.supervisor.verify_identity(state.instance.name, 1200, 1201, running=True)
    assert state.supervisor.starts == 1 and snapshot(state) == before
    with state.engine.connect() as db:
        assert (
            db.exec_driver_sql(
                "SELECT payload FROM application_authority_grants WHERE installation_id=1"
            ).scalar_one()
            == grant
        )
        assert db.exec_driver_sql(
            "SELECT enabled,status,authority_mode,active_version FROM application_extension_installations WHERE id=1"
        ).fetchone() == (
            1,
            "active",
            "review_required",
            state.validated.manifest.version,
        )
    status = inspect(state)
    assert status["latest_reactivation_id"] == request_id and status["metadata_only"]
    assert handle(state, request(state, request_id=request_id))["ok"] is False
    assert state.supervisor.starts == 1


@ROOT_ONLY
@pytest.mark.parametrize("lost", ["issue", "begin", "finish"])
def test_lost_reply_requires_fresh_stop_of_new_start_then_new_review(reviewed, lost):
    state = reviewed
    value, before = request(state), snapshot(state)
    original = state.metadata._run

    def missing(arguments, **kw):
        frame = json.loads(kw["input"])
        result = original(arguments, **kw)
        if (lost == "issue" and frame["action"] == "issue_reactivation") or (
            frame["action"] == "reactivation_checkpoint" and frame["phase"] == lost
        ):
            raise subprocess.TimeoutExpired("fixed-worker", 25)
        return result

    state.metadata._run = missing
    assert handle(state, value)["error"] == "relational_reactivation_unconfirmed"
    state.metadata._run = original
    assert inspect(state)["latest_reactivation_id"] == value["request_id"]
    assert handle(state, value)["ok"] is False
    retained = {
        p: p.read_bytes()
        for p in state.helper_state.glob("relational-reactivation-*.json")
    }
    state.source_activation_id = value["request_id"]
    state.revision = inspect_start(state)["source_revision"]
    recovery = stop_request(state)
    assert stop(state, recovery)["status"] == "stopped_review_required"
    assert state.supervisor.process is None
    assert all(p.read_bytes() == content for p, content in retained.items())
    assert snapshot(state) == before
    state.recovery_id = recovery["request_id"]
    state.recovery_revision = inspect(state)["source_revision"]
    state.expected_grant = review(state)["grant_record_revision"]
    state.supervisor = ProcessSupervisor(state)
    assert handle(state)["status"] == "active_review_required"
    assert state.supervisor.starts == 1 and snapshot(state) == before


@ROOT_ONLY
def test_bad_current_actor_grant_source_cas_and_layout_refuse_before_key(
    reviewed, monkeypatch, caplog
):
    state = reviewed
    before = snapshot(state)
    with monkeypatch.context() as patch:
        patch.setattr(
            "three_mm_runtime.application_relational_preparation._key",
            lambda *a: pytest.fail("Invalid snapshot read key"),
        )
        for changes in (
            {"actor_token": state.user_token},
            {"actor_token": "sensitive-invalid-token"},
            {"expected_recovery_revision": "f" * 32},
            {"expected_grant_record_revision": "f" * 32},
        ):
            state.frames.clear()
            value = request(state, **changes)
            assert (
                handle(state, value)["error"] == "relational_reactivation_unconfirmed"
            )
            assert state.frames == ["inspect_reactivation"]
            assert value["actor_token"] not in caplog.text
        state.worker_root = state.runtime / "wrong-layout"
        state.frames.clear()
        assert handle(state)["error"] == "relational_reactivation_unconfirmed"
        assert state.frames == ["inspect_reactivation"]
    assert snapshot(state) == before and state.supervisor.starts == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"database_path": "/foreign"},
        {"transport_secret": "a" * 64},
        {"service_uid": 1200},
        {"configuration": {}},
        {"receipt": {}},
        {"command": "start"},
        {"installation_id": True},
        {"installation_id": 0},
        {"actor_token": "x" * 4097},
        {"source_recovery_id": "../foreign"},
        {"expected_recovery_revision": "b" * 31},
        {"request_id": ""},
        {"confirm_restart_stopped_prepared_service": False},
        {"confirm_restart_stopped_prepared_service": 1},
    ],
)
def test_closed_typed_request_rejects_bypass_or_implicit_consent(changes):
    with pytest.raises(ValueError):
        reactivation_request(wire(**changes))


@pytest.mark.parametrize(
    "problem", ["missing", "extra", "bool_id", "secret", "ticket", "header"]
)
def test_private_worker_dialect_is_closed_before_manager_access(problem):
    frame = {
        k: v
        for k, v in wire().items()
        if k not in {"confirm_restart_stopped_prepared_service", "request_id"}
    }
    frame["action"] = "inspect_reactivation"
    if problem == "missing":
        frame.pop("expected_recovery_revision")
    elif problem == "extra":
        frame["application_root"] = "/foreign"
    elif problem == "bool_id":
        frame["installation_id"] = True
    else:
        frame.update(
            action="reactivation_checkpoint",
            transport_secret="a" * 64,
            ticket={},
            phase="begin",
            receipt=None,
        )
        if problem == "secret":
            frame["transport_secret"] = "secret"
        elif problem == "header":
            frame["source_recovery_id"] = "../foreign"
    expected_error = (
        authority.AuthorityManagementError if problem == "header" else ValueError
    )
    with pytest.raises(expected_error):
        dispatch(None, frame, application_root="/trusted/runtime")


@pytest.mark.parametrize(
    "problem", ["timeout", "id", "extra", "missing", "outcome", "shape"]
)
def test_client_unknown_or_mismatched_response_never_retries(monkeypatch, problem):
    client, calls = UpdateHelperClient(None), []

    def response(payload, **kw):
        calls.append(payload)
        if problem == "timeout":
            raise UpdateHelperError("unknown")
        result = {
            "version": 1,
            "preparation_id": payload["request_id"],
            "lifecycle_sha256": "a" * 64,
            "outcome": "active_review_required",
            "signature": "b" * 64,
        }
        value = {"ok": True, "status": "active_review_required", "reactivation": result}
        if problem == "id":
            result["preparation_id"] = "f" * 32
        if problem == "extra":
            value["permissions"] = "restored"
        if problem == "missing":
            value.pop("reactivation")
        if problem == "outcome":
            result["outcome"] = "prepared_not_started"
        if problem == "shape":
            value = []
        return value

    monkeypatch.setattr(client, "_request", response)
    value = wire()
    with pytest.raises(UpdateHelperError, match="Do not retry"):
        client.reactivate_application_relational(
            1,
            value["actor_token"],
            value["expected_grant_record_revision"],
            source_recovery_id=value["source_recovery_id"],
            expected_recovery_revision=value["expected_recovery_revision"],
            request_id=value["request_id"],
            confirm_restart_stopped_prepared_service=True,
        )
    assert len(calls) == 1


@ROOT_ONLY
@pytest.mark.parametrize("uid", [0, 1200])
def test_actual_root_or_app_peer_with_core_group_is_not_core(deployed, uid):
    state = deployed
    path = state.helper_state.parent / "peer-reactivation.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    os.chown(path, 0, 1203)
    path.chmod(0o660)
    server.listen(1)
    server.settimeout(15)
    errors = []

    def serve():
        try:
            connection, _ = server.accept()
            with connection:
                update_helper._serve_connection(connection, **state.arguments)
        except BaseException as exc:
            errors.append(type(exc).__name__)

    thread = threading.Thread(target=serve)
    thread.start()
    script = """import json,socket,sys
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
    client.connect(sys.argv[1]); client.sendall(sys.stdin.buffer.readline()); print(client.recv(65536).decode())
"""
    try:
        process = subprocess.run(
            [sys.executable, "-c", script, str(path)],
            input=canonical(wire()) + b"\n",
            capture_output=True,
            timeout=20,
            user=uid,
            group=1203,
            extra_groups=(),
        )
    finally:
        thread.join(timeout=25)
        server.close()
    assert not thread.is_alive() and not errors and process.returncode == 0
    assert json.loads(process.stdout) == {"ok": False, "error": "invalid_request"}
    assert not state.frames and not state.key_path.exists()


@ROOT_ONLY
def test_cli_missing_consent_refuses_before_hidden_prompt_or_helper(deployed):
    state = deployed
    process = cli(
        state,
        [
            "reactivate-relational",
            "--installation-id",
            "1",
            "--source-recovery-id",
            "a" * 32,
            "--expected-recovery-revision",
            "b" * 32,
            "--expected-grant-record-revision",
            "c" * 32,
            "--request-id",
            "d" * 32,
        ],
    )
    assert (
        process.returncode == 2 and b"Current Core administrator" not in process.stderr
    )
    assert not state.frames and not state.key_path.exists()


def test_duplicate_new_action_frame_refuses_before_peer_or_dispatch(monkeypatch):
    class Connection:
        response = None

        def settimeout(self, value):
            pass

        def recv(self, size):
            return b'{"action":"reactivate_application_relational","actor_token":"one","actor_token":"two"}\n'

        def sendall(self, data):
            self.response = json.loads(data)

    connection = Connection()
    monkeypatch.setattr(
        update_helper,
        "_handle_request",
        lambda *a, **kw: pytest.fail("Ambiguous frame reached handler"),
    )
    update_helper._serve_connection(connection)
    assert connection.response == {"ok": False, "error": "invalid_request"}


def test_new_action_client_rejects_duplicate_response_without_retry(monkeypatch):
    from three_mm_runtime import update_helper_client as client_module

    calls = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def settimeout(self, value):
            pass

        def connect(self, path):
            pass

        def sendall(self, value):
            self.value = json.loads(value)
            calls.append(self.value["request_id"])

        def recv(self, size):
            receipt = {
                "version": 1,
                "preparation_id": self.value["request_id"],
                "lifecycle_sha256": "a" * 64,
                "outcome": "active_review_required",
                "signature": "b" * 64,
            }
            return (
                b'{"ok":true,"status":"active_review_required","status":"active_review_required","reactivation":'
                + canonical(receipt)
                + b"}\n"
            )

    monkeypatch.setattr(client_module.socket, "socket", lambda *a: Connection())
    value = wire()
    with pytest.raises(UpdateHelperError, match="Do not retry"):
        UpdateHelperClient("/unit-only.sock").reactivate_application_relational(
            1,
            value["actor_token"],
            value["expected_grant_record_revision"],
            source_recovery_id=value["source_recovery_id"],
            expected_recovery_revision=value["expected_recovery_revision"],
            request_id=value["request_id"],
            confirm_restart_stopped_prepared_service=True,
        )
    assert calls == [value["request_id"]]
