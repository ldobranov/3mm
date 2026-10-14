"""Local CLI/Core OS peer/metadata worker -> real non-root prepared startup.

Only disposable Linux paths and numeric process credentials; no live accounts,
units, releases or authority. Production systemd argv remains a separate check.
"""

import hashlib
import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ModulePackage
from backend.services.application_relational_admin_worker import dispatch
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_relational_activation import ProcessSupervisor
from backend.tests.test_application_relational_preparation import (
    ROOT_ONLY,
    identity,
    managed_installed,
    source_installed,
    source_subject,
)
from backend.tests.test_application_relational_production import (
    production as original_production,
)
from backend.tests.test_application_relational_production import (
    request as preparation_request,
)
from backend.tests.test_application_relational_registration import (
    approve,
)
from backend.tests.test_application_relational_registration import fresh as catalog
from backend.tests.test_application_relational_registration import (
    register,
)
from backend.tests.test_application_relational_runtime import SERVICE
from three_mm_application_sdk.relational_wire import canonical
from three_mm_runtime import application_lifecycle as locks
from three_mm_runtime import application_relational_activation as activation_helper
from three_mm_runtime import update_helper
from three_mm_runtime.application_relational_control import (
    CoreMetadataClient,
    activation_request,
)
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Actual Core OS peer/worker")


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(prefix="3mm-ctl-") as directory:
        yield Path(directory)


@pytest.fixture
def initial(catalog, tmp_path, monkeypatch):
    state = catalog
    manifest = state.validated.manifest.model_dump(mode="json")
    definition = state.validated.application_extension.model_dump(mode="json")
    with zipfile.ZipFile(state.archive) as old:
        previous_wheel = old.read(definition["service"]["artifact"])
    wheel = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(previous_wheel)) as old,
        zipfile.ZipFile(wheel, "w") as target,
    ):
        for entry in old.namelist():
            target.writestr(
                entry, SERVICE if entry.endswith("/service.py") else old.read(entry)
            )
    definition["service"]["artifact_sha256"] = hashlib.sha256(
        wheel.getvalue()
    ).hexdigest()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        target.writestr("manifest.json", json.dumps(manifest))
        target.writestr("application-extension.json", json.dumps(definition))
        target.writestr(definition["service"]["artifact"], wheel.getvalue())
    state.validated = validate_module_package(output.getvalue())
    state.archive = state.root / "modules" / (state.validated.sha256 + ".zip")
    state.archive.write_bytes(output.getvalue())
    with state.engine.begin() as db:
        db.execute(
            update(ModulePackage).values(
                sha256=state.validated.sha256,
                manifest=manifest,
                size_bytes=len(output.getvalue()),
            )
        )
    assert register(state)["active_version"] is None
    approve(state, 1)
    tmp_path.chmod(0o755)
    state.runtime, state.transport_keys, state.helper_state = [
        tmp_path / name for name in ("runtime", "keys", "helper-state")
    ]
    for path in (state.runtime, state.transport_keys, state.helper_state):
        path.mkdir(mode=0o750)
    for path in (state.runtime, state.transport_keys):
        os.chown(path, 0, 1201)
    with Session(state.engine) as db:
        state.instance = state.runtime / db.get(Installation, 1).instance_id
    state.database = state.instance / "data/state.sqlite3"
    state.data = state.database.parent
    state.key_path = state.transport_keys / (state.instance.name + ".key")
    state.calls = []
    state.expected_grant = state.manager.inspect(1)["grant_record_revision"]
    monkeypatch.setattr(locks, "RELEASE_MUTATION_LOCK", tmp_path / "release.lock")
    return state


@pytest.fixture
def deployed(original_production, monkeypatch):
    state = original_production
    database = Path(state.engine.url.database)
    state.worker_root = state.runtime
    state.worker_arguments_root = state.runtime
    state.environment = dict(
        os.environ,
        DATABASE_URL=f"sqlite:///{database}",
        UPLOADS_DIR=str(state.root),
        THREE_MM_AUTHORITY_REVIEW_KEY_DIR=str(state.key_directory),
        THREE_MM_APPLICATION_ROOT=str(state.runtime),
        PYTHONDONTWRITEBYTECODE="1",
    )

    def runner(arguments, **kwargs):
        frame = json.loads(kwargs["input"])
        state.frames.append(frame["action"])
        environment = dict(
            state.environment, THREE_MM_APPLICATION_ROOT=str(state.worker_root)
        )
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.services.application_relational_admin_worker",
                "--core-uid",
                "1202",
                "--database",
                str(database),
                "--application-root",
                str(state.worker_arguments_root),
            ],
            user=1202,
            group=1203,
            extra_groups=(),
            env=environment,
            **kwargs,
        )

    state.metadata = CoreMetadataClient(
        core_uid=1202, database=database, application_root=state.runtime, runner=runner
    )
    state.supervisor = ProcessSupervisor(state)
    state.preparation_id = "b" * 32  # Never used to authorize a successful start.
    monkeypatch.setattr(
        activation_helper, "PreparedServiceSupervisor", lambda: state.supervisor
    )
    try:
        yield state
    finally:
        state.supervisor.recover_disabled(state.instance.name)


@pytest.fixture
def prepared(deployed):
    state = deployed
    result = update_helper._handle_request(
        preparation_request(state), relational_peer_uid=1202, **state.arguments
    )
    assert result["status"] == "prepared_not_started", (result, state.frames)
    state.preparation_id = result["preparation"]["database"]["preparation_id"]
    state.frames.clear()
    return state


def request(state, **changes):
    return {
        "action": "activate_application_relational",
        "installation_id": 1,
        "actor_token": state.token,
        "expected_grant_record_revision": state.expected_grant,
        "source_preparation_id": state.preparation_id,
        "request_id": identity(),
        "confirm_start_prepared_service": True,
        **changes,
    }


def handle(state, value=None, **changes):
    return update_helper._handle_request(
        value or request(state),
        **{"relational_peer_uid": 1202, **state.arguments, **changes},
    )


def assert_fenced(state):
    with state.engine.connect() as db:
        row = db.exec_driver_sql(
            "SELECT enabled, status, authority_mode FROM application_extension_installations WHERE id=1"
        ).fetchone()
    assert row.authority_mode == "review_required"


@ROOT_ONLY
def test_actual_core_worker_activation_preserves_preparation_and_old_grant(prepared):
    state = prepared
    before = [
        path.read_bytes()
        for path in (
            state.database,
            state.key_path,
            state.instance / "active.json",
            state.instance / "relational.json",
        )
    ]
    with state.engine.connect() as db:
        old_grant = db.exec_driver_sql(
            "SELECT payload FROM application_authority_grants WHERE installation_id=1"
        ).scalar_one()
        assert (
            db.exec_driver_sql(
                "SELECT active_version FROM application_extension_installations WHERE id=1"
            ).scalar_one()
            is None
        )
    value = request(state)
    result = handle(state, value)
    assert result["status"] == "active_review_required", (result, state.frames)
    assert result["activation"]["preparation_id"] == value["request_id"]
    assert (
        state.frames
        == ["inspect_activation", "issue_activation"] + ["activation_checkpoint"] * 4
    )
    assert state.supervisor.starts == 1
    assert json.loads((state.data / "factory.json").read_text()) == {
        "uid": 1200,
        "denied": [True, True, True],
    }
    assert before == [
        path.read_bytes()
        for path in (
            state.database,
            state.key_path,
            state.instance / "active.json",
            state.instance / "relational.json",
        )
    ]
    with state.engine.connect() as db:
        row = db.exec_driver_sql(
            "SELECT active_version, enabled, status, socket_path FROM application_extension_installations WHERE id=1"
        ).fetchone()
        assert row == (
            state.validated.application_extension.version,
            1,
            "active",
            str(state.instance / "run/service.sock"),
        )
        assert (
            db.exec_driver_sql(
                "SELECT payload FROM application_authority_grants WHERE installation_id=1"
            ).scalar_one()
            == old_grant
        )
    assert_fenced(state)
    assert handle(state, value)["ok"] is False
    assert state.supervisor.starts == 1


@ROOT_ONLY
@pytest.mark.parametrize("uid", [None, 0, 1200, True])
def test_actual_os_core_peer_required_before_metadata_key_or_start(deployed, uid):
    assert handle(deployed, relational_peer_uid=uid) == {
        "ok": False,
        "error": "invalid_request",
    }
    assert not deployed.frames and not deployed.supervisor.starts
    assert not deployed.key_path.exists()


@ROOT_ONLY
@pytest.mark.parametrize("problem", ["user", "stale", "invalid", "layout"])
def test_current_actor_exact_preparation_and_layout_are_required(
    deployed, problem, caplog
):
    state = deployed
    changes = {
        "user": {"actor_token": state.user_token},
        "invalid": {"actor_token": "sensitive-invalid-token"},
        "stale": {"expected_grant_record_revision": "f" * 32},
    }.get(problem, {})
    if problem == "layout":
        state.worker_root = state.runtime / "wrong-layout"
    value = request(state, **changes)
    result = handle(state, value)
    assert result == {"ok": False, "error": "relational_activation_unconfirmed"}
    assert not state.supervisor.starts
    assert state.frames == ["inspect_activation"]
    assert not state.key_path.exists()
    assert value["actor_token"] not in caplog.text


@ROOT_ONLY
def test_wrong_prepared_source_cannot_reserve_or_start(prepared):
    state = prepared
    before = state.database.read_bytes()
    result = handle(state, request(state, source_preparation_id="f" * 32))
    assert result == {"ok": False, "error": "relational_activation_unconfirmed"}
    assert state.frames == ["inspect_activation", "issue_activation"]
    assert state.database.read_bytes() == before and not state.supervisor.starts


@ROOT_ONLY
@pytest.mark.parametrize("phase", ["issue", "begin", "finish"])
def test_lost_metadata_ack_never_issues_second_start_or_restores_grants(
    prepared, phase
):
    state = prepared
    original = state.metadata._run
    value = request(state)
    before = (state.instance / "relational.json").read_bytes()

    def lost(arguments, **kw):
        frame = json.loads(kw["input"])
        result = original(arguments, **kw)
        if (phase == "issue" and frame["action"] == "issue_activation") or (
            frame["action"] == "activation_checkpoint" and frame["phase"] == phase
        ):
            raise subprocess.TimeoutExpired("fixed-worker", 25)
        return result

    state.metadata._run = lost
    assert handle(state, value)["error"] == "relational_activation_unconfirmed"
    assert state.supervisor.starts == (1 if phase == "finish" else 0)
    assert state.supervisor.process is None
    assert (state.instance / "relational.json").read_bytes() == before
    if phase != "issue":
        assert_fenced(state)
        assert (
            state.helper_state
            / ("relational-activation-" + state.instance.name + ".json")
        ).is_file()
    assert handle(state, value)["ok"] is False
    assert state.supervisor.starts == (1 if phase == "finish" else 0)


@pytest.mark.parametrize(
    "changes",
    [
        {"database_path": "/foreign"},
        {"runtime_root": "/foreign"},
        {"transport_secret": "a" * 64},
        {"service_uid": 0},
        {"configuration": {}},
        {"command": "anything"},
        {"installation_id": True},
        {"source_preparation_id": 1},
        {"request_id": "A" * 32},
        {"expected_grant_record_revision": "bad"},
        {"confirm_start_prepared_service": False},
        {"confirm_start_prepared_service": 1},
    ],
)
def test_closed_typed_request_has_no_paths_keys_commands_or_implicit_consent(changes):
    value = request(
        SimpleNamespace(
            token="hidden", expected_grant="a" * 32, preparation_id="b" * 32
        )
    )
    with pytest.raises(ValueError):
        activation_request(dict(value, **changes))


@pytest.mark.parametrize(
    "frame",
    [
        {"action": "inspect_activation", "runtime_root": "/foreign"},
        {
            "action": "issue_activation",
            "transport_secret": "a" * 64,
            "request_id": "a" * 32,
        },
        {
            "action": "activation_checkpoint",
            "transport_secret": "a" * 64,
            "ticket": [],
            "phase": "finish",
            "receipt": {},
        },
        {"action": []},
    ],
)
def test_private_metadata_dialect_is_closed_before_manager_access(frame):
    value = {
        "installation_id": 1,
        "actor_token": "hidden",
        "expected_grant_record_revision": "a" * 32,
        **frame,
    }
    with pytest.raises(ValueError):
        dispatch(None, value)


@pytest.mark.parametrize("problem", ["wrong_id", "wrong_outcome", "extra", "malformed"])
def test_client_refuses_ambiguous_result_and_does_not_retry(monkeypatch, problem):
    value = request(
        SimpleNamespace(
            token="hidden", expected_grant="a" * 32, preparation_id="b" * 32
        )
    )
    result = {
        "version": 1,
        "preparation_id": value["request_id"],
        "lifecycle_sha256": "d" * 64,
        "outcome": "active_review_required",
        "signature": "e" * 64,
    }
    if problem == "wrong_id":
        result["preparation_id"] = "f" * 32
    elif problem == "wrong_outcome":
        result["outcome"] = "prepared_not_started"
    elif problem == "extra":
        result["transport_secret"] = "a" * 64
    else:
        result = []
    calls = []
    client = UpdateHelperClient(Path("/unused"))

    def reply(payload, **kw):
        calls.append(payload)
        assert kw == {"expected_status": "active_review_required"}
        return {"ok": True, "status": "active_review_required", "activation": result}

    monkeypatch.setattr(client, "_request", reply)
    with pytest.raises(UpdateHelperError, match="unconfirmed"):
        client.activate_application_relational(
            1,
            "hidden",
            "a" * 32,
            source_preparation_id="b" * 32,
            request_id=value["request_id"],
            confirm_start_prepared_service=True,
        )
    assert len(calls) == 1


@ROOT_ONLY
def test_cli_actual_nonroot_core_peer_worker_and_application_host(prepared):
    state = prepared
    path = state.helper_state.parent / "control.sock"
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
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.services.application_authority_admin",
                "activate-relational",
                "--installation-id",
                "1",
                "--source-preparation-id",
                state.preparation_id,
                "--request-id",
                request_id,
                "--expected-grant-record-revision",
                state.expected_grant,
                "--confirm-start-prepared-service",
            ],
            input=state.token.encode() + b"\n",
            capture_output=True,
            timeout=90,
            start_new_session=True,
            user=1202,
            group=1203,
            extra_groups=(),
            env=dict(state.environment, THREE_MM_APPLICATION_HELPER_SOCKET=str(path)),
        )
    finally:
        thread.join(timeout=95)
        server.close()
    assert not thread.is_alive() and not errors
    assert process.returncode == 0, (process.stderr.decode(), state.frames)
    result = json.loads(process.stdout)
    assert result["status"] == "active_review_required"
    assert result["activation"]["preparation_id"] == request_id
    assert result["permission_approval"] == "not_evaluated"
    assert result["boot_autostart_enabled"] is False
    assert state.token.encode() not in process.stdout + process.stderr
    assert json.loads((state.data / "factory.json").read_text())["uid"] == 1200
    assert_fenced(state)


@ROOT_ONLY
@pytest.mark.parametrize("duplicate", ["action", "request_id"])
def test_duplicate_sensitive_frame_is_refused_before_handler(
    tmp_path, monkeypatch, duplicate
):
    value = request(
        SimpleNamespace(
            token="hidden", expected_grant="a" * 32, preparation_id="b" * 32
        )
    )
    encoded = canonical(value).decode()
    frame = encoded[:-1] + ',"' + duplicate + '":"' + value[duplicate] + '"}\n'
    monkeypatch.setattr(
        update_helper,
        "_handle_request",
        lambda *a, **kw: pytest.fail("Ambiguous frame reached handler"),
    )
    server, client = socket.socketpair()
    with server, client:
        client.sendall(frame.encode())
        update_helper._serve_connection(
            server,
            stage_root=tmp_path / "stage",
            state_root=tmp_path / "state",
            allowlist=tmp_path / "allowlist",
            status_file=tmp_path / "status",
        )
        assert json.loads(client.recv(1024)) == {
            "ok": False,
            "error": "invalid_request",
        }


def test_fixed_worker_root_dependency_is_not_caller_json_or_sensitive_argv(tmp_path):
    client = CoreMetadataClient(
        core_uid=1202,
        database=tmp_path / "core.db",
        application_root=tmp_path / "fixed-runtime",
    )
    args = client.arguments
    assert args[args.index("--application-root") + 1] == str(tmp_path / "fixed-runtime")
    assert "--property=User=3mm" in args and "--property=NoNewPrivileges=yes" in args
    assert "actor_token" not in str(args) and "transport_secret" not in str(args)


def test_client_transport_timeout_is_unconfirmed_without_retry(monkeypatch):
    client = UpdateHelperClient(Path("/unused"))
    calls = []

    def failed(*a, **kw):
        calls.append(1)
        raise UpdateHelperError("Transport outcome unknown")

    monkeypatch.setattr(client, "_request", failed)
    with pytest.raises(UpdateHelperError, match="Do not retry"):
        client.activate_application_relational(
            1,
            "hidden",
            "a" * 32,
            source_preparation_id="b" * 32,
            request_id="c" * 32,
            confirm_start_prepared_service=True,
        )
    assert calls == [1]


@pytest.mark.parametrize("action", [[], {}, None, True])
def test_malformed_action_cannot_crash_shared_helper(action, tmp_path):
    result = update_helper._handle_request(
        {"action": action},
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist",
        status_file=tmp_path / "status",
    )
    assert result == {"ok": False, "error": "invalid_request"}
