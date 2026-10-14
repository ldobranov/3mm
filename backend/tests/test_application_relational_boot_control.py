"""Actual local Core CLI/UID -> Root enable-only -> Core-UID boot journal.

Disposable roots/processes, real current human/native/grant contracts. Unit I/O
is a test adapter, NOT live systemd/reboot. No fabricated successful permissions.
"""

import json
import os
import socket
import subprocess
import threading
from pathlib import Path
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
)
from backend.tests.test_application_relational_activation_control import (
    request as start_request,
)
from backend.tests.test_application_relational_activation_control import (
    source_installed,
    source_subject,
    tmp_path,
)
from backend.tests.test_application_relational_boot import BootProcessAdapter
from backend.tests.test_application_relational_preparation import ROOT_ONLY, identity
from backend.tests.test_application_relational_reactivation_control import review
from backend.tests.test_application_relational_recovery_control import (
    cli,
    inspect,
    metadata_rows,
)
from backend.tests.test_application_relational_recovery_control import (
    request as stop_request,
)
from three_mm_application_sdk.relational_wire import canonical, sign_metadata
from three_mm_runtime import application_relational_activation_recovery as stop_helper
from three_mm_runtime import application_relational_boot as boot_helper
from three_mm_runtime import update_helper
from three_mm_runtime.application_relational_control import boot_enable_request
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Actual Core/Unix peer")


@pytest.fixture
def started(prepared, monkeypatch):
    state = prepared
    value = start_request(state)
    result = update_helper._handle_request(
        value, relational_peer_uid=1202, **state.arguments
    )
    assert result["status"] == "active_review_required", (result, state.frames)
    state.source_activation_id = value["request_id"]
    state.revision = inspect(state)["source_revision"]
    state.boot_supervisor = BootProcessAdapter(state.supervisor)
    monkeypatch.setattr(
        boot_helper, "PreparedBootSupervisor", lambda: state.boot_supervisor
    )
    monkeypatch.setattr(
        stop_helper, "PreparedServiceSupervisor", lambda: state.supervisor
    )
    state.frames.clear()
    return state


@pytest.fixture
def reviewed(started):
    state = started
    state.expected_grant = review(state)["grant_record_revision"]
    state.frames.clear()
    return state


def request(state, **changes):
    return {
        "action": "enable_application_relational_boot",
        "installation_id": 1,
        "actor_token": state.token,
        "source_activation_id": state.source_activation_id,
        "expected_activation_revision": state.revision,
        "expected_grant_record_revision": state.expected_grant,
        "request_id": identity(),
        "confirm_enable_prepared_boot": True,
        **changes,
    }


def handle(state, value=None, **changes):
    return update_helper._handle_request(
        value or request(state),
        **{"relational_peer_uid": 1202, **state.arguments, **changes},
    )


def wire(**changes):
    return request(
        SimpleNamespace(
            token="private-test-token",
            source_activation_id="a" * 32,
            revision="b" * 32,
            expected_grant="c" * 32,
        ),
        **changes,
    )


def files(state):
    return {
        path: path.read_bytes()
        for path in (
            state.database,
            state.key_path,
            state.instance / "active.json",
            state.instance / "relational.json",
            *state.helper_state.glob("relational-activation-*.json"),
        )
    }


def authority_state(state):
    with state.engine.connect() as db:
        return (
            db.exec_driver_sql(
                "SELECT payload,seal FROM application_authority_grants WHERE installation_id=1"
            ).fetchall(),
            db.exec_driver_sql(
                "SELECT enabled,status,authority_epoch,authority_mode,active_version,socket_path FROM application_extension_installations WHERE id=1"
            ).fetchone(),
        )


@ROOT_ONLY
def test_actual_cli_peer_core_uid_writer_enables_without_restart_or_grant_replay(
    reviewed,
):
    state = reviewed
    before, rights, pid = (
        files(state),
        authority_state(state),
        state.supervisor.process.pid,
    )
    path = state.helper_state.parent / "boot.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    os.chown(path, 0, 1203)
    path.chmod(0o660)
    server.listen(1)
    server.settimeout(15)
    errors, phases = [], []
    original = state.metadata._run

    def observe(arguments, **kw):
        frame = json.loads(kw["input"])
        if frame["action"] == "boot_enable_checkpoint":
            assert (
                frame["expected_activation_revision"]
                == frame["ticket"]["source_activation_revision"]
            )
            assert frame["expected_activation_revision"] != state.revision
            phases.append(frame["phase"])
            with pytest.raises(
                authority.AuthorityManagementError, match="boot_enable_frame_changed"
            ):
                dispatch(
                    None,
                    dict(frame, expected_activation_revision=state.revision),
                    application_root=state.runtime,
                )
        return original(arguments, **kw)

    def serve():
        try:
            connection, _ = server.accept()
            with connection:
                update_helper._serve_connection(connection, **state.arguments)
        except BaseException as exc:
            errors.append(type(exc).__name__)

    state.metadata._run = observe
    thread = threading.Thread(target=serve)
    thread.start()
    request_id = identity()
    try:
        process = cli(
            state,
            [
                "enable-relational-boot",
                "--installation-id",
                "1",
                "--source-activation-id",
                state.source_activation_id,
                "--expected-activation-revision",
                state.revision,
                "--expected-grant-record-revision",
                state.expected_grant,
                "--request-id",
                request_id,
                "--confirm-enable-prepared-boot",
            ],
            THREE_MM_APPLICATION_HELPER_SOCKET=str(path),
        )
    finally:
        thread.join(timeout=25)
        server.close()
        state.metadata._run = original
    assert not thread.is_alive() and not errors
    assert process.returncode == 0, (process.stderr.decode(), state.frames)
    result = json.loads(process.stdout)
    assert result["status"] == "boot_enabled_not_started"
    assert result["boot"]["preparation_id"] == request_id
    assert (
        result["boot_autostart_enabled"]
        and result["permission_approval"] == "not_evaluated"
    )
    assert state.token.encode() not in process.stdout + process.stderr
    assert phases == ["authorize", "begin", "check", "check", "finish"]
    assert (
        state.frames
        == ["inspect_boot_enable", "issue_boot_enable"] + ["boot_enable_checkpoint"] * 5
    )
    assert state.boot_supervisor.enabled and state.boot_supervisor.enables == 1
    assert state.supervisor.starts == 1 and state.supervisor.process.pid == pid
    state.supervisor.verify_identity(state.instance.name, 1200, 1201, running=True)
    assert files(state) == before and authority_state(state) == rights
    policy = json.loads((state.instance / "boot-authority.json").read_bytes())
    assert policy["phase"] == "boot_confirmed" and policy["receipt"] == result["boot"]
    assert inspect(state)["source_revision"] != state.revision
    assert handle(state, request(state, request_id=request_id))["ok"] is False
    assert state.boot_supervisor.enables == 1 and state.supervisor.starts == 1


@ROOT_ONLY
def test_no_runtime_review_refuses_before_existing_key_or_process_effect(
    started, monkeypatch
):
    state = started
    before, rows = files(state), metadata_rows(state)
    monkeypatch.setattr(
        "three_mm_runtime.application_relational_preparation._key",
        lambda *a: pytest.fail("Read key before current authority"),
    )
    assert handle(state)["error"] == "relational_boot_enable_unconfirmed"
    assert state.frames == ["inspect_boot_enable"]
    assert state.boot_supervisor.enables == 0 and state.supervisor.starts == 1
    assert files(state) == before and metadata_rows(state) == rows


@ROOT_ONLY
def test_actual_core_uid_boot_wiring_accepts_exact_confirmed_repeated_start(reviewed):
    state = reviewed
    before = files(state)
    recovery_request = stop_request(state)
    stopped = update_helper._handle_request(
        recovery_request, relational_peer_uid=1202, **state.arguments
    )
    assert stopped["status"] == "stopped_review_required"
    recovery_status = cli(
        state,
        [
            "inspect-relational-recovery",
            "--installation-id",
            "1",
            "--source-recovery-id",
            recovery_request["request_id"],
        ],
    )
    assert recovery_status.returncode == 0, recovery_status.stderr.decode()
    revision = json.loads(recovery_status.stdout)["source_revision"]
    state.expected_grant = review(state)["grant_record_revision"]
    state.supervisor = ProcessSupervisor(state)
    restart_id = identity()
    restart = update_helper._handle_request(
        {
            "action": "reactivate_application_relational",
            "installation_id": 1,
            "actor_token": state.token,
            "source_recovery_id": recovery_request["request_id"],
            "expected_recovery_revision": revision,
            "expected_grant_record_revision": state.expected_grant,
            "request_id": restart_id,
            "confirm_restart_stopped_prepared_service": True,
        },
        relational_peer_uid=1202,
        **state.arguments,
    )
    assert restart["status"] == "active_review_required", (restart, state.frames)
    state.source_activation_id = restart_id
    state.revision = inspect(state)["source_revision"]
    state.expected_grant = review(state)["grant_record_revision"]
    state.boot_supervisor = BootProcessAdapter(state.supervisor)
    state.frames.clear()
    rights, pid = authority_state(state), state.supervisor.process.pid
    result = handle(state)
    assert result["status"] == "boot_enabled_not_started", (result, state.frames)
    assert state.boot_supervisor.enables == 1 and state.supervisor.process.pid == pid
    assert state.supervisor.starts == 1 and authority_state(state) == rights
    assert all(path.read_bytes() == contents for path, contents in before.items())
    policy = json.loads((state.instance / "boot-required.json").read_bytes())
    assert policy["source_activation_action"] == "reactivate_prepared_service"
    assert policy["source_activation_id"] == restart_id


@ROOT_ONLY
@pytest.mark.parametrize("problem", ["actor", "source", "grant", "layout"])
def test_current_actor_source_grant_and_installed_layout_are_checked_before_key(
    reviewed, monkeypatch, problem, caplog
):
    state = reviewed
    value = request(state)
    if problem == "actor":
        value["actor_token"] = "private-invalid-token"
    elif problem == "source":
        value["expected_activation_revision"] = "f" * 32
    elif problem == "grant":
        value["expected_grant_record_revision"] = "f" * 32
    else:
        state.worker_root = state.runtime / "foreign"
    before, rows = files(state), metadata_rows(state)
    monkeypatch.setattr(
        "three_mm_runtime.application_relational_preparation._key",
        lambda *a: pytest.fail("Read key before current snapshot"),
    )
    assert handle(state, value)["error"] == "relational_boot_enable_unconfirmed"
    assert state.frames == ["inspect_boot_enable"]
    assert files(state) == before and metadata_rows(state) == rows
    assert not state.boot_supervisor.enables and value["actor_token"] not in caplog.text


@ROOT_ONLY
@pytest.mark.parametrize("lost", ["issue", "begin", "finish"])
def test_lost_core_uid_ack_retains_unknown_and_requires_fresh_stop(reviewed, lost):
    state = reviewed
    value, before, rights = request(state), files(state), authority_state(state)
    original = state.metadata._run

    def missing(arguments, **kw):
        frame = json.loads(kw["input"])
        result = original(arguments, **kw)
        if (lost == "issue" and frame["action"] == "issue_boot_enable") or (
            frame["action"] == "boot_enable_checkpoint" and frame["phase"] == lost
        ):
            raise subprocess.TimeoutExpired("fixed-worker", 25)
        return result

    state.metadata._run = missing
    assert handle(state, value)["error"] == "relational_boot_enable_unconfirmed"
    state.metadata._run = original
    assert authority_state(state) == rights and files(state) == before
    assert state.supervisor.starts == 1 and state.supervisor.process is not None
    assert not state.boot_supervisor.enabled
    if lost == "finish":
        assert (
            json.loads((state.instance / "boot-authority.json").read_bytes())["phase"]
            == "boot_pending"
        )
    else:
        # A lost begin ACK must NOT reach Root publication or unit enable.
        assert not (state.instance / "boot-required.json").exists()
        assert not (state.instance / "boot-authority.json").exists()
    state.revision = inspect(state)["source_revision"]
    assert (
        handle(
            state,
            dict(
                value,
                request_id=identity(),
                expected_activation_revision=state.revision,
            ),
        )["ok"]
        is False
    )
    assert state.boot_supervisor.enables == (1 if lost == "finish" else 0)
    stopped = update_helper._handle_request(
        stop_request(state), relational_peer_uid=1202, **state.arguments
    )
    assert stopped["status"] == "stopped_review_required", (stopped, state.frames)
    assert state.supervisor.process is None
    assert files(state) == before
    assert not (state.instance / "boot-required.json").exists()
    assert not (state.instance / "boot-authority.json").exists()


@ROOT_ONLY
@pytest.mark.parametrize("uid", [0, 1200])
def test_actual_root_or_app_peer_even_in_core_group_is_not_core(deployed, uid):
    state = deployed
    path = state.helper_state.parent / "wrong-boot-peer.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    os.chown(path, 0, 1203)
    path.chmod(0o660)
    server.listen(1)
    server.settimeout(10)
    script = "import socket,sys; s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); s.sendall(sys.stdin.buffer.read()); print(s.recv(4096).decode())"
    process = subprocess.Popen(
        [__import__("sys").executable, "-c", script, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        user=uid,
        group=1203,
        extra_groups=(),
    )
    try:
        process.stdin.write(canonical(wire()) + b"\n")
        process.stdin.close()
        process.stdin = None
        connection, _ = server.accept()
        with connection:
            update_helper._serve_connection(connection, **state.arguments)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0 and not stderr
        assert json.loads(stdout) == {"ok": False, "error": "invalid_request"}
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=3)
        server.close()
    assert not state.frames and not state.instance.exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"path": "/foreign"},
        {"runtime_root": "/foreign"},
        {"transport_secret": "a" * 64},
        {"service_uid": 0},
        {"configuration": {}},
        {"command": "enable --now"},
        {"receipt": {}},
        {"scopes": []},
        {"confirm_enable_prepared_boot": False},
        {"confirm_enable_prepared_boot": 1},
        {"installation_id": True},
        {"expected_activation_revision": "bad"},
        {"source_activation_id": "bad"},
        {"request_id": "bad"},
        {"actor_token": ""},
    ],
)
def test_closed_boot_request_has_no_path_key_command_or_implicit_confirmation(changes):
    with pytest.raises(ValueError):
        boot_enable_request(wire(**changes))


@pytest.mark.parametrize(
    "operation", ["inspect_boot_enable", "issue_boot_enable", "boot_enable_checkpoint"]
)
@pytest.mark.parametrize(
    "extra",
    [
        {"runtime_root": "/foreign"},
        {"command": "enable"},
        {"confirm_enable_prepared_boot": True},
    ],
)
def test_metadata_dialect_refuses_caller_context_before_manager_access(
    operation, extra
):
    frame = {
        name: value
        for name, value in wire().items()
        if name not in {"request_id", "confirm_enable_prepared_boot"}
    }
    frame["action"] = operation
    if operation == "issue_boot_enable":
        frame.update(
            transport_secret="d" * 64,
            request_id=identity(),
            service_uid=1200,
            service_gid=1201,
            coordinator_uid=1202,
        )
    if operation == "boot_enable_checkpoint":
        frame.update(transport_secret="d" * 64, ticket={}, phase="begin", receipt=None)
    with pytest.raises(ValueError):
        dispatch(None, dict(frame, **extra), application_root=Path("/trusted"))


@pytest.mark.parametrize("problem", ["lost", "extra", "request", "source", "outcome"])
def test_client_refuses_ambiguous_completion_without_retry(monkeypatch, problem):
    value, calls = wire(), []
    result = sign_metadata(
        b"x" * 32,
        "boot_enable_result",
        {
            "version": 1,
            "preparation_id": value["request_id"],
            "source_activation_id": value["source_activation_id"],
            "ticket_sha256": "d" * 64,
            "lifecycle_sha256": "e" * 64,
            "witness_sha256": "f" * 64,
            "outcome": "boot_enabled_not_started",
        },
    )
    response = {"ok": True, "status": "boot_enabled_not_started", "boot": result}
    if problem == "extra":
        response["extra"] = True
    elif problem in {"request", "source"}:
        result["preparation_id" if problem == "request" else "source_activation_id"] = (
            "0" * 32
        )
    elif problem == "outcome":
        result["outcome"] = "active"
    client = UpdateHelperClient(Path("/unused"))

    def call(*a, **kw):
        calls.append(1)
        if problem == "lost":
            raise UpdateHelperError("Unknown result")
        return response

    monkeypatch.setattr(client, "_request", call)
    with pytest.raises(UpdateHelperError, match="Do not retry"):
        client.enable_application_relational_boot(
            value["installation_id"],
            value["actor_token"],
            value["expected_grant_record_revision"],
            **{
                name: value[name]
                for name in (
                    "source_activation_id",
                    "expected_activation_revision",
                    "request_id",
                    "confirm_enable_prepared_boot",
                )
            },
        )
    assert calls == [1]


@ROOT_ONLY
def test_cli_requires_explicit_boot_confirmation_before_prompt_or_helper(deployed):
    state = deployed
    process = cli(
        state,
        [
            "enable-relational-boot",
            "--installation-id",
            "1",
            "--source-activation-id",
            "a" * 32,
            "--expected-activation-revision",
            "b" * 32,
            "--expected-grant-record-revision",
            "c" * 32,
            "--request-id",
            "d" * 32,
        ],
    )
    assert process.returncode == 2
    assert b"confirm-enable-prepared-boot" in process.stderr
    assert b"login token" not in process.stderr and not state.frames


def test_duplicate_boot_helper_frame_is_refused_before_dispatch(tmp_path, monkeypatch):
    caller, server = socket.socketpair()
    value = canonical(wire())[:-1] + b',"installation_id":1}\n'
    monkeypatch.setattr(
        update_helper,
        "_handle_request",
        lambda *a, **kw: pytest.fail("Dispatched ambiguous boot frame"),
    )
    with caller, server:
        caller.sendall(value)
        update_helper._serve_connection(
            server,
            stage_root=tmp_path / "stage",
            state_root=tmp_path / "state",
            allowlist=tmp_path / "allowlist",
            status_file=tmp_path / "status",
        )
        assert json.loads(caller.recv(1024)) == {
            "ok": False,
            "error": "invalid_request",
        }


def test_duplicate_boot_client_response_is_unconfirmed_without_retry(monkeypatch):
    from three_mm_runtime import update_helper_client

    calls = []

    class ResponseSocket:
        def __enter__(self):
            calls.append(1)
            return self

        def __exit__(self, *a):
            pass

        def settimeout(self, value):
            pass

        def connect(self, path):
            pass

        def sendall(self, data):
            assert json.loads(data)["action"] == "enable_application_relational_boot"

        def recv(self, size):
            return (
                b'{"ok":true,"ok":true,"status":"boot_enabled_not_started","boot":{}}\n'
            )

    monkeypatch.setattr(
        update_helper_client.socket, "socket", lambda *a: ResponseSocket()
    )
    value = wire()
    with pytest.raises(UpdateHelperError, match="Do not retry"):
        UpdateHelperClient(Path("/unused")).enable_application_relational_boot(
            value["installation_id"],
            value["actor_token"],
            value["expected_grant_record_revision"],
            **{
                name: value[name]
                for name in (
                    "source_activation_id",
                    "expected_activation_revision",
                    "request_id",
                    "confirm_enable_prepared_boot",
                )
            },
        )
    assert calls == [1]
