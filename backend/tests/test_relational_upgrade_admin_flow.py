"""Real local CLI -> Unix peer -> Root helper -> separate Core-UID workers.

Disposable files/processes only. Unit supervision doubled; no live systemd.
"""

import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from backend.tests import test_application_relational_upgrade_restore as restore_cases
from backend.tests.test_application_relational_preparation import (
    ROOT_ONLY,
    action,
    identity,
    managed_installed,
    prepared_paths,
    source_installed,
    source_subject,
    stopped,
)
from three_mm_runtime import application_relational_control as installed_control
from three_mm_runtime import update_helper
from three_mm_runtime.application_relational_control import CoreMetadataClient

pytestmark = [
    ROOT_ONLY,
    pytest.mark.skipif(os.name != "posix", reason="Real process principals"),
]
upgradable = restore_cases.upgradable


@pytest.mark.parametrize("kind", ["upgrade", "published", "rollback", "restore"])
def test_actual_admin_flow(upgradable, monkeypatch, tmp_path, kind):
    state = upgradable
    if kind == "restore":
        restore_cases.partial(state, monkeypatch)
    elif kind == "published":
        state.failed = restore_cases.rollback_cases.upgrade_issue(state)

        def lost(*a, **kw):
            if a[1] == "finish":
                raise OSError("Lost completion before Core")
            return restore_cases.rollback_cases.upgrade_checkpoint(state, *a, **kw)

        with pytest.raises(RuntimeError):
            restore_cases.rollback_cases.upgrade(state, state.failed, lost)
    elif kind == "rollback":
        state = restore_cases.rollback_cases.restored.__wrapped__(state, monkeypatch)
    source = state.source if kind == "upgrade" else state.failed
    source_id = source["preparation_id"]
    expected_revision = action(state, source)["revision"]
    expected_grant = state.manager.inspect(1)["grant_record_revision"]
    core_db = Path(state.engine.url.database)
    state.engine.dispose()
    # Changing ownership ONLY on this per-test Core database/key namespace.
    os.chown(tmp_path, 1202, 1203)
    tmp_path.chmod(0o755)
    for parent in (tmp_path.parent, tmp_path.parent.parent):
        parent.chmod(0o755)
    for path in (
        core_db,
        core_db.with_name(core_db.name + "-wal"),
        core_db.with_name(core_db.name + "-shm"),
    ):
        if path.exists():
            os.chown(path, 1202, 1203)
    os.chown(state.key_directory, 1202, 1203)
    for path in state.key_directory.iterdir():
        os.chown(path, 1202, 1203)
    sock = tmp_path / "local-helper.sock"
    environment = dict(
        os.environ,
        DATABASE_URL=f"sqlite:///{core_db}",
        UPLOADS_DIR=str(state.root),
        THREE_MM_AUTHORITY_REVIEW_KEY_DIR=str(state.key_directory),
        THREE_MM_APPLICATION_ROOT=str(state.runtime),
        THREE_MM_UPDATE_HELPER_SOCKET=str(sock),
        PYTHONDONTWRITEBYTECODE="1",
    )
    # Config's application helper socket has its own explicit setting.
    environment["THREE_MM_APPLICATION_HELPER_SOCKET"] = str(sock)
    frames = []

    def runner(arguments, **kw):
        frame = json.loads(kw["input"])
        frames.append(frame["action"])
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.services.application_relational_admin_worker",
                "--core-uid",
                "1202",
                "--database",
                str(core_db),
                "--application-root",
                str(state.runtime),
            ],
            user=1202,
            group=1203,
            extra_groups=(),
            env=environment,
            **kw,
        )

    metadata = CoreMetadataClient(core_uid=1202, database=core_db, runner=runner)
    from three_mm_runtime import (
        application_relational_upgrade_control as upgrade_control,
    )

    real_installed = upgrade_control.installed_upgrade
    root_diagnostics = []

    def trace_installed(*a, **kw):
        import traceback

        try:
            return real_installed(*a, **kw)
        except Exception as error:
            root_diagnostics.append(
                (
                    type(error).__name__,
                    [
                        (entry.name, entry.lineno)
                        for entry in traceback.extract_tb(error.__traceback__)
                    ],
                )
            )
            raise

    monkeypatch.setattr(upgrade_control, "installed_upgrade", trace_installed)
    monkeypatch.setattr(installed_control, "CoreMetadataClient", lambda **kw: metadata)
    monkeypatch.setattr(
        update_helper,
        "_service_ids",
        lambda user, group: (1200, 1201) if user == "3mm-app" else (1202, 1203),
    )
    from three_mm_runtime.application_activation import SystemdApplicationSupervisor

    monkeypatch.setattr(
        SystemdApplicationSupervisor,
        "recover_disabled",
        lambda self, identifier: state.calls.append(("stop", identifier)),
    )
    arguments = dict(
        stage_root=tmp_path / "stage",
        state_root=state.helper_state,
        allowlist=tmp_path / "allowlist",
        status_file=tmp_path / "status",
        application_upload_root=state.root / "modules",
        application_root=state.runtime,
        application_key_root=state.transport_keys,
        application_database=core_db,
    )
    request_id = identity()
    command, consent = {
        "upgrade": ("upgrade-relational", "confirm-owned-forward-upgrade"),
        "published": (
            "confirm-relational-upgrade",
            "confirm-published-upgrade-reviewed",
        ),
        "rollback": ("confirm-relational-rollback", "confirm-restored-state-reviewed"),
        "restore": ("finish-relational-restore", "confirm-finish-interrupted-restore"),
    }[kind]

    def cli(*args):
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.services.application_authority_admin",
                *args,
            ],
            input=state.token.encode() + b"\n",
            capture_output=True,
            timeout=90,
            start_new_session=True,
            user=1202,
            group=1203,
            extra_groups=(),
            env=environment,
        )
        assert state.token.encode() not in process.stdout + process.stderr
        assert process.returncode == 0, (
            process.stderr.decode(),
            frames,
            root_diagnostics,
        )
        return json.loads(process.stdout)

    inspected = cli(
        "inspect-relational-upgrade",
        "--installation-id",
        "1",
        "--source-action-id",
        source_id,
    )
    assert inspected["source_revision"] == expected_revision
    errors = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(sock))
        os.chown(sock, 0, 1203)
        sock.chmod(0o660)
        listener.listen(1)
        listener.settimeout(60)

        def serve():
            try:
                connection, _ = listener.accept()
                with connection:
                    update_helper._serve_connection(connection, **arguments)
            except BaseException as error:
                errors.append(repr(error))

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            result = cli(
                command,
                "--installation-id",
                "1",
                "--source-action-id",
                source_id,
                "--expected-source-revision",
                expected_revision,
                "--expected-grant-record-revision",
                expected_grant,
                "--request-id",
                request_id,
                "--" + consent,
            )
        finally:
            thread.join(timeout=65)
        assert not thread.is_alive() and not errors
    assert result["status"] == (
        "upgraded_not_started"
        if kind in {"upgrade", "published"}
        else "restored_not_started"
    ), frames
    assert result["upgrade"]["preparation_id"] == request_id
    assert frames[:2] == ["inspect_upgrade_source", "issue_relational_upgrade"]
    assert frames[2:] and set(frames[2:]) == {"relational_upgrade_checkpoint"}
    confirmed = cli(
        "inspect-relational-upgrade",
        "--installation-id",
        "1",
        "--source-action-id",
        request_id,
    )
    assert confirmed["state"] == ("upgraded" if kind == "upgrade" else "confirmed")
    assert result["permission_approval"] == "not_evaluated"
    with sqlite3.connect(core_db) as db:
        assert db.execute(
            "SELECT enabled,status,authority_mode FROM application_extension_installations WHERE id=1"
        ).fetchone() == (0, "disabled", "review_required")
    restore_cases.rollback_cases.original(state)
    assert all(call[0] == "stop" for call in state.calls)
