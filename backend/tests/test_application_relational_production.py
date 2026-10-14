"""Existing helper -> actual Core UID worker -> actual non-root migration worker.

Disposable Linux files only; no production systemd units/services are launched.
The fixed production systemd command is checked separately from process tests.
"""

import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.services.application_relational_admin_worker import dispatch
from backend.tests.test_application_relational_installation import (
    ROOT_ONLY,
    absent_paths,
    initial,
    managed_installed,
    source_installed,
    source_subject,
    stopped,
)
from three_mm_application_sdk.relational_wire import canonical
from three_mm_runtime import update_helper
from three_mm_runtime.application_relational_control import (
    CoreMetadataClient,
    preparation_request,
)
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Actual local helper/Core credentials"
)


def request(state):
    return {
        "action": "prepare_application_relational",
        "installation_id": 1,
        "actor_token": state.token,
        "expected_grant_record_revision": state.expected_grant,
        "confirm_fresh_owned_namespace": True,
        "confirm_owned_business_migrations": True,
    }


@pytest.fixture
def production(initial, tmp_path, monkeypatch):
    state = initial
    database = Path(state.engine.url.database)
    state.engine.dispose()
    for parent in (tmp_path.parent, tmp_path.parent.parent):
        parent.chmod(0o755)
    tmp_path.chmod(0o755)
    # Dedicated Core metadata ownership, not broad production chmod or new users.
    os.chown(tmp_path, 1202, 1203)
    for path in (
        database,
        database.with_name(database.name + "-wal"),
        database.with_name(database.name + "-shm"),
    ):
        if path.exists():
            os.chown(path, 1202, 1203)
    os.chown(state.key_directory, 1202, 1203)
    for path in state.key_directory.iterdir():
        os.chown(path, 1202, 1203)
    environment = dict(
        os.environ,
        DATABASE_URL=f"sqlite:///{database}",
        UPLOADS_DIR=str(state.root),
        THREE_MM_AUTHORITY_REVIEW_KEY_DIR=str(state.key_directory),
        PYTHONDONTWRITEBYTECODE="1",
    )
    state.frames = []

    def runner(arguments, **kwargs):
        frame = json.loads(kwargs["input"])
        state.frames.append(frame["action"])
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.services.application_relational_admin_worker",
                "--core-uid",
                "1202",
                "--database",
                str(database),
            ],
            user=1202,
            group=1203,
            extra_groups=(),
            env=environment,
            **kwargs,
        )

    state.metadata = CoreMetadataClient(core_uid=1202, database=database, runner=runner)
    monkeypatch.setattr(
        "three_mm_runtime.application_relational_control.CoreMetadataClient",
        lambda **kw: state.metadata,
    )
    monkeypatch.setattr(
        update_helper,
        "_service_ids",
        lambda user, group: (1200, 1201) if user == "3mm-app" else (1202, 1203),
    )
    # Only disposable unit I/O is doubled; no live systemd unit is touched.
    from three_mm_runtime.application_activation import SystemdApplicationSupervisor

    monkeypatch.setattr(
        SystemdApplicationSupervisor,
        "recover_disabled",
        lambda self, identifier: state.calls.append(("stop", identifier)),
    )
    state.arguments = {
        "stage_root": tmp_path / "stage",
        "state_root": state.helper_state,
        "allowlist": tmp_path / "allowlist.json",
        "status_file": tmp_path / "status.json",
        "application_upload_root": state.root / "modules",
        "application_root": state.runtime,
        "application_key_root": state.transport_keys,
        "application_database": database,
    }
    return state


@ROOT_ONLY
def test_real_production_path_uses_core_principal_and_two_distinct_consents(production):
    state = production
    result = update_helper._handle_request(
        request(state), relational_peer_uid=1202, **state.arguments
    )
    assert result["ok"] is True, (result, state.frames)
    assert result["status"] == "prepared_not_started"
    assert state.frames == [
        "inspect",
        "issue_namespace",
        "checkpoint",
        "checkpoint",
        "checkpoint",
        "checkpoint",
        "issue_migration",
        "checkpoint",
        "checkpoint",
        "checkpoint",
        "checkpoint",
        "checkpoint",
    ]
    assert result["preparation"]["database"]["outcome"] == "prepared_not_started"
    assert state.database.stat().st_uid == 1200
    assert len(state.key_path.read_bytes()) == 32
    with sqlite3.connect(state.database) as db:
        assert db.execute(
            "SELECT revision FROM three_mm_schema_migrations"
        ).fetchall() == [("0001",), ("0002",)]
    with state.engine.connect() as db:
        assert db.exec_driver_sql(
            "SELECT enabled, status FROM application_extension_installations WHERE id=1"
        ).fetchone() == (0, "disabled")
    before = state.database.read_bytes()
    again = update_helper._handle_request(
        request(state), relational_peer_uid=1202, **state.arguments
    )
    assert again["ok"] is False
    assert state.database.read_bytes() == before


@ROOT_ONLY
@pytest.mark.parametrize("actor", ["user", "invalid", "stale"])
def test_invalid_actor_or_stale_grant_refuses_before_key_or_namespace(
    production, actor, caplog
):
    state = production
    value = request(state)
    if actor == "user":
        value["actor_token"] = state.user_token
    elif actor == "invalid":
        value["actor_token"] = "sensitive-invalid-token"
    else:
        value["expected_grant_record_revision"] = "f" * 32
    assert (
        update_helper._handle_request(
            value, relational_peer_uid=1202, **state.arguments
        )["ok"]
        is False
    )
    assert state.frames == ["inspect"]
    assert not state.instance.exists() and not state.key_path.exists()
    assert not list(state.helper_state.glob("namespace-key-*"))
    assert value["actor_token"] not in caplog.text


@ROOT_ONLY
@pytest.mark.parametrize("uid", [None, 0, 1200, True])
def test_only_actual_core_peer_is_accepted_not_root_app_or_claimed_group(
    production, uid
):
    state = production
    result = update_helper._handle_request(
        request(state), relational_peer_uid=uid, **state.arguments
    )
    assert result == {"ok": False, "error": "invalid_request"}
    assert not state.frames and not state.instance.exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"path": "/foreign"},
        {"transport_secret": "a" * 64},
        {"service_uid": 0},
        {"command": "anything"},
        {"configuration": {}},
        {"installation_id": True},
        {"confirm_owned_business_migrations": 1},
        {"confirm_fresh_owned_namespace": False},
    ],
)
def test_outer_helper_request_is_closed_and_has_no_paths_keys_uids_or_implicit_consent(
    changes,
):
    value = request(SimpleNamespace(token="hidden-token", expected_grant="a" * 32))
    with pytest.raises(ValueError):
        preparation_request({**value, **changes})


def test_fixed_systemd_core_worker_has_no_shell_or_sensitive_arguments(tmp_path):
    seen = []

    def run(arguments, **kwargs):
        seen.append((arguments, kwargs))
        return SimpleNamespace(returncode=0, stdout=b'{"ok":true,"result":{}}')

    client = CoreMetadataClient(
        core_uid=1202, database=tmp_path / "core.db", runner=run
    )
    client.call({"actor_token": "sensitive-token", "transport_secret": "a" * 64})
    arguments, kwargs = seen[0]
    assert arguments[:5] == (
        "/usr/bin/systemd-run",
        "--quiet",
        "--pipe",
        "--wait",
        "--collect",
    )
    assert "--property=User=3mm" in arguments and "--property=Group=3mm" in arguments
    assert "--property=EnvironmentFile=/etc/3mm/3mm.env" in arguments
    assert "--property=NoNewPrivileges=yes" in arguments
    assert "sensitive-token" not in str(arguments) and "a" * 64 not in str(arguments)
    assert "/bin/sh" not in arguments and "/bin/bash" not in arguments
    assert b"sensitive-token" in kwargs["input"] and kwargs["timeout"] == 25


@pytest.mark.parametrize("failure", ["timeout", "bad_response", "error"])
def test_metadata_unknown_response_is_never_retried(tmp_path, failure):
    seen = []

    def run(*args, **kwargs):
        seen.append(1)
        if failure == "timeout":
            raise subprocess.TimeoutExpired("fixed-worker", 25)
        return SimpleNamespace(returncode=1 if failure == "error" else 0, stdout=b"{}")

    client = CoreMetadataClient(
        core_uid=1202, database=tmp_path / "core.db", runner=run
    )
    with pytest.raises((ValueError, subprocess.TimeoutExpired)):
        client.call({})
    assert len(seen) == 1


@pytest.mark.parametrize(
    "changes", [{"command": "anything"}, {"action": "eval"}, {"installation_id": True}]
)
def test_core_metadata_dialect_rejects_unknown_operations_or_fields_before_manager_access(
    changes,
):
    value = {
        "action": "inspect",
        "installation_id": 1,
        "actor_token": "hidden-token",
        "expected_grant_record_revision": "a" * 32,
        **changes,
    }
    with pytest.raises(ValueError):
        dispatch(None, value)


@ROOT_ONLY
def test_core_worker_cannot_be_invoked_as_root_even_with_an_admin_token(production):
    state = production
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.services.application_relational_admin_worker",
            "--core-uid",
            "1202",
            "--database",
            str(state.engine.url.database),
        ],
        input=canonical(request(state)) + b"\n",
        capture_output=True,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout) == {
        "ok": False,
        "error": "local_authority_unavailable",
    }
    assert state.token.encode() not in result.stdout + result.stderr


@ROOT_ONLY
def test_lost_core_begin_ack_leaves_no_namespace_effect_and_never_runs_migrations(
    production,
):
    state = production
    original = state.metadata._run

    def lost(arguments, **kwargs):
        frame = json.loads(kwargs["input"])
        result = original(arguments, **kwargs)
        if frame["action"] == "checkpoint" and frame["phase"] == "begin":
            raise subprocess.TimeoutExpired("fixed-worker", 25)
        return result

    state.metadata._run = lost
    result = update_helper._handle_request(
        request(state), relational_peer_uid=1202, **state.arguments
    )
    assert result["ok"] is False
    assert "issue_migration" not in state.frames
    assert not state.instance.exists() and not state.key_path.exists()
    assert len(list(state.helper_state.glob("namespace-key-*"))) == 1
    with state.engine.connect() as db:
        values = [
            json.loads(row[0])
            for row in db.exec_driver_sql(
                "SELECT payload FROM application_authority_actions"
            )
        ]
    source = next(
        value
        for value in values
        if value["data"]["operation"] == "relational_prepare_namespace"
    )
    assert source["state"] == "execution_unconfirmed"


@ROOT_ONLY
def test_service_socket_obtains_peer_uid_from_os_not_json(production, monkeypatch):
    state = production
    captured = []

    def handle(value, **kw):
        captured.append(kw["relational_peer_uid"])
        return {"ok": False, "error": "invalid_request"}

    monkeypatch.setattr(update_helper, "_handle_request", handle)
    server, client = socket.socketpair()
    with server, client:
        client.sendall(canonical(request(state)) + b"\n")
        update_helper._serve_connection(server, **state.arguments)
        assert json.loads(client.recv(1024))["ok"] is False
    assert captured == [os.geteuid()]


def test_client_distinguishes_preparation_from_activation_and_requires_closed_receipts(
    monkeypatch,
):
    client = UpdateHelperClient(Path("/unused"))
    captured = []

    def response(value, **kw):
        captured.append((value, kw))
        return {
            "ok": True,
            "status": "prepared_not_started",
            "preparation": {"namespace": {}, "database": {}},
        }

    monkeypatch.setattr(client, "_request", response)
    with pytest.raises(UpdateHelperError, match="unconfirmed"):
        client.prepare_application_relational(
            1,
            "hidden-token",
            "a" * 32,
            confirm_fresh_owned_namespace=True,
            confirm_owned_business_migrations=True,
        )
    assert captured[0][1] == {"expected_status": "prepared_not_started"}
    assert "configuration" not in captured[0][0]


@ROOT_ONLY
def test_actual_core_admin_cli_unix_peer_and_metadata_worker_prepare_without_enable(
    production,
):
    state = production
    socket_path = state.helper_state.parent / "helper.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chown(socket_path, 0, 1203)
    socket_path.chmod(0o660)
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

    worker = threading.Thread(target=serve)
    worker.start()
    environment = dict(
        os.environ,
        DATABASE_URL=f"sqlite:///{state.engine.url.database}",
        UPLOADS_DIR=str(state.root),
        THREE_MM_AUTHORITY_REVIEW_KEY_DIR=str(state.key_directory),
        THREE_MM_APPLICATION_HELPER_SOCKET=str(socket_path),
        PYTHONDONTWRITEBYTECODE="1",
    )
    try:
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.services.application_authority_admin",
                "prepare-relational",
                "--installation-id",
                "1",
                "--expected-grant-record-revision",
                state.expected_grant,
                "--confirm-fresh-owned-namespace",
                "--confirm-owned-business-migrations",
            ],
            input=state.token.encode() + b"\n",
            capture_output=True,
            timeout=90,
            start_new_session=True,  # No controlling TTY: consume the private test input pipe.
            user=1202,
            group=1203,
            extra_groups=(),
            env=environment,
        )
    finally:
        worker.join(timeout=95)
        server.close()
    assert not worker.is_alive() and not errors
    assert process.returncode == 0, (process.stderr.decode(), state.frames)
    result = json.loads(process.stdout)
    assert result["status"] == "prepared_not_started"
    assert result["permission_approval"] == "not_evaluated"
    assert state.token.encode() not in process.stdout + process.stderr
    assert state.database.exists() and state.database.stat().st_uid == 1200
    with state.engine.connect() as db:
        assert db.exec_driver_sql(
            "SELECT enabled, status FROM application_extension_installations WHERE id=1"
        ).fetchone() == (0, "disabled")
