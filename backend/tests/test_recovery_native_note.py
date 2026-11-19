"""A new native app process reads its own data after a disposable Linux restore.

The default runs only subprocesses. The opt-in Linux variant also exercises
the application stop/start through disposable user-systemd services. Neither
touches installed system units, real user accounts, grants or hardware. HTTP
access is tested only with a fresh login against the disposable restored DB.
"""
from contextlib import ExitStack
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.artifacts.packages import validate_module_package
from backend.applications.runtime.gateway import load_application_package
from backend.accounts.passwords import hash_password
from backend.db.module import ApplicationExtensionInstallation, ApplicationPermissionGrant, ModulePackage
from backend.db.user import User
from backend.system.backups.service import read_backup_operation_status
from backend.tests.test_application_file_backup import Controller, _restore
from backend.tests.test_application_tasks import native_task_host
from backend.tests.test_backup_preview import _settings
from components.system_runtime.application_activation import activate_application_package
from components.system_runtime.application_transport import ApplicationServiceClient
from deployment import restore_application_extensions as reconstruction
from deployment.create_backup import create_backup
from deployment.portable_backup import create_portable_export, import_portable_backup
from tools.application_project import build_package
from tools.recovery_check import verify_portable


REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Real local Linux application host")


class LocalService:
    """Production host + health client, a private subprocess in place of systemd."""

    def __init__(self, host, root):
        self.host = host
        self.root = root / "application-extensions"
        self.keys = root / "app-keys"
        self.process = None

    def restart(self, instance):
        self.close()
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-S", str(self.host), "--instance", instance,
             "--root", str(self.root), "--key-root", str(self.keys)],
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, cwd=self.root,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def generation(self):
        assert self.process.poll() is None
        return self.process.pid

    def stop(self, _instance):
        self.close()

    def is_enabled(self, _instance):
        return False

    def client(self, instance):
        return ApplicationServiceClient(self.root / instance / "run/service.sock",
                                        (self.keys / (instance + ".key")).read_bytes(), 5)


class LocalUserService(LocalService):
    """Real systemd for the app only. Never select or operate installed OS units."""

    def __init__(self, host, root):
        assert os.geteuid() != 0
        super().__init__(host, root)
        self.unit = self.invocation = None

    def prop(self, name):
        result = subprocess.run(["systemctl", "--user", "show", self.unit, "-p", name, "--value"],
                                capture_output=True, text=True, timeout=10)
        assert result.returncode in (0, 4), result.stderr
        return result.stdout.strip()

    def restart(self, instance):
        self.close()
        self.unit = "note-recovery-test-" + uuid.uuid4().hex + ".service"
        assert self.prop("LoadState") == "not-found"
        subprocess.run(["systemd-run", "--user", "--quiet", "--collect", "--unit=" + self.unit,
                        "--property=Type=exec", "--property=Restart=no", "--property=RuntimeMaxSec=240s",
                        "--property=NoNewPrivileges=yes", "--property=RestrictAddressFamilies=AF_UNIX",
                        "--property=StandardOutput=null", "--property=StandardError=null",
                        "--property=WorkingDirectory=" + str(self.root), "/usr/bin/env", "-i",
                        "PATH=/usr/bin:/bin", "LANG=C.UTF-8", sys.executable, "-I", "-S", str(self.host),
                        "--instance", instance, "--root", str(self.root), "--key-root", str(self.keys)],
                       check=True, timeout=15)
        self.invocation = self.prop("InvocationID")
        assert self.invocation and self.prop("ActiveState") == "active"

    def close(self):
        if self.unit is not None and self.prop("LoadState") != "not-found":
            assert self.invocation and self.prop("InvocationID") == self.invocation
            subprocess.run(["systemctl","--user","stop",self.unit], check=True, timeout=15)
            assert self.prop("ActiveState") == "inactive"
        self.unit = self.invocation = None

    def generation(self):
        assert self.prop("ActiveState") == "active" and int(self.prop("MainPID")) > 1
        assert self.prop("InvocationID") == self.invocation
        return self.invocation


def install_fixture(settings, host, blob, validated, *, reader):
    package = settings.backend.uploads_dir / "modules" / (validated.sha256 + ".zip")
    package.parent.mkdir()
    package.write_bytes(blob)
    active = activate_application_package(package, validated.sha256, root=host.root,
                                          key_root=host.keys, supervisor=host)
    engine = create_engine(settings.backend.database_url)
    try:
        with Session(engine) as db, db.begin():
            row = ModulePackage(module_id=active.module_id, version=active.version,
                                manifest=validated.manifest.model_dump(mode="json"), sha256=validated.sha256,
                                size_bytes=len(blob), file_path=str(package), registrations=[])
            db.add(row)
            db.flush()
            record = ApplicationExtensionInstallation(module_id=active.module_id, module_package_id=row.id,
                instance_id=active.instance_id, enabled=True, status="active", active_version=active.version,
                socket_path=str(active.socket_path), configuration={})
            db.add(record)
            db.flush()
            user = User(username="recovery-operator", email="recovery@example.test", role="user",
                        hashed_password=hash_password("rehearsal-only-login"))
            db.add(user)
            db.flush()
            if reader:
                db.add(ApplicationPermissionGrant(application_installation_id=record.id,
                    user_id=user.id, permission_id="note_read"))
            return active.instance_id, record.authority_epoch
    finally:
        engine.dispose()


def check_operator_access(engine, owner, *, can_read):
    """A fresh normal login and actual Core routes against the restored DB, no grant or dispatch."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.accounts.users_api import router as accounts
    from backend.applications.management.api import router as applications
    from backend.storage.sessions import get_db

    def database():
        with Session(engine) as db:
            yield db
    app = FastAPI()
    app.include_router(accounts, prefix="/api/user")
    app.include_router(applications)
    app.dependency_overrides[get_db] = database
    base = "/api/v1/application-extensions/" + owner
    with TestClient(app) as client:
        assert client.get(base + "/access").status_code == 401
        login = client.post("/api/user/login", json={"email":"recovery@example.test","password":"rehearsal-only-login"})
        assert login.status_code == 200
        headers = {"Authorization":"Bearer " + login.json()["token"]}
        response = client.get(base + "/access",headers=headers)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store", response.status_code
        data = response.json()
        assert data["permission_ids"] == (["note_read"] if can_read else [])
        assert ("note" in data["allowed_route_ids"]) == can_read and not data["platform_administrator"]
        assert client.post(base + "/operator/operations/save_note",headers=headers,json={
            "payload":{"text":"must not be saved","revision":1},"idempotency_key":"6"*32}).status_code == 403
        assert client.post("/api/user/logout",headers=headers).status_code == 200
        assert client.get(base + "/access",headers=headers).status_code in (401,403)


@pytest.mark.parametrize("fail_candidate", [False, True], ids=["fresh-install", "rollback"])
@pytest.mark.parametrize("host_factory", [LocalService, pytest.param(LocalUserService,
    marks=pytest.mark.skipif(os.environ.get("TEST_NATIVE_NOTE_USER_SYSTEMD") != "1",
                             reason="Explicit disposable Linux user-manager rehearsal only"))],
    ids=["subprocess","user-systemd"])
def test_portable_roundtrip_reads_original_note_and_save_receipt_through_new_process(
        native_task_host, monkeypatch, fail_candidate, host_factory):
    # Short, private roots keep AF_UNIX path length independent of checkout/pytest paths.
    with tempfile.TemporaryDirectory(prefix="nr-", dir="/tmp") as work, ExitStack() as cleanup:
        folder = Path(work)
        source, dest = folder/"source", folder/"dest"
        source.mkdir(); dest.mkdir()
        current = _settings(source)
        dest_settings = _settings(dest)
        monkeypatch.setattr("backend.config.get_settings", lambda: current)
        monkeypatch.setattr("logging.config.fileConfig", lambda *args, **kwargs: None)
        monkeypatch.setenv("THREE_MM_PLATFORM_RUNTIME_SOCKET", str(folder/"absent-platform.sock"))
        monkeypatch.setattr(reconstruction, "WANTS_ROOT", folder/"absent-units")
        cfg = Config(str(REPO/"alembic.ini"))
        # The shared fixture supplies a historical stub DB. Replace it with a
        # real fresh schema created by the project's complete Alembic chain.
        for settings, root in ((current,source),(dest_settings,dest)):
            (root/"core/3mm.db").rename(root/"fixture-only.sqlite")
            with monkeypatch.context() as target_settings:
                target_settings.setattr("backend.config.get_settings", lambda: settings)
                command.upgrade(cfg,"head")

        source_host, fresh_host = host_factory(native_task_host,source), host_factory(native_task_host,dest)
        cleanup.callback(source_host.close); cleanup.callback(fresh_host.close)
        blob = build_package(REPO/"modules/application-starter")
        validated = validate_module_package(blob)
        owner = validated.manifest.module_id
        monkeypatch.setattr("backend.accounts.tokens.SECRET_KEY", "local-recovery-test-only-key-at-least-32-bytes")
        instance, original_epoch = install_fixture(current, source_host, blob, validated, reader=True)
        original_key = (source_host.keys/(instance+".key")).read_bytes()
        # Normal signed host interface with a synthetic test actor, not a
        # claim about the restored Web user's access or the HTTP admission layer.
        actor = {"audience":"operator","user_id":9,"subject_id":"usr_"+"3"*32,"correlation_id":"note-rehearsal",
                 "permission_ids":["note_read","note_write"]}
        original_id = "4"*32
        first = source_host.client(instance)
        saved = first.invoke("save_note", {"text":"recovery fixture","revision":0}, {**actor,"idempotency_key":original_id})
        assert saved == {"text":"recovery fixture","revision":1}
        source_host.close()
        previous_id = "5" * 32
        previous_epoch = None
        if fail_candidate:
            dest_instance, previous_epoch = install_fixture(dest_settings, fresh_host, blob, validated, reader=False)
            assert dest_instance == instance
            previous = fresh_host.client(instance).invoke("save_note", {"text": "previous installation", "revision": 0},
                                                         {**actor, "idempotency_key": previous_id})
            assert previous == {"text": "previous installation", "revision": 1}
        key = source/"keys/backup.key"
        backup = create_backup(current,key_file=key,requested_by_user_id=7,controller=Controller())
        exported = create_portable_export(current.backups.storage_dir,key,backup.backup_id,"rehearsal-only-password")
        copy = folder/"download.3mmrecovery"
        shutil.copyfile(exported.path,copy)
        # The target has neither the source directory nor its key in the
        # expected location. Do not erase user files or touch any live service.
        source.rename(folder/"detached-source")
        current = dest_settings
        assert verify_portable(copy,"rehearsal-only-password",target_architecture=os.uname().machine)["state"]=="validated"
        new_key = dest/"keys/backup.key"
        imported = import_portable_backup(copy,current.backups.storage_dir,new_key,"rehearsal-only-password",
                                          max_archive_bytes=32*1024*1024)

        def activate(path, sha, **kw):
            assert path == current.backend.uploads_dir/"modules"/(validated.sha256+".zip") and sha == validated.sha256
            # The fixture executes as its own UID; do not request production ownership.
            kw.pop("service_uid"); kw.pop("service_gid")
            return activate_application_package(path,sha,**kw,supervisor=fresh_host)
        monkeypatch.setattr(reconstruction,"activate_application_package",activate)

        verified_processes = []

        class Runtime(Controller):
            def stop(self, _services):
                fresh_host.close()

            def migrate(self):
                command.upgrade(cfg,"head")
            def activate_and_verify(self):
                assert reconstruction.restore_application_extensions(dest/"core/3mm.db",
                    upload_root=current.backend.uploads_dir/"modules",application_root=fresh_host.root,key_root=fresh_host.keys,
                    service_ids=(os.getuid(),os.getgid())) == (owner,)
                client = fresh_host.client(instance)
                restored_candidate = not verified_processes
                verified_processes.append(fresh_host.generation())
                assert client.invoke("read_note", {}, actor) == (saved if restored_candidate else previous)
                retained, absent = (original_id, previous_id) if restored_candidate else (previous_id, original_id)
                assert client.invoke("lookup_save", {"request_id": retained}, actor) == {"status":"found","revision":1}
                assert client.invoke("lookup_save", {"request_id": absent}, actor) == {"status":"not_found","revision":None}
                if fail_candidate and restored_candidate:
                    # The candidate actually served the backup. Simulate another
                    # failed health dependency only after that observable boundary.
                    raise RuntimeError("test readiness refused candidate")

        if fail_candidate:
            with pytest.raises(RuntimeError, match="test readiness refused candidate"):
                _restore(current, dest, imported, new_key, Runtime())
            status = read_backup_operation_status(current.backups.storage_dir / "status.json")
            assert status.state == "rolled_back" and status.error_code == "restore_rolled_back"
            assert len(set(verified_processes)) == 2
        else:
            assert _restore(current, dest, imported, new_key, Runtime()).state == "completed"
            assert len(verified_processes) == 1
        assert original_key != (fresh_host.keys/(instance+".key")).read_bytes()
        engine = create_engine(current.backend.database_url)
        try:
            with Session(engine) as db:
                restored = db.query(ApplicationExtensionInstallation).filter_by(module_id=owner).one()
                assert restored.authority_epoch not in (original_epoch, previous_epoch)
                assert restored.status == "active" and restored.enabled
                # Native host health alone is not enough: the Core gateway must
                # still resolve the reviewed package after the source disappears.
                active_package = db.get(ModulePackage, restored.module_package_id)
                assert load_application_package(active_package).sha256 == validated.sha256
                assert Path(active_package.file_path) == current.backend.uploads_dir / "modules" / (validated.sha256 + ".zip")
            check_operator_access(engine, owner, can_read=not fail_candidate)
            assert fresh_host.client(instance).invoke("read_note",{},actor) == (previous if fail_candidate else saved)
        finally:
            engine.dispose()
