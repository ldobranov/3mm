"""Actual Core admin/OS peer -> Root stop -> actual Core-UID recovery journal.

Disposable paths/process credentials only; no live systemd/account/grant changes.
"""

import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.services.application_relational_admin_worker import dispatch
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
from backend.tests.test_application_relational_preparation import ROOT_ONLY, identity
from three_mm_application_sdk.relational_wire import canonical
from three_mm_runtime import application_relational_activation_recovery as helper
from three_mm_runtime import update_helper
from three_mm_runtime.application_relational_control import activation_recovery_request
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Actual Core/principals/Unix peer"
)


class Crash(BaseException):
    pass


def cli(state, arguments, *, token=None, **environment):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.services.application_authority_admin",
            *arguments,
        ],
        input=(state.token if token is None else token).encode() + b"\n",
        capture_output=True,
        timeout=90,
        start_new_session=True,
        user=1202,
        group=1203,
        extra_groups=(),
        env=dict(state.environment, **environment),
    )


def inspect(state, *, token=None):
    process = cli(
        state,
        [
            "inspect-relational-start",
            "--installation-id",
            "1",
            "--source-activation-id",
            state.source_activation_id,
        ],
        token=token,
    )
    assert process.returncode == 0, process.stderr.decode()
    assert state.token.encode() not in process.stdout + process.stderr
    return json.loads(process.stdout)


@pytest.fixture
def interrupted(prepared, monkeypatch):
    state = prepared
    value = start_request(state)
    original = state.metadata._run

    def crash(arguments, **kwargs):
        frame = json.loads(kwargs["input"])
        result = original(arguments, **kwargs)
        if frame["action"] == "activation_checkpoint" and frame["phase"] == "check":
            raise Crash()
        return result

    state.metadata._run = crash
    with pytest.raises(Crash):
        update_helper._handle_request(
            value, relational_peer_uid=1202, **state.arguments
        )
    state.metadata._run = original
    state.source_activation_id = value["request_id"]
    state.revision = inspect(state)["source_revision"]
    state.frames.clear()
    assert state.supervisor.starts == 1 and state.supervisor.process is not None
    monkeypatch.setattr(helper, "PreparedServiceSupervisor", lambda: state.supervisor)
    return state


def request(state, **changes):
    return {
        "action": "recover_application_relational_start",
        "installation_id": 1,
        "actor_token": state.token,
        "source_activation_id": state.source_activation_id,
        "expected_activation_revision": state.revision,
        "request_id": identity(),
        "confirm_stop_preserve_prepared_state": True,
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


def snapshot(state):
    return {
        path: path.read_bytes()
        for path in (
            state.database,
            state.key_path,
            state.instance / "active.json",
            state.instance / "relational.json",
            state.helper_state
            / ("relational-activation-" + state.instance.name + ".json"),
        )
    }


def metadata_rows(state):
    with state.engine.connect() as db:
        return tuple(
            db.exec_driver_sql(sql).fetchall()
            for sql in (
                "SELECT payload,seal FROM application_authority_actions ORDER BY request_id",
                "SELECT payload,seal FROM application_authority_grants WHERE installation_id=1",
                "SELECT authority_epoch,authority_mode,enabled,status FROM application_extension_installations WHERE id=1",
                "SELECT revision FROM core_authority_guard",
            )
        )


@ROOT_ONLY
def test_inspect_command_is_core_authenticated_readonly_and_never_checks_process(
    interrupted,
):
    state = interrupted
    rows, before = metadata_rows(state), snapshot(state)
    result = inspect(state)
    assert result == {
        "installation_id": 1,
        "source_activation_id": state.source_activation_id,
        "source_revision": state.revision,
        "source_state": "execution_unconfirmed",
        "latest_recovery_id": None,
        "metadata_only": True,
        "permission_approval": "not_evaluated",
    }
    assert metadata_rows(state) == rows and snapshot(state) == before
    assert state.supervisor.process is not None and not state.frames


@ROOT_ONLY
def test_actual_core_recovery_writer_stops_nonroot_host_without_grant_restore(
    interrupted,
):
    state = interrupted
    before = snapshot(state)
    with state.engine.connect() as db:
        old_grant = db.exec_driver_sql(
            "SELECT payload FROM application_authority_grants WHERE installation_id=1"
        ).scalar_one()
    value = request(state)
    result = handle(state, value)
    assert result["status"] == "stopped_review_required", (result, state.frames)
    assert result["recovery"]["preparation_id"] == value["request_id"]
    assert result["recovery"]["source_activation_id"] == state.source_activation_id
    assert (
        state.frames
        == ["inspect_activation_recovery", "issue_activation_recovery"]
        + ["activation_recovery_checkpoint"] * 4
    )
    assert state.supervisor.process is None and state.supervisor.starts == 1
    assert snapshot(state) == before
    with state.engine.connect() as db:
        assert db.exec_driver_sql(
            "SELECT enabled,status,authority_mode,active_version FROM application_extension_installations WHERE id=1"
        ).fetchone() == (0, "disabled", "review_required", None)
        assert (
            db.exec_driver_sql(
                "SELECT payload FROM application_authority_grants WHERE installation_id=1"
            ).scalar_one()
            == old_grant
        )
    assert handle(state, value)["error"] == "relational_start_recovery_unconfirmed"
    assert state.supervisor.starts == 1


@ROOT_ONLY
def test_revoked_native_review_does_not_require_new_permission_or_trust_to_stop(
    interrupted,
):
    state = interrupted
    with state.engine.connect() as db:
        identifier, payload = db.exec_driver_sql(
            "SELECT review_id,payload FROM application_native_reviews LIMIT 1"
        ).fetchone()
        revision = json.loads(payload)[
            "revision"
        ]  # Diagnostic input, verified by actual Core CLI.
        grant = db.exec_driver_sql(
            "SELECT payload FROM application_authority_grants WHERE installation_id=1"
        ).scalar_one()
    process = cli(
        state,
        [
            "revoke-native-review",
            "--installation-id",
            "1",
            "--native-review-id",
            identifier,
            "--expected-revision",
            revision,
        ],
    )
    assert process.returncode == 0, process.stderr.decode()
    state.revision = inspect(state)["source_revision"]
    result = handle(state)
    assert result["status"] == "stopped_review_required", (result, state.frames)
    with state.engine.connect() as db:
        assert (
            db.exec_driver_sql(
                "SELECT payload FROM application_authority_grants WHERE installation_id=1"
            ).scalar_one()
            == grant
        )
    assert state.supervisor.process is None


@ROOT_ONLY
@pytest.mark.parametrize("uid", [None, 0, 1200, True])
def test_core_os_peer_required_before_metadata_or_existing_key_read(deployed, uid):
    state = SimpleNamespace(
        token=deployed.token, source_activation_id="b" * 32, revision="c" * 32
    )
    assert handle(deployed, request(state), relational_peer_uid=uid) == {
        "ok": False,
        "error": "invalid_request",
    }
    assert not deployed.frames and not deployed.key_path.exists()


@ROOT_ONLY
@pytest.mark.parametrize("problem", ["user", "invalid", "stale", "layout"])
def test_bad_actor_revision_or_layout_refuses_before_stop(interrupted, problem, caplog):
    state = interrupted
    before = snapshot(state)
    changes = {
        "user": {"actor_token": state.user_token},
        "invalid": {"actor_token": "sensitive-invalid-token"},
        "stale": {"expected_activation_revision": "f" * 32},
    }.get(problem, {})
    if problem == "layout":
        state.worker_root = state.runtime / "wrong-layout"
    value = request(state, **changes)
    assert handle(state, value) == {
        "ok": False,
        "error": "relational_start_recovery_unconfirmed",
    }
    assert state.frames == ["inspect_activation_recovery"]
    assert state.supervisor.process is not None and snapshot(state) == before
    assert value["actor_token"] not in caplog.text


@ROOT_ONLY
@pytest.mark.parametrize("lost", ["issue", "begin", "finish"])
def test_lost_metadata_ack_requires_new_source_revision_and_fresh_human_request(
    interrupted, lost
):
    state = interrupted
    original = state.metadata._run
    value, before = request(state), snapshot(state)

    def missing(arguments, **kw):
        frame = json.loads(kw["input"])
        result = original(arguments, **kw)
        if (lost == "issue" and frame["action"] == "issue_activation_recovery") or (
            frame["action"] == "activation_recovery_checkpoint"
            and frame["phase"] == lost
        ):
            raise subprocess.TimeoutExpired("fixed-worker", 25)
        return result

    state.metadata._run = missing
    assert handle(state, value)["error"] == "relational_start_recovery_unconfirmed"
    state.metadata._run = original
    assert handle(state, value)["ok"] is False  # No replay with original CAS.
    retained = {
        path: path.read_bytes()
        for path in state.helper_state.glob("relational-start-recovery-*.json")
    }
    status = inspect(state)
    assert status["latest_recovery_id"] == value["request_id"]
    assert status["source_revision"] != state.revision
    state.revision = status["source_revision"]
    assert handle(state)["status"] == "stopped_review_required"
    assert all(path.read_bytes() == content for path, content in retained.items())
    assert snapshot(state) == before
    assert state.supervisor.process is None and state.supervisor.starts == 1


@ROOT_ONLY
def test_cli_core_peer_recovery_does_not_start_or_change_prepared_state(interrupted):
    state = interrupted
    before = snapshot(state)
    path = state.helper_state.parent / "recovery-control.sock"
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
    request_id = identity()
    try:
        process = cli(
            state,
            [
                "recover-relational-start",
                "--installation-id",
                "1",
                "--source-activation-id",
                state.source_activation_id,
                "--expected-activation-revision",
                state.revision,
                "--request-id",
                request_id,
                "--confirm-stop-preserve-prepared-state",
            ],
            THREE_MM_APPLICATION_HELPER_SOCKET=str(path),
        )
    finally:
        thread.join(timeout=95)
        server.close()
    assert not thread.is_alive() and not errors
    assert process.returncode == 0, (process.stderr.decode(), state.frames)
    result = json.loads(process.stdout)
    assert (
        result["status"] == "stopped_review_required"
        and result["recovery"]["preparation_id"] == request_id
    )
    assert (
        result["permission_approval"] == "not_evaluated"
        and result["boot_autostart_enabled"] is False
    )
    assert state.token.encode() not in process.stdout + process.stderr
    assert snapshot(state) == before
    assert state.supervisor.process is None and state.supervisor.starts == 1


@pytest.mark.parametrize(
    "change",
    [
        {"database_path": "/foreign"},
        {"runtime_root": "/foreign"},
        {"transport_secret": "a" * 64},
        {"service_uid": 0},
        {"configuration": {}},
        {"command": "anything"},
        {"receipt": {}},
        {"expected_grant_record_revision": "a" * 32},
        {"installation_id": True},
        {"request_id": "A" * 32},
        {"source_activation_id": 1},
        {"expected_activation_revision": "bad"},
        {"confirm_stop_preserve_prepared_state": False},
        {"confirm_stop_preserve_prepared_state": 1},
    ],
)
def test_closed_request_does_not_accept_keys_paths_grants_commands_or_implicit_consent(
    change,
):
    value = request(
        SimpleNamespace(
            token="hidden", source_activation_id="b" * 32, revision="c" * 32
        )
    )
    with pytest.raises(ValueError):
        activation_recovery_request(dict(value, **change))


@pytest.mark.parametrize(
    "extra",
    [
        {"action": "inspect_activation_recovery", "runtime_root": "/foreign"},
        {
            "action": "inspect_activation_recovery",
            "expected_grant_record_revision": "a" * 32,
        },
        {
            "action": "issue_activation_recovery",
            "transport_secret": "a" * 64,
            "request_id": "d" * 32,
        },
        {
            "action": "activation_recovery_checkpoint",
            "transport_secret": "a" * 64,
            "ticket": [],
            "phase": "finish",
            "receipt": {},
        },
    ],
)
def test_private_metadata_dialect_refuses_extra_or_missing_fields_before_manager_access(
    extra,
):
    with pytest.raises(ValueError):
        dispatch(
            None,
            {
                "installation_id": 1,
                "actor_token": "hidden",
                "source_activation_id": "b" * 32,
                "expected_activation_revision": "c" * 32,
                **extra,
            },
        )


@pytest.mark.parametrize(
    "problem",
    [
        "wrong_id",
        "wrong_source",
        "wrong_outcome",
        "extra",
        "malformed",
        "outer_extra",
        "timeout",
    ],
)
def test_client_does_not_retry_unknown_or_mismatched_response(monkeypatch, problem):
    value = request(
        SimpleNamespace(
            token="hidden", source_activation_id="b" * 32, revision="c" * 32
        )
    )
    result = {
        "version": 1,
        "preparation_id": value["request_id"],
        "ticket_sha256": "a" * 64,
        "source_activation_id": value["source_activation_id"],
        "lifecycle_sha256": "d" * 64,
        "witness_sha256": "e" * 64,
        "outcome": "stopped_review_required",
        "signature": "f" * 64,
    }
    if problem in {"wrong_id", "wrong_source", "wrong_outcome", "extra"}:
        result.update(
            {
                "wrong_id": {"preparation_id": "f" * 32},
                "wrong_source": {"source_activation_id": "f" * 32},
                "wrong_outcome": {"outcome": "active_review_required"},
                "extra": {"transport_secret": "a" * 64},
            }[problem]
        )
    if problem == "malformed":
        result = []
    calls = []
    client = UpdateHelperClient(Path("/unused"))

    def response(payload, **kw):
        calls.append(payload)
        assert kw == {"expected_status": "stopped_review_required"}
        if problem == "timeout":
            raise UpdateHelperError("Transport outcome unknown")
        return {
            "ok": True,
            "status": "stopped_review_required",
            "recovery": result,
            **({"transport_secret": "a" * 64} if problem == "outer_extra" else {}),
        }

    monkeypatch.setattr(client, "_request", response)
    with pytest.raises(UpdateHelperError, match="Do not retry"):
        client.recover_application_relational_start(
            1,
            "hidden",
            "c" * 32,
            source_activation_id="b" * 32,
            request_id=value["request_id"],
            confirm_stop_preserve_prepared_state=True,
        )
    assert len(calls) == 1


@ROOT_ONLY
def test_duplicate_recovery_helper_frame_refuses_before_dispatch(tmp_path, monkeypatch):
    value = request(
        SimpleNamespace(
            token="hidden", source_activation_id="b" * 32, revision="c" * 32
        )
    )
    frame = (
        canonical(value)[:-1]
        + b',"request_id":"'
        + value["request_id"].encode()
        + b'"}\n'
    )
    monkeypatch.setattr(
        update_helper,
        "_handle_request",
        lambda *a, **kw: pytest.fail("Ambiguous recovery frame reached handler"),
    )
    server, client = socket.socketpair()
    with server, client:
        client.sendall(frame)
        update_helper._serve_connection(server)
        assert json.loads(client.recv(1024)) == {
            "ok": False,
            "error": "invalid_request",
        }


@ROOT_ONLY
@pytest.mark.parametrize("uid", [0, 1200])
def test_real_root_or_app_peer_even_in_core_group_is_not_the_core_user(deployed, uid):
    state = deployed
    path = state.helper_state.parent / "peer-check.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    os.chown(path, 0, 1203)
    path.chmod(0o660)
    server.listen(1)
    server.settimeout(15)
    value = request(
        SimpleNamespace(
            token=state.token, source_activation_id="b" * 32, revision="c" * 32
        )
    )
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
    program = (
        "import socket,sys; s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); "
        "s.sendall(sys.stdin.buffer.read()); print(s.recv(4096).decode()); s.close()"
    )
    try:
        process = subprocess.run(
            [sys.executable, "-c", program, str(path)],
            input=canonical(value) + b"\n",
            capture_output=True,
            timeout=20,
            user=uid,
            group=1203,
            extra_groups=(),
            env={"PATH": "/usr/bin:/bin"},
        )
    finally:
        thread.join(timeout=25)
        server.close()
    assert not thread.is_alive() and not errors
    assert process.returncode == 0, process.stderr.decode()
    assert json.loads(process.stdout) == {"ok": False, "error": "invalid_request"}
    assert not state.frames and not state.key_path.exists()


@ROOT_ONLY
def test_cli_requires_stop_confirmation_before_prompt_or_helper(deployed):
    state = deployed
    process = cli(
        state,
        [
            "recover-relational-start",
            "--installation-id",
            "1",
            "--source-activation-id",
            "b" * 32,
            "--expected-activation-revision",
            "c" * 32,
            "--request-id",
            "d" * 32,
        ],
    )
    assert process.returncode == 2
    assert b"--confirm-stop-preserve-prepared-state" in process.stderr
    assert b"Current Core administrator" not in process.stderr
    assert state.token.encode() not in process.stdout + process.stderr
    assert not state.frames and not state.key_path.exists()
