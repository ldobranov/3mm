import hashlib
import io
import json
import zipfile
import sqlite3
from pathlib import Path

import pytest

from backend.services.module_packages import validate_module_package
from backend.tests.test_module_packages import (
    APPLICATION_WHEEL,
    application_definition,
    application_manifest,
)
from three_mm_runtime.application_activation import (
    ApplicationActivationError,
    activate_application_package,
    application_instance_id,
)
from three_mm_runtime import application_activation


def service_package() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(application_manifest(runtimes=["core"], entrypoints={"core": "application-extension.json"})))
        definition = application_definition(routes=[])
        archive.writestr("application-extension.json", json.dumps(definition))
        archive.writestr(definition["service"]["artifact"], APPLICATION_WHEEL)
    return output.getvalue()


class Supervisor:
    def __init__(self):
        self.calls = []

    def is_enabled(self, instance_id):
        self.calls.append(("is_enabled", instance_id))
        return False

    def restart(self, instance_id):
        self.calls.append(("restart", instance_id))

    def stop(self, instance_id):
        self.calls.append(("stop", instance_id))


class ReadyClient:
    def __init__(self, *_args):
        pass

    def invoke(self, operation_id, payload, context):
        return {"status": "ready"}


class BrokenClient(ReadyClient):
    def invoke(self, operation_id, payload, context):
        raise OSError("not ready")


class EnabledSupervisor(Supervisor):
    def is_enabled(self, instance_id):
        self.calls.append(("is_enabled", instance_id))
        return True


def test_activation_stages_only_the_reviewed_wheel_and_becomes_active(tmp_path):
    blob = service_package()
    package_path = tmp_path / "uploads" / f"{hashlib.sha256(blob).hexdigest()}.zip"
    package_path.parent.mkdir()
    package_path.write_bytes(blob)
    supervisor = Supervisor()

    result = activate_application_package(
        package_path,
        hashlib.sha256(blob).hexdigest(),
        root=tmp_path / "apps",
        key_root=tmp_path / "keys",
        supervisor=supervisor,
        client_factory=ReadyClient,
    )

    active = json.loads((tmp_path / "apps" / result.instance_id / "active.json").read_text())
    assert active["sha256"] == result.sha256
    assert active["wheel"] == "service.whl"
    assert (tmp_path / "keys" / f"{result.instance_id}.key").stat().st_size == 32
    assert supervisor.calls == [("restart", result.instance_id)]


def test_activation_repairs_service_directory_modes_independently_of_umask(
    tmp_path,
    monkeypatch,
):
    blob = service_package()
    package_path = tmp_path / "uploads" / f"{hashlib.sha256(blob).hexdigest()}.zip"
    package_path.parent.mkdir()
    package_path.write_bytes(blob)
    chmod_calls = []
    real_chmod = application_activation.os.chmod

    def record_chmod(path, mode):
        chmod_calls.append((Path(path), mode))
        real_chmod(path, mode)

    monkeypatch.setattr(application_activation.os, "chmod", record_chmod)
    root = tmp_path / "apps"
    keys = tmp_path / "keys"

    result = activate_application_package(
        package_path,
        hashlib.sha256(blob).hexdigest(),
        root=root,
        key_root=keys,
        supervisor=Supervisor(),
        client_factory=ReadyClient,
    )

    instance_root = root / result.instance_id
    expected_directories = {
        instance_root,
        instance_root / "releases",
        instance_root / "releases" / result.sha256,
        instance_root / "data",
        instance_root / "run",
        keys,
    }
    normalized_directories = {
        path for path, mode in chmod_calls if mode == 0o750
    }
    assert expected_directories <= normalized_directories


def test_failed_first_activation_removes_active_pointer_and_stops_service(tmp_path):
    blob = service_package()
    sha256 = hashlib.sha256(blob).hexdigest()
    package_path = tmp_path / f"{sha256}.zip"
    package_path.write_bytes(blob)
    supervisor = Supervisor()

    with pytest.raises(ApplicationActivationError, match="previous version was restored"):
        activate_application_package(
            package_path,
            sha256,
            root=tmp_path / "apps",
            key_root=tmp_path / "keys",
            supervisor=supervisor,
            client_factory=BrokenClient,
            sleep=lambda _seconds: None,
        )

    instance = application_instance_id("org.3mm.workflow-reference")
    assert not (tmp_path / "apps" / instance / "active.json").exists()
    assert supervisor.calls[-1] == ("stop", instance)


def test_failed_upgrade_restores_previous_sqlite_state(tmp_path):
    blob = service_package()
    sha256 = hashlib.sha256(blob).hexdigest()
    package_path = tmp_path / f"{sha256}.zip"
    package_path.write_bytes(blob)
    root = tmp_path / "apps"
    keys = tmp_path / "keys"
    activate_application_package(
        package_path,
        sha256,
        root=root,
        key_root=keys,
        supervisor=Supervisor(),
        client_factory=ReadyClient,
    )
    instance = application_instance_id("org.3mm.workflow-reference")
    database = root / instance / "data/state.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE records(value TEXT)")
        connection.execute("INSERT INTO records VALUES ('previous')")

    class MutatingBrokenClient(ReadyClient):
        def invoke(self, *_args):
            with sqlite3.connect(database) as connection:
                connection.execute("DELETE FROM records")
                connection.execute("INSERT INTO records VALUES ('candidate')")
            raise OSError("candidate failed")

    with pytest.raises(ApplicationActivationError):
        activate_application_package(
            package_path,
            sha256,
            root=root,
            key_root=keys,
            supervisor=EnabledSupervisor(),
            client_factory=MutatingBrokenClient,
            sleep=lambda _seconds: None,
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM records").fetchall() == [
            ("previous",)
        ]
