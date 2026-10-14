"""Actual non-root cold host pre-import gate; no live boot/unit/account writes.

Import witness is added BEFORE review/preparation. Normal real review/grants and
Root start/enable are used, never SQL enable/fake trust. Boot/unit I/O remain
adapters; cold child, peer credentials, metadata and platform sockets are real.
"""

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.user import User
from backend.services import application_authority_management as authority
from backend.services import application_relational_startup as core
from backend.services.application_extensions import ApplicationGatewayError
from backend.tests import test_application_relational_runtime as reference
from backend.tests.test_application_relational_activation import (
    ProcessSupervisor,
    start,
)
from backend.tests.test_application_relational_activation_recovery import recover
from backend.tests.test_application_relational_boot import (
    ROOT_ONLY,
    SECRET,
    apply,
)
from backend.tests.test_application_relational_boot import checkpoint as boot_checkpoint
from backend.tests.test_application_relational_boot import enable as enable_boot
from backend.tests.test_application_relational_boot import (
    identity,
)
from backend.tests.test_application_relational_boot import issue as issue_boot
from backend.tests.test_application_relational_boot import (
    issue_stop,
    journal,
    managed_installed,
    migratable,
    native,
    physical,
    prepared_paths,
    running,
    source_installed,
    source_subject,
    stopped,
    tmp_path,
    unchanged_authority,
)
from backend.tests.test_application_relational_reactivation import (
    issue as issue_restart,
)
from backend.tests.test_application_relational_runtime import invoke
from three_mm_application_sdk import ApplicationPlatformClient
from three_mm_application_sdk.relational_wire import (
    _activation_ticket,
    _preparation_ticket,
    _RelationalBootStartupPermit,
    canonical,
    sign_metadata,
)
from three_mm_runtime import application_relational_boot as boot_helper
from three_mm_runtime import application_relational_boot_policy as policy_helper
from three_mm_runtime import application_relational_preparation as preparation_helper

pytestmark = [
    pytest.mark.skipif(os.name != "posix", reason="Actual POSIX host/peer"),
    ROOT_ONLY,
]


@pytest.fixture
def marked(request, monkeypatch):
    monkeypatch.setattr(
        reference,
        "SERVICE",
        reference.SERVICE + "\nPath('service-imported').write_text(str(os.getpid()))\n",
    )
    return request.getfixturevalue("running")


@pytest.fixture
def bootable(marked):
    state = marked
    state.boot_ticket = issue_boot(state)
    enable_boot(state, state.boot_ticket)
    return state


def records(state):
    with state.keys.locked() as key, Session(state.engine) as db:
        return [
            authority._load(db, key, "action", row, row.request_id)
            for row in db.scalars(select(Action))
            if json.loads(row.payload)["data"].get("operation") == core.OPERATION
        ]


def cold(state, *, allowed):
    supervisor = state.actual_supervisor
    process = supervisor.process
    launch = process.args
    supervisor.recover_disabled(state.instance.name)
    (state.instance / "run/service.sock").unlink(missing_ok=True)
    supervisor.process = subprocess.Popen(
        launch,
        user=1200,
        group=1201,
        extra_groups=[],
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=state.data,
        env={"PATH": "/usr/bin:/bin"},
    )
    candidate = supervisor.process
    if not allowed:
        output, error = candidate.communicate(timeout=10)
        assert candidate.returncode != 0, (output, error)
        assert not (state.instance / "run/service.sock").exists()
        assert b"startup" in error.lower() or b"boot" in error.lower(), error
        return error
    deadline = time.monotonic() + 10
    while not (state.instance / "run/service.sock").is_socket():
        if candidate.poll() is not None:
            raise AssertionError(candidate.communicate(timeout=2)[1].decode())
        assert time.monotonic() < deadline, "Cold host startup did not complete"
        time.sleep(0.05)
    supervisor.verify_identity(state.instance.name, 1200, 1201, running=True)
    return candidate.pid


def before_import(state):
    return (state.data / "service-imported").read_bytes(), (
        state.data / "factory.json"
    ).read_bytes()


def test_real_cold_start_uses_fresh_kernel_nonce_before_import_without_grant_replay(
    bootable,
):
    state = bootable
    before = unchanged_authority(state)
    saved = {
        path: path.read_bytes()
        for path in (
            state.database,
            state.instance / "active.json",
            state.instance / "relational.json",
            state.instance / policy_helper.REQUIRED_NAME,
            state.instance / policy_helper.POLICY_NAME,
            state.transport_keys / (state.instance.name + ".key"),
        )
    }
    old_pid = state.actual_supervisor.process.pid
    pid = cold(state, allowed=True)
    assert pid != old_pid and (state.data / "service-imported").read_text() == str(pid)
    assert unchanged_authority(state) == before
    assert all(path.read_bytes() == payload for path, payload in saved.items())
    admitted = records(state)
    assert len(admitted) == 1 and admitted[0]["state"] == "admitted"
    permit = admitted[0]["data"]["permit"]
    assert (
        permit["process_pid"] == pid
        and permit["service_uid"] == 1200
        and permit["service_gid"] == 1201
    )
    assert invoke(state, "inspect") == {"values": ["preserved"]}
    assert json.loads((state.data / "factory.json").read_text())["denied"] == [True] * 3
    with Session(state.engine) as db, pytest.raises(core.RelationalStartupError):
        core.admit_boot_startup(
            db,
            1,
            permit["runtime_nonce"],
            transport_secret=SECRET,
            runtime_root=state.runtime,
            peer_credentials=(pid, 1200, 1201),
        )
    assert len(records(state)) == 1
    second_pid = cold(state, allowed=True)
    assert second_pid != pid
    admitted = records(state)
    assert (
        len(admitted) == 2
        and len({x["data"]["permit"]["runtime_nonce"] for x in admitted}) == 2
    )
    assert unchanged_authority(state) == before


def test_old_boot_setting_is_history_not_a_renewed_enable_ticket(marked, monkeypatch):
    state = marked
    real_boot, now = authority._clock()
    old_boot = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    with monkeypatch.context() as patch:
        patch.setattr(authority, "_clock", lambda: (old_boot, now))
        patch.setattr(preparation_helper, "_clock", lambda: (old_boot, now))
        state.boot_ticket = issue_boot(state)
        enable_boot(state, state.boot_ticket)
    original = journal(state, state.boot_ticket)
    assert state.boot_ticket["boot_id"] != authority._clock()[0]
    pid = cold(state, allowed=True)
    permit = records(state)[0]["data"]["permit"]
    assert permit["boot_id"] == real_boot and permit["process_pid"] == pid
    assert journal(state, state.boot_ticket) == original
    with pytest.raises(authority.AuthorityManagementError):
        boot_checkpoint(state, state.boot_ticket, "authorize")


@pytest.mark.parametrize(
    "drift",
    [
        "revoke",
        "native",
        "grant",
        "author_blocked",
        "author_demoted",
        "source",
        "disabled",
        "layout",
        "seal",
        "key",
        "generation",
        "epoch",
        "configuration",
    ],
)
def test_current_core_authority_refuses_before_import_not_just_business_sql(
    bootable, drift
):
    state = bootable
    imported = before_import(state)
    if drift == "revoke":
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=state.boot_ticket["grant_record_revision"],
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
    elif drift == "grant":
        apply(state, state.native_id)
    elif drift == "source":
        issue_stop(state, state.started)  # Genuine new stop reservation/fence.
    elif drift == "key":
        state.keys.rotate(expected_key_id=state.keys.identity().key_id)
    else:
        with state.engine.begin() as db:
            if drift.startswith("author_"):
                db.execute(
                    update(User)
                    .where(User.id == 1)
                    .values(
                        **(
                            {"is_blocked": True}
                            if drift == "author_blocked"
                            else {"role": "operator"}
                        )
                    )
                )
            elif drift == "seal":
                db.execute(
                    update(Action)
                    .where(Action.request_id == state.boot_ticket["preparation_id"])
                    .values(seal="0" * 64)
                )
            elif drift == "generation":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            else:
                db.execute(
                    update(Installation).values(
                        **{
                            "disabled": {"enabled": False, "status": "disabled"},
                            "layout": {"socket_path": "/foreign/run/service.sock"},
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
    cold(state, allowed=False)
    assert before_import(state) == imported and records(state) == []


@pytest.mark.parametrize(
    "problem",
    [
        "missing_policy",
        "missing_marker",
        "pending",
        "owner",
        "group",
        "symlink",
        "duplicate",
        "oversized",
        "signature",
        "receipt",
    ],
)
def test_missing_or_untrusted_root_gate_never_falls_back_to_manual_start(
    bootable, problem
):
    state = bootable
    imported = before_import(state)
    path = state.instance / policy_helper.POLICY_NAME
    if problem == "missing_policy":
        path.unlink()  # Disposable test corruption, required marker survives.
    elif problem == "missing_marker":
        (state.instance / policy_helper.REQUIRED_NAME).unlink()
    elif problem == "owner":
        os.chown(path, 1200, 1201)
    elif problem == "group":
        os.chown(path, 0, 0)
    elif problem == "symlink":
        target = path.with_suffix(".retained")
        path.rename(target)
        path.symlink_to(target)
    elif problem == "duplicate":
        path.write_bytes(b'{"version":1,"version":1}')
    elif problem == "oversized":
        path.write_bytes(b" " * 8193)
    else:
        value = json.loads(path.read_text())
        if problem == "pending":
            value.update(phase="boot_pending", receipt=None)
        elif problem == "signature":
            value["ticket"]["signature"] = "0" * 64
        else:
            value["receipt"]["signature"] = "0" * 64
        path.write_bytes(canonical(value))
    cold(state, allowed=False)
    assert before_import(state) == imported and records(state) == []


@pytest.mark.parametrize(
    "problem", ["lost", "nonce", "pid", "policy", "deadline", "purpose", "extra"]
)
def test_lost_or_wrong_fresh_handoff_consumes_nonce_without_import_or_retry(
    bootable, problem, monkeypatch
):
    state = bootable
    imported = before_import(state)
    dispatch = state.server._dispatch
    calls = []

    def damaged(db, installation, request, **kwargs):
        result = dispatch(db, installation, request, **kwargs)
        if request["action"] != "relational.boot.startup":
            return result
        calls.append(request["runtime_nonce"])
        if problem == "lost":
            raise OSError("Response lost AFTER admission commit")
        changes = {
            "nonce": {"runtime_nonce": identity()},
            "pid": {"process_pid": 1},
            "policy": {"policy_sha256": "0" * 64},
            "extra": {"sql": "SELECT 1"},
            "deadline": {
                "issued_at_ms": result["issued_at_ms"] - 6000,
                "deadline_ms": result["deadline_ms"] - 6000,
            },
        }
        return sign_metadata(
            SECRET,
            "activation_result" if problem == "purpose" else "boot_startup",
            {**result, **changes.get(problem, {})},
        )

    monkeypatch.setattr(state.server, "_dispatch", damaged)
    cold(state, allowed=False)
    assert len(calls) == 1 and before_import(state) == imported
    admitted = records(state)
    assert (
        len(admitted) == 1
        and admitted[0]["data"]["permit"]["runtime_nonce"] == calls[0]
    )


def test_required_marker_precedes_partial_publication_and_any_enable(
    marked, monkeypatch
):
    state = marked
    ticket = issue_boot(state)
    original = policy_helper._exclusive_file

    def partial(path, *a, **kw):
        if path.name == policy_helper.POLICY_NAME:
            raise OSError("Policy publication interrupted")
        return original(path, *a, **kw)

    monkeypatch.setattr(policy_helper, "_exclusive_file", partial)
    with pytest.raises(boot_helper.RelationalBootEnableError):
        enable_boot(state, ticket)
    assert (state.instance / policy_helper.REQUIRED_NAME).is_file()
    assert not (state.instance / policy_helper.POLICY_NAME).exists()
    assert state.boot_supervisor.enables == 0
    imported = before_import(state)
    cold(state, allowed=False)
    assert before_import(state) == imported


def test_lost_finish_ack_does_not_promote_core_history_to_root_boot_permission(marked):
    state = marked
    ticket = issue_boot(state)

    def lost(value, phase, **kw):
        result = boot_checkpoint(state, value, phase, **kw)
        if phase == "finish":
            raise OSError("Core finish reply lost")
        return result

    with pytest.raises(boot_helper.RelationalBootEnableError):
        enable_boot(state, ticket, checkpoint=lost)
    assert journal(state, ticket)["state"] == "confirmed"
    assert (
        policy_helper.read_boot_policy(state.instance, SECRET, confirmed=False)["phase"]
        == "boot_pending"
    )
    imported = before_import(state)
    cold(state, allowed=False)
    assert before_import(state) == imported and records(state) == []


def test_explicit_verified_stop_archives_boot_gate_before_new_manual_start(bootable):
    state = bootable
    source = state.started
    paths = {
        state.instance / name: (state.instance / name).read_bytes()
        for name in (policy_helper.REQUIRED_NAME, policy_helper.POLICY_NAME)
    }
    stop = issue_stop(state, source)
    assert recover(state, stop)["outcome"] == "stopped_review_required"
    assert not policy_helper.boot_gate_present(state.instance)
    archived = list(state.helper_state.glob("relational-boot-archive-*.json"))
    assert len(archived) == 2
    assert {x.read_bytes() for x in archived} == set(paths.values())
    assert all(
        x.stat().st_uid == x.stat().st_gid == 0 and x.stat().st_mode & 0o777 == 0o600
        for x in archived
    )
    apply(state, state.native_id)
    state.started = issue_restart(state, stop)
    state.actual_supervisor = ProcessSupervisor(state)
    assert start(state, state.started)["outcome"] == "active_review_required"
    apply(state, state.native_id)
    assert invoke(state, "inspect") == {"values": ["preserved"]}


@pytest.mark.parametrize(
    "extra",
    [
        {"uid": 1200},
        {"pid": 1},
        {"root": "/foreign"},
        {"ticket": {}},
        {"sql": "SELECT 1"},
    ],
)
def test_closed_startup_frame_rejects_application_selected_context(bootable, extra):
    state = bootable
    with pytest.raises(RuntimeError, match="metadata is invalid"):
        ApplicationPlatformClient(
            state.server.socket_path, state.instance.name, SECRET
        )._call("relational.boot.startup", {"runtime_nonce": identity(), **extra})
    assert records(state) == []


@pytest.mark.parametrize("uid", [0, 1202, 1234])
def test_real_kernel_peer_not_json_or_core_group_is_required(bootable, uid):
    state = bootable
    script = (
        "import sys;sys.path.insert(0,"
        + repr(str(Path(__file__).resolve().parents[2]))
        + ");"
        "from pathlib import Path;from three_mm_application_sdk import ApplicationPlatformClient;"
        "ApplicationPlatformClient(Path("
        + repr(str(state.server.socket_path))
        + "),"
        + repr(state.instance.name)
        + ","
        + repr(SECRET)
        + ")._call('relational.boot.startup',{'runtime_nonce':'"
        + "a" * 32
        + "'})"
    )
    result = subprocess.run(
        [state.actual_supervisor.process.args[0], "-I", "-c", script],
        user=uid,
        group=1201,
        extra_groups=[],
        capture_output=True,
        start_new_session=True,
        env={"PATH": "/usr/bin:/bin"},
        cwd=state.data if uid == 0 else state.runtime,
        timeout=10,
    )
    assert result.returncode != 0 and b"startup authority unavailable" in result.stderr
    assert records(state) == []


def test_source_process_peer_must_match_metadata_socket_not_another_same_uid_child(
    bootable,
):
    state = bootable
    # Correct service UID/GID and authentic secret still cannot borrow another
    # process's metadata worker/runtime nonce.
    script = (
        "import sys;sys.path.insert(0,"
        + repr(str(Path(__file__).resolve().parents[2]))
        + ");from pathlib import Path;from three_mm_application_sdk import ApplicationPlatformClient;ApplicationPlatformClient(Path("
        + repr(str(state.server.socket_path))
        + "),"
        + repr(state.instance.name)
        + ","
        + repr(SECRET)
        + ")._call('relational.boot.startup',{'runtime_nonce':'"
        + "a" * 32
        + "'})"
    )
    result = subprocess.run(
        [state.actual_supervisor.process.args[0], "-I", "-c", script],
        user=1200,
        group=1201,
        extra_groups=[],
        capture_output=True,
        start_new_session=True,
        cwd=state.data,
        env={"PATH": "/usr/bin:/bin"},
        timeout=10,
    )
    assert result.returncode != 0 and b"startup authority unavailable" in result.stderr
    assert records(state) == []


def test_startup_permit_cannot_be_used_as_sql_start_or_migration_ticket(bootable):
    cold(bootable, allowed=True)
    permit = records(bootable)[0]["data"]["permit"]
    for parser in (_activation_ticket, _preparation_ticket):
        with pytest.raises(ValidationError):
            parser(permit)
    with pytest.raises(ValidationError):
        _RelationalBootStartupPermit.model_validate(
            dict(permit, deadline_ms=permit["issued_at_ms"] + 5001)
        )


def test_exhausted_journal_refuses_import_without_pruning_or_new_rights(
    bootable, monkeypatch
):
    state = bootable
    imported = before_import(state)
    before = unchanged_authority(state)
    monkeypatch.setattr(core.preparation, "MAX_PREPARATION_ACTIONS", 1)
    cold(state, allowed=False)
    assert records(state) == [] and before_import(state) == imported
    assert unchanged_authority(state) == before


def test_failed_durable_startup_write_rolls_back_and_never_imports(
    bootable, monkeypatch
):
    state = bootable
    imported = before_import(state)
    before = unchanged_authority(state)
    original = authority._save

    def fail(db, key, kind, row, value):
        if value["data"].get("operation") == core.OPERATION:
            raise OSError("Startup admission durability unavailable")
        return original(db, key, kind, row, value)

    monkeypatch.setattr(authority, "_save", fail)
    cold(state, allowed=False)
    assert records(state) == [] and before_import(state) == imported
    assert unchanged_authority(state) == before


def test_interrupted_gate_archive_retains_marker_then_fresh_verified_stop_finishes(
    bootable, monkeypatch
):
    state = bootable
    stop = issue_stop(state, state.started)
    original = Path.unlink

    def interrupted(path, *a, **kw):
        if path == state.instance / policy_helper.REQUIRED_NAME:
            raise OSError("Required-marker removal interrupted")
        return original(path, *a, **kw)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", interrupted)
        with pytest.raises(RuntimeError, match="unconfirmed"):
            recover(state, stop)
    assert state.actual_supervisor.process is None
    assert (state.instance / policy_helper.REQUIRED_NAME).is_file()
    assert not (state.instance / policy_helper.POLICY_NAME).exists()
    assert len(list(state.helper_state.glob("relational-boot-archive-*.json"))) == 2
    newer = issue_stop(state, state.started)
    assert recover(state, newer)["outcome"] == "stopped_review_required"
    assert not policy_helper.boot_gate_present(state.instance)
    assert len(list(state.helper_state.glob("relational-boot-archive-*.json"))) == 2


def test_actual_nonroot_core_server_admits_actual_nonroot_host_without_root_fallback(
    bootable,
):
    state = bootable
    # Match installer DAC only in this disposable fixture. Core journal/key
    # writes actually run as UID/GID 1202/1203 with app group 1201, never Root.
    state.server.stop()
    database = Path(state.engine.url.database)
    key_directory = state.keys._directory
    owned = [
        database.parent,
        database,
        *(
            database.with_name(database.name + suffix)
            for suffix in ("-wal", "-shm", "-journal")
            if database.with_name(database.name + suffix).exists()
        ),
        key_directory,
        *key_directory.iterdir(),
        state.platform,
    ]
    owners = {path: (path.stat().st_uid, path.stat().st_gid) for path in owned}
    child = None
    try:
        for path in owned:
            os.chown(path, 1202, 1203)
        os.chown(state.platform, 1202, 1201)
        source = Path(__file__).resolve().parents[2]
        environment = {
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(source),
            "PYTHONDONTWRITEBYTECODE": "1",
            "DATABASE_URL": str(state.engine.url),
            "UPLOADS_DIR": str(state.root),
            "THREE_MM_AUTHORITY_REVIEW_KEY_DIR": str(key_directory),
            "THREE_MM_APPLICATION_ROOT": str(state.runtime),
            "THREE_MM_APPLICATION_KEY_ROOT": str(state.transport_keys),
            "AI_SETTINGS_MASTER_KEY": os.environ["AI_SETTINGS_MASTER_KEY"],
        }
        launch = (
            "import os,sys,time;sys.path.insert(0," + repr(str(source)) + ");"
            "assert os.geteuid()==1202 and os.getegid()==1203;"
            'import threading;exec("def startup_trace(frame,event,arg):\\n'
            " if event=='exception' and frame.f_code.co_filename.endswith('application_relational_startup.py'):\\n"
            "  sys.stderr.write('startup:'+str(frame.f_lineno)+':'+arg[0].__name__+'\\\\n')\\n"
            ' return startup_trace\\n");threading.settrace(startup_trace);'
            "from pathlib import Path;from backend.services.application_platform import ApplicationPlatformServer;"
            "server=ApplicationPlatformServer(Path("
            + repr(str(state.server.socket_path))
            + "),Path("
            + repr(str(state.transport_keys))
            + "),group='fixture-no-system-group');"
            "server.start();os.chown(server.socket_path,-1,1201);time.sleep(120)"
        )
        child = subprocess.Popen(
            [state.actual_supervisor.process.args[0], "-I", "-c", launch],
            user=1202,
            group=1203,
            extra_groups=[1201],
            cwd=database.parent,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        deadline = time.monotonic() + 10
        while not state.server.socket_path.is_socket():
            if child.poll() is not None:
                raise AssertionError(child.communicate(timeout=2)[1].decode())
            assert time.monotonic() < deadline
            time.sleep(0.05)
        # Wait for the owner-process's group publication, not just bind.
        while state.server.socket_path.stat().st_gid != 1201:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        try:
            pid = cold(state, allowed=True)
        except AssertionError as error:
            child.terminate()
            diagnostic = child.communicate(timeout=5)[1].decode()
            raise AssertionError(
                "Non-root Core startup diagnostic: " + diagnostic
            ) from error
        assert (state.data / "service-imported").read_text() == str(pid)
    finally:
        if child is not None:
            child.terminate()
            child.communicate(timeout=5)
        for path, (uid, gid) in owners.items():
            os.chown(path, uid, gid)
    admitted = records(state)
    assert len(admitted) == 1 and admitted[0]["data"]["permit"]["process_pid"] == pid
