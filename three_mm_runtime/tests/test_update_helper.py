from datetime import UTC, datetime
from pathlib import Path
import os
import sqlite3
from contextlib import nullcontext
from functools import partial
from types import SimpleNamespace

import pytest

from backend.services.backups import BackupPreviewResponse
from backend.services.update_staging import StagedUpdate
from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    FileProvisioningStore,
    NetworkCredentials,
    ProvisioningRequest,
    ProvisioningSnapshot,
)
from three_mm_runtime import update_helper
from three_mm_runtime.update_helper import UpdateMutationBoundary


@pytest.mark.skipif(os.name != "posix", reason="Unix helper listener")
def test_host_networking_does_not_block_update_listener_without_network_manager(tmp_path, monkeypatch):
    import grp
    from types import SimpleNamespace

    class ProbeComplete(Exception):
        pass

    class Listener:
        failures = iter((update_helper.socket.timeout(), ProbeComplete()))
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def bind(self, path):
            Path(path).write_bytes(b"listener probe")
        def listen(self, *args):
            pass
        def settimeout(self, *args):
            pass
        def accept(self):
            raise next(self.failures)

    monkeypatch.setenv("THREE_MM_NETWORK_BACKEND", "host")
    monkeypatch.setattr(grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=os.getgid()))
    monkeypatch.setattr(update_helper.os, "chown", lambda *args: None)
    monkeypatch.setattr(update_helper.socket, "socket", lambda *args: Listener())
    monkeypatch.setattr(update_helper.NetworkManagerReadOnlyAdapter, "from_system",
                        lambda: pytest.fail("Host networking must not probe NetworkManager"))
    with pytest.raises(ProbeComplete):
        update_helper.serve(tmp_path / "helper.sock", stage_root=tmp_path / "stage",
            state_root=tmp_path / "state", allowlist=tmp_path / "allowlist.json",
            repository="ldobranov/3mm", manifest_asset_name="3mm-release-manifest.json")
    assert (tmp_path / "helper.sock").exists()


def staged_update() -> StagedUpdate:
    return StagedUpdate(
        release_id="v1.2.0",
        version="1.2.0",
        commit="b" * 40,
        architecture="aarch64",
        artifact_filename="3mm-1.2.0-aarch64.tar.gz",
        artifact_sha256="c" * 64,
        artifact_size_bytes=1234,
        dependencies=["python3"],
        frontend_origin="http://192.168.1.88:8080",
        staged_at=datetime.now(UTC),
        approval_expires_at=datetime.now(UTC),
        approval_nonce="d" * 64,
        preflight=[],
    )


def test_helper_rejects_commands_paths_and_packages_from_the_request(
    tmp_path: Path,
) -> None:
    response = update_helper._handle_request(
        {
            "action": "apply",
            "release_id": "v1.2.0",
            "approval_nonce": "d" * 64,
            "requested_by_user_id": 7,
            "command": "apt install anything",
        },
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
    )

    assert response == {"ok": False, "error": "invalid_request"}


def test_scheduler_diagnostics_are_not_discarded(monkeypatch, caplog):
    from types import SimpleNamespace

    def run(arguments, **kwargs):
        assert "stdout" not in kwargs and "stderr" not in kwargs
        assert kwargs["timeout"] == 30
        return SimpleNamespace(returncode=5)

    monkeypatch.setattr(update_helper.subprocess, "run", run)
    assert (
        update_helper.SubprocessUpdateCommandRunner().run(("/usr/bin/systemd-run",))
        == 5
    )
    assert "exited with code 5" in caplog.text


def test_helper_revalidates_stage_and_schedules_fixed_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = staged_update()
    calls: list[dict[str, object]] = []
    statuses = []

    class FakeBoundary:
        def schedule(self, **arguments) -> None:
            calls.append(arguments)

    monkeypatch.setattr(
        update_helper,
        "validate_staged_payload",
        lambda *_args, **_kwargs: staged,
    )
    monkeypatch.setattr(
        update_helper,
        "write_operation_status",
        lambda _path, value, **_kwargs: statuses.append(value),
    )
    monkeypatch.setattr(update_helper, "_service_ids", lambda *_names: (1000, 1000))

    response = update_helper._handle_request(
        {
            "action": "apply",
            "release_id": staged.release_id,
            "approval_nonce": staged.approval_nonce,
            "requested_by_user_id": 7,
        },
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
        boundary=FakeBoundary(),
    )

    assert response == {"ok": True, "status": "queued"}
    assert statuses[0].state == "queued"
    assert calls == [
        {
            "stage_root": tmp_path / "stage",
            "state_root": tmp_path / "state",
            "allowlist": tmp_path / "allowlist.json",
            "release_id": staged.release_id,
            "approval_nonce": staged.approval_nonce,
            "requested_by_user_id": 7,
        }
    ]


def test_mutation_boundary_uses_no_shell_and_only_the_fixed_worker() -> None:
    calls: list[tuple[str, ...]] = []

    class FakeRunner:
        def run(self, arguments) -> int:
            calls.append(tuple(arguments))
            return 0

    boundary = UpdateMutationBoundary(runner=FakeRunner())
    boundary.schedule(
        stage_root=Path("/var/lib/3mm/core/update-staging"),
        state_root=Path("/var/lib/3mm/update-helper"),
        allowlist=Path("/opt/3mm/current/deployment/update-dependency-allowlist.json"),
        release_id="v1.2.0",
        approval_nonce="d" * 64,
        requested_by_user_id=7,
    )

    command = calls[0]
    assert command[0] == "/usr/bin/systemd-run"
    assert "/bin/sh" not in command
    assert "/bin/bash" not in command
    assert command.count("/opt/3mm/current/deployment/apply_staged_update.py") == 1
    assert command[-4:] == (
        "--repository",
        "ldobranov/3mm",
        "--manifest-asset",
        "3mm-update-manifest.json",
    )
    assert "apt-get" not in " ".join(command)


def test_manual_network_setup_accepts_only_a_fixed_admin_request(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "provisioning"
    FileProvisioningStore(data_dir).save(
        ProvisioningSnapshot.provisioned(
            ProvisioningRequest(
                network=NetworkCredentials("network", "not-persisted"),
                locale="en-GB",
                device_name="device",
                administrator_name="admin",
                role=AgentRole.STANDALONE,
            )
        )
    )
    calls = []

    class FakeBoundary:
        def schedule_network_setup(self, trigger, **values):
            calls.append((trigger, values))

    response = update_helper._handle_request(
        {"action": "start_network_setup", "requested_by_user_id": 7},
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
        boundary=FakeBoundary(),
        provisioning_data_dir=data_dir,
    )
    injected = update_helper._handle_request(
        {
            "action": "start_network_setup",
            "requested_by_user_id": 7,
            "command": "nmcli connection delete anything",
        },
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
        boundary=FakeBoundary(),
        provisioning_data_dir=data_dir,
    )

    assert response == {"ok": True, "status": "queued"}
    assert calls == [
        (
            "manual",
            {
                "data_dir": data_dir,
                "service_user": "3mm",
                "service_group": "3mm",
            },
        )
    ]
    assert injected == {"ok": False, "error": "invalid_request"}


def test_network_setup_boundary_uses_only_the_fixed_module() -> None:
    calls: list[tuple[str, ...]] = []

    class FakeRunner:
        def run(self, arguments) -> int:
            calls.append(tuple(arguments))
            return 0

    boundary = UpdateMutationBoundary(runner=FakeRunner())
    boundary.schedule_network_setup("automatic")

    command = calls[0]
    assert command[0] == "/usr/bin/systemd-run"
    assert "/bin/sh" not in command
    assert "/bin/bash" not in command
    assert "three_mm_runtime.network_recovery" in command
    assert "--property=ProtectSystem=strict" in command
    assert "--property=ReadWritePaths=/var/lib/3mm/provisioning" in command
    assert "--property=ReadWritePaths=/run/lock" in command
    assert command[-7:] == (
        "/var/lib/3mm/provisioning",
        "--trigger",
        "automatic",
        "--user",
        "3mm",
        "--group",
        "3mm",
    )


def test_system_actions_accept_only_fixed_requests_and_workers(tmp_path: Path) -> None:
    scheduled: list[str] = []

    class FakeBoundary:
        def schedule_system_action(self, action: str) -> None:
            scheduled.append(action)

    common = {
        "stage_root": tmp_path / "stage",
        "state_root": tmp_path / "state",
        "allowlist": tmp_path / "allowlist.json",
        "status_file": tmp_path / "status.json",
        "boundary": FakeBoundary(),
    }
    restarted = update_helper._handle_request(
        {"action": "restart_device", "requested_by_user_id": 7},
        **common,
    )
    reset = update_helper._handle_request(
        {"action": "factory_reset", "requested_by_user_id": 7},
        **common,
    )
    injected = update_helper._handle_request(
        {
            "action": "factory_reset",
            "requested_by_user_id": 7,
            "path": "/var/lib/anything",
        },
        **common,
    )

    assert restarted == {"ok": True, "status": "queued"}
    assert reset == {"ok": True, "status": "queued"}
    assert injected == {"ok": False, "error": "invalid_request"}
    assert scheduled == ["restart_device", "factory_reset"]


def test_system_action_boundary_uses_fixed_commands() -> None:
    calls: list[tuple[str, ...]] = []

    class FakeRunner:
        def run(self, arguments) -> int:
            calls.append(tuple(arguments))
            return 0

    boundary = UpdateMutationBoundary(runner=FakeRunner())
    boundary.schedule_system_action("restart_device")
    boundary.schedule_system_action("factory_reset")

    restart, reset = calls
    assert restart[-2:] == ("/usr/bin/systemctl", "reboot")
    assert "/bin/sh" not in restart and "/bin/bash" not in restart
    assert reset[-1] == "/opt/3mm/current/deployment/factory_reset.py"
    assert "--property=ProtectSystem=strict" in reset
    assert "--property=ReadWritePaths=/var/lib/3mm" in reset
    assert "--property=ReadWritePaths=/etc/3mm" in reset
    assert "/bin/sh" not in reset and "/bin/bash" not in reset


def test_backup_request_schedules_only_the_fixed_encrypted_worker(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, ...]] = []

    class FakeRunner:
        def run(self, arguments) -> int:
            calls.append(tuple(arguments))
            return 0

    boundary = UpdateMutationBoundary(runner=FakeRunner())
    response = update_helper._handle_request(
        {"action": "create_backup", "requested_by_user_id": 7},
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
        boundary=boundary,
        backup_root=Path("/var/lib/3mm/backups"),
    )

    assert response == {"ok": True, "status": "queued"}
    command = calls[0]
    assert command[0] == "/usr/bin/systemd-run"
    assert "/bin/sh" not in command and "/bin/bash" not in command
    assert "/opt/3mm/current/deployment/create_backup.py" in command
    assert "--property=ReadWritePaths=/var/lib/3mm/backups" in command
    assert command[-2:] == ("--requested-by-user-id", "7")


def test_backup_preview_reads_protected_state_inside_the_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = object()
    preview = BackupPreviewResponse(
        ready=True,
        manifest=None,
        entry_count=7,
        estimated_backup_bytes=1234,
        available_bytes=5678,
        minimum_free_after_backup_bytes=64,
        required_available_bytes=1298,
        sufficient_space=True,
        storage_path="/var/lib/3mm/backups",
        issues=(),
    )
    captured = []
    monkeypatch.setattr(update_helper, "production_settings", lambda _root: settings)
    monkeypatch.setattr(
        update_helper,
        "build_backup_preview",
        lambda selected: captured.append(selected) or preview,
    )

    response = update_helper._handle_request(
        {"action": "preview_backup", "requested_by_user_id": 7},
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
        backup_root=tmp_path / "backups",
    )

    assert response["status"] == "inspected"
    assert response["preview"]["ready"] is True
    assert response["preview"]["entry_count"] == 7
    assert captured == [settings]


def test_restore_request_rejects_paths_and_schedules_fixed_worker(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, ...]] = []

    class FakeRunner:
        def run(self, arguments) -> int:
            calls.append(tuple(arguments))
            return 0

    boundary = UpdateMutationBoundary(runner=FakeRunner())
    common = {
        "stage_root": tmp_path / "stage",
        "state_root": tmp_path / "state",
        "allowlist": tmp_path / "allowlist.json",
        "status_file": tmp_path / "status.json",
        "boundary": boundary,
    }
    backup_id = "bkp_20260828T120000Z_0123abcd"
    accepted = update_helper._handle_request(
        {
            "action": "restore_backup",
            "backup_id": backup_id,
            "requested_by_user_id": 7,
        },
        **common,
    )
    rejected = update_helper._handle_request(
        {
            "action": "restore_backup",
            "backup_id": "../../etc/passwd",
            "requested_by_user_id": 7,
        },
        **common,
    )

    assert accepted == {"ok": True, "status": "queued"}
    assert rejected == {"ok": False, "error": "invalid_request"}
    command = calls[0]
    assert "/opt/3mm/current/deployment/restore_backup.py" in command
    assert command[-4:] == ("--backup-id", backup_id, "--requested-by-user-id", "7")


def test_portable_export_keeps_password_inside_the_helper_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    backup_id = "bkp_20260828T120000Z_0123abcd"
    captured = []
    monkeypatch.setattr(update_helper, "_service_ids", lambda *_args: (1000, 1000))
    monkeypatch.setattr(
        update_helper,
        "create_portable_export",
        lambda root, key, selected, password, owner: captured.append(
            (root, key, selected, password, owner)
        )
        or type(
            "Export",
            (),
            {
                "export_id": "a" * 32,
                "backup_id": selected,
                "filename": f"{selected}.3mmrecovery",
            },
        )(),
    )

    response = update_helper._handle_request(
        {
            "action": "export_backup",
            "backup_id": backup_id,
            "passphrase": "recovery-password",
            "requested_by_user_id": 7,
        },
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
        backup_root=tmp_path / "backups",
    )

    assert response["status"] == "ready"
    assert response["export_id"] == "a" * 32
    assert captured[0][3] == "recovery-password"


def test_portable_restore_uses_only_the_fixed_upload_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    backup_id = "bkp_20260828T120000Z_0123abcd"
    scheduled = []
    imported = []

    class Boundary:
        def schedule_restore(self, **kwargs) -> None:
            scheduled.append(kwargs)

    monkeypatch.setattr(update_helper, "_service_ids", lambda *_args: (1000, 1000))
    monkeypatch.setattr(
        update_helper,
        "import_portable_backup",
        lambda upload, root, key, password, **kwargs: imported.append(
            (upload, root, key, password, kwargs)
        )
        or backup_id,
    )
    backup_root = tmp_path / "backups"
    response = update_helper._handle_request(
        {
            "action": "restore_portable_backup",
            "upload_id": "b" * 32,
            "passphrase": "recovery-password",
            "requested_by_user_id": 7,
        },
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
        boundary=Boundary(),
        backup_root=backup_root,
    )
    rejected = update_helper._handle_request(
        {
            "action": "restore_portable_backup",
            "upload_id": "../../etc/passwd",
            "passphrase": "recovery-password",
            "requested_by_user_id": 7,
        },
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
        boundary=Boundary(),
        backup_root=backup_root,
    )

    assert response == {"ok": True, "status": "queued", "backup_id": backup_id}
    assert rejected == {"ok": False, "error": "invalid_request"}
    assert imported[0][0] == tmp_path / "core/backup-imports" / (
        f"{'b' * 32}.3mmrecovery"
    )
    assert scheduled[0]["backup_id"] == backup_id


def test_application_activation_uses_only_the_fixed_sha_package_path(
    monkeypatch, tmp_path: Path
) -> None:
    captured = []
    from contextlib import nullcontext
    monkeypatch.setattr(update_helper, "application_lifecycle_operation", lambda *_a, **_kw: nullcontext())
    sha256 = "a" * 64
    monkeypatch.setattr(update_helper, "_service_ids", lambda *_args: (1200, 1201))
    monkeypatch.setattr(
        update_helper,
        "activate_application_package",
        lambda package_path, expected, **kwargs: captured.append(
            (package_path, expected, kwargs)
        )
        or type(
            "Activated",
            (),
            {
                "module_id": "org.3mm.demo",
                "version": "1.0.0",
                "sha256": expected,
                "instance_id": "b" * 24,
                "socket_path": tmp_path / "apps" / ("b" * 24) / "run/service.sock",
            },
        )(),
    )

    response = update_helper._handle_request(
        {
            "action": "activate_application_extension",
            "sha256": sha256,
            "requested_by_user_id": 7,
            "lifecycle": {},  # Ticket validation is covered by test_application_lifecycle.
        },
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
        application_upload_root=tmp_path / "uploads",
        application_root=tmp_path / "apps",
        application_key_root=tmp_path / "keys",
    )
    injected = update_helper._handle_request(
        {
            "action": "activate_application_extension",
            "sha256": sha256,
            "requested_by_user_id": 7,
            "package_path": "/tmp/anything.zip",
        },
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
    )

    assert response["status"] == "active"
    assert captured[0][0] == tmp_path / "uploads" / f"{sha256}.zip"
    assert captured[0][1] == sha256
    assert captured[0][2]["service_uid"] == 1200
    assert captured[0][2]["service_gid"] == 1201
    assert injected == {"ok": False, "error": "invalid_request"}


def test_application_uninstall_uses_fixed_runtime_roots(tmp_path: Path, monkeypatch) -> None:
    calls = []
    from contextlib import nullcontext
    monkeypatch.setattr(update_helper, "application_lifecycle_operation", lambda *_a, **_kw: nullcontext())

    class Boundary:
        def uninstall_application_extension(self, instance_id, **kwargs):
            calls.append((instance_id, kwargs))

    response = update_helper._handle_request(
        {
            "action": "uninstall_application_extension",
            "instance_id": "b" * 24,
            "requested_by_user_id": 7,
            "lifecycle": {},
        },
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
        boundary=Boundary(),
        application_root=tmp_path / "apps",
        application_key_root=tmp_path / "keys",
    )

    assert response == {"ok": True, "status": "uninstalled"}
    assert calls == [
        (
            "b" * 24,
            {"root": tmp_path / "apps", "key_root": tmp_path / "keys"},
        )
    ]


def test_application_data_erase_uses_only_the_fixed_instance_root(
    tmp_path: Path, monkeypatch,
) -> None:
    calls = []
    monkeypatch.setattr(update_helper, "_retained_data_erase_operation", lambda *_a, **_kw: nullcontext())

    class Boundary:
        def erase_application_extension_data(self, instance_id, **kwargs):
            calls.append((instance_id, kwargs))

    response = update_helper._handle_request(
        {
            "action": "erase_application_extension_data",
            "instance_id": "c" * 24,
            "module_id": "org.example.retained", "guard_generation": "f" * 32, "guard_revision": 1,
            "requested_by_user_id": 7,
        },
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist.json",
        status_file=tmp_path / "status.json",
        boundary=Boundary(),
        application_root=tmp_path / "apps",
    )

    assert response == {"ok": True, "status": "erased"}
    assert calls == [("c" * 24, {"root": tmp_path / "apps"})]


def test_access_point_rpc_is_bounded_and_uses_fixed_worker(tmp_path, monkeypatch):
    calls=[]
    class Boundary:
        def schedule_access_point(self,*args,**kwargs):calls.append((args,kwargs))
    values=dict(stage_root=tmp_path/'stage',state_root=tmp_path/'state',allowlist=tmp_path/'allow',status_file=tmp_path/'status',boundary=Boundary())
    payload={'action':'start_access_point','requested_by_user_id':7,'id':'a'*32,'interface':'wifi0','duration':300}
    assert update_helper._handle_request(payload,**values)=={'ok':True,'status':'queued'}
    assert calls==[(('start','a'*32),{'interface':'wifi0','duration':300})]
    for bad in [{**payload,'command':'reboot'},{**payload,'interface':'wifi0;reboot'},{**payload,'duration':True},{**payload,'id':'../other'},{**payload,'requested_by_user_id':True}]:
        assert update_helper._handle_request(bad,**values)=={'ok':False,'error':'invalid_request'}
    assert len(calls)==1


def test_access_point_scheduler_cancels_only_the_matching_start_request(monkeypatch):
    import three_mm_provisioning.recovery_access_point as ap
    commands=[]
    class Runner:
        def run(self,args):commands.append(tuple(args));return 0
    monkeypatch.setattr(ap,'read_status',lambda:{'id':'a'*32,'state':'starting'})
    monkeypatch.setattr(ap,'publish_status',lambda _status:None)
    boundary=update_helper.UpdateMutationBoundary(runner=Runner())
    boundary.schedule_access_point('stop','a'*32)
    assert commands[0]==('/usr/bin/systemctl','stop','3mm-access-point-start-'+('a'*32)+'.timer','3mm-access-point-start-'+('a'*32)+'.service')
    assert 'three_mm_provisioning.recovery_access_point' in commands[1]
    assert commands[1][-3:]==('stop','--id','a'*32)
    assert '--on-active=3s' in commands[1]

    commands.clear()
    monkeypatch.setattr(ap, 'read_status', lambda: {'id': 'b' * 32, 'state': 'starting'})
    boundary.schedule_access_point('stop', 'a' * 32)
    assert len(commands) == 1 and commands[0][0] == '/usr/bin/systemd-run'
    commands.clear()
    monkeypatch.setattr(ap, 'read_status', lambda: {'id': 'a' * 32, 'state': 'active'})
    boundary.schedule_access_point('stop', 'a' * 32)
    assert len(commands) == 1 and commands[0][0] == '/usr/bin/systemd-run'


@pytest.fixture
def retained_erase(tmp_path, monkeypatch):
    from three_mm_runtime import application_lifecycle as fencing
    database = tmp_path / "retained-core.db"
    state = tmp_path / "helper-state"
    state.mkdir(mode=0o700)
    payload = dict(action="erase_application_extension_data", instance_id="c" * 24,
                   module_id="org.example.retained", requested_by_user_id=7,
                   guard_generation="f" * 32, guard_revision=1)
    with sqlite3.connect(database) as db:
        db.executescript("""
            CREATE TABLE core_authority_guard(singleton_id INTEGER PRIMARY KEY, generation TEXT, revision INTEGER);
            CREATE TABLE application_retained_data(module_id TEXT, instance_id TEXT);
            CREATE TABLE application_extension_installations(module_id TEXT, instance_id TEXT);
        """)
        db.execute("INSERT INTO core_authority_guard VALUES (1, ?, 1)", (payload["guard_generation"],))
        db.execute("INSERT INTO application_retained_data VALUES (?, ?)", (payload["module_id"], payload["instance_id"]))
    monkeypatch.setattr(fencing, "RELEASE_MUTATION_LOCK", tmp_path / "release-mutation.lock")
    if os.name != "posix":
        # Only native flock is substituted, never the fresh read-only DB checks.
        monkeypatch.setattr(fencing, "_release_lock", lambda **_kw: nullcontext())
        monkeypatch.setattr(fencing, "_runtime_lock", lambda *_a, **_kw: nullcontext())
    operation = partial(update_helper._retained_data_erase_operation,
                        database=database, state_root=state, enforce_permissions=False)
    monkeypatch.setattr(update_helper, "_retained_data_erase_operation", lambda value, **_kw: operation(value))
    calls = []
    class Boundary:
        def erase_application_extension_data(self, instance_id, **kwargs):
            calls.append((instance_id, kwargs))
    values = dict(stage_root=tmp_path / "stage", state_root=state,
                  allowlist=tmp_path / "allowlist", status_file=tmp_path / "status",
                  application_database=database, application_root=tmp_path / "apps", boundary=Boundary())
    return SimpleNamespace(database=database, state=state, payload=payload, calls=calls,
                           values=values, operation=operation, fencing=fencing)


def test_erase_helper_requires_exact_fresh_retained_mapping(retained_erase):
    s = retained_erase
    result = update_helper._handle_request(s.payload, **s.values)
    assert result == {"ok": True, "status": "erased"}
    assert s.calls == [(s.payload["instance_id"], {"root": s.values["application_root"]})]
    with sqlite3.connect(s.database) as db:
        # Helper does not create/delete/alter Core ownership; the holding API does.
        assert db.execute("SELECT * FROM application_retained_data").fetchall() == [(s.payload["module_id"], s.payload["instance_id"])]


@pytest.mark.parametrize("change", ["missing", "wrong_instance", "wrong_module", "ambiguous"])
def test_erase_helper_refuses_missing_mismatched_or_ambiguous_retained_record(retained_erase, change):
    s = retained_erase
    with sqlite3.connect(s.database) as db:
        if change == "missing":
            db.execute("DELETE FROM application_retained_data")
        elif change == "wrong_instance":
            db.execute("UPDATE application_retained_data SET instance_id=?", ("d" * 24,))
        elif change == "wrong_module":
            db.execute("UPDATE application_retained_data SET module_id='org.example.other'")
        else:
            db.execute("INSERT INTO application_retained_data VALUES (?, ?)", ("org.example.other", s.payload["instance_id"]))
    assert update_helper._handle_request(s.payload, **s.values) == {"ok": False, "error": "application_data_erase_failed"}
    assert not s.calls


@pytest.mark.parametrize("matching", ["module", "instance", "both"])
def test_erase_helper_refuses_any_fresh_installation_owner(retained_erase, matching):
    s = retained_erase
    module = s.payload["module_id"] if matching in {"module", "both"} else "org.example.other"
    instance = s.payload["instance_id"] if matching in {"instance", "both"} else "d" * 24
    with sqlite3.connect(s.database) as db:
        db.execute("INSERT INTO application_extension_installations VALUES (?, ?)", (module, instance))
    assert update_helper._handle_request(s.payload, **s.values)["error"] == "application_data_erase_failed"
    assert not s.calls


@pytest.mark.parametrize("change", ["missing_guard", "generation", "revision"])
def test_queued_erase_cannot_cross_fresh_guard_generation_or_revision(retained_erase, change):
    s = retained_erase
    with sqlite3.connect(s.database) as db:
        if change == "missing_guard":
            db.execute("DELETE FROM core_authority_guard")
        elif change == "generation":
            db.execute("UPDATE core_authority_guard SET generation=?", ("e" * 32,))
        else:
            # A later install/uninstall can retain the same runtime locator.
            # Its advanced committed guard must still reject this old request.
            db.execute("UPDATE core_authority_guard SET revision=2")
    assert update_helper._handle_request(s.payload, **s.values)["error"] == "application_data_erase_failed"
    assert not s.calls
    if change == "revision":
        assert update_helper._handle_request(dict(s.payload, guard_revision=2), **s.values)["status"] == "erased"


def test_erase_helper_does_not_create_missing_core_database(retained_erase):
    s = retained_erase
    missing = s.database.with_name("missing.db")
    # Recreate the real scope with a missing fixed read-only DB path.
    original = s.operation.func
    with pytest.raises(s.fencing.ApplicationLifecycleError):
        with original(s.payload, database=missing, state_root=s.state, enforce_permissions=False):
            pytest.fail("missing DB authorized erasure")
    assert not missing.exists() and not s.calls


@pytest.mark.parametrize("field,value", [("guard_revision", True), ("guard_revision", 0),
    ("guard_revision", 2**53), ("guard_generation", "invalid"), ("instance_id", "../data"),
    ("module_id", ""), ("requested_by_user_id", True)])
def test_erase_helper_rejects_invalid_context_before_effect(retained_erase, field, value):
    s = retained_erase
    assert update_helper._handle_request(dict(s.payload, **{field: value}), **s.values) == {"ok": False, "error": "invalid_request"}
    assert not s.calls


def test_erase_helper_rejects_legacy_unfenced_request(retained_erase):
    s = retained_erase
    request = {k: s.payload[k] for k in ("action", "instance_id", "requested_by_user_id")}
    assert update_helper._handle_request(request, **s.values) == {"ok": False, "error": "invalid_request"}
    assert not s.calls


@pytest.mark.skipif(os.name != "posix", reason="Native serialization locks")
@pytest.mark.parametrize("held", ["release", "runtime"])
def test_erase_helper_cannot_overlap_held_native_lifecycle_lock(retained_erase, held):
    s = retained_erase
    scope = s.fencing._release_lock(enforce_permissions=False) if held == "release" else s.fencing._runtime_lock(s.state, enforce_permissions=False)
    with scope:
        assert update_helper._handle_request(s.payload, **s.values)["error"] == "application_data_erase_failed"
    assert not s.calls


@pytest.mark.skipif(os.name != "posix", reason="Native activation/erase serialization")
def test_erase_scope_excludes_delayed_activation_before_its_database_read(retained_erase):
    s = retained_erase
    activation = dict(action="activate_application_extension", sha256="a" * 64,
        requested_by_user_id=7, configuration={}, lifecycle=dict(installation_id=1,
            module_id=s.payload["module_id"], instance_id=s.payload["instance_id"],
            incarnation="c" * 32, epoch="d" * 32, guard_generation=s.payload["guard_generation"]))
    with s.operation(s.payload):
        with pytest.raises(s.fencing.ApplicationLifecycleError):
            with s.fencing.application_lifecycle_operation(activation, database=s.database,
                    state_root=s.state, enforce_permissions=False):
                pytest.fail("activation crossed erasure")


def test_erase_reads_committed_revision_while_core_writer_prevents_new_install(retained_erase):
    s = retained_erase
    class Boundary:
        def erase_application_extension_data(self, *_args, **_kwargs):
            # The helper's RO snapshot is already closed. The API writer, not a
            # helper-held read transaction, excludes this concurrent activation.
            with sqlite3.connect(s.database, timeout=0.01) as other:
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    other.execute("INSERT INTO application_extension_installations VALUES (?, ?)",
                                  (s.payload["module_id"], s.payload["instance_id"]))
            s.calls.append("erased")
    with sqlite3.connect(s.database) as writer:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE core_authority_guard SET revision=2")  # Not committed until helper ACK.
        result = update_helper._handle_request(s.payload, **dict(s.values, boundary=Boundary()))
        assert result == {"ok": True, "status": "erased"}
    assert s.calls == ["erased"]


def test_erase_helper_never_acknowledges_runtime_deletion_failure(retained_erase):
    s = retained_erase
    class Boundary:
        def erase_application_extension_data(self, *_args, **_kwargs):
            raise PermissionError("do-not-ack")
    assert update_helper._handle_request(s.payload, **dict(s.values, boundary=Boundary())) == {"ok": False, "error": "application_data_erase_failed"}


def test_erase_client_binds_retained_mapping_and_committed_guard(monkeypatch, tmp_path):
    from three_mm_runtime.update_helper_client import UpdateHelperClient
    calls = []
    monkeypatch.setattr(UpdateHelperClient, "_request", lambda self, payload, **kwargs: calls.append((payload, kwargs)))
    UpdateHelperClient(tmp_path / "helper.sock").erase_application_extension_data(
        "c" * 24, 7, module_id="org.example.retained", guard_generation="f" * 32, guard_revision=4)
    assert calls == [(dict(action="erase_application_extension_data", instance_id="c" * 24,
        requested_by_user_id=7, module_id="org.example.retained", guard_generation="f" * 32,
        guard_revision=4), {"expected_status": "erased"})]
