import hashlib
import io
import json
import os
import zipfile
import sqlite3
from pathlib import Path
from types import SimpleNamespace

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
    erase_application_instance_data,
    uninstall_application_instance,
)
from three_mm_runtime import application_activation


def service_package() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                application_manifest(
                    runtimes=["core"],
                    entrypoints={"core": "application-extension.json"},
                    configuration_defaults={
                        "READER_DEVICE_ID": "dev_0123456789abcdef0123456789abcdef"
                    },
                )
            ),
        )
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

    def recover_disabled(self, instance_id):
        self.stop(instance_id)
        return dict(LoadState="loaded", ActiveState="inactive", SubState="dead",
                    UnitFileState="disabled", MainPID="0", Job="")


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


def test_health_timeout_bounds_elapsed_time_and_each_probe(monkeypatch):
    elapsed, timeouts = [0.0], []
    monkeypatch.setattr(application_activation, "time", SimpleNamespace(monotonic=lambda: elapsed[0]))

    class SlowClient:
        def __init__(self, _socket, _key, timeout):
            self.timeout = timeout
            timeouts.append(timeout)
        def invoke(self, *_args):
            elapsed[0] += self.timeout
            raise OSError("health response timed out")

    def sleep(seconds): elapsed[0] += seconds

    with pytest.raises(ApplicationActivationError, match="did not become healthy"):
        application_activation._wait_for_health(
            dict(startup_timeout_seconds=3, health_operation_id="health", sha256="a" * 64),
            b"k" * 32, Path("unused.sock"), client_factory=SlowClient, sleep=sleep)
    assert elapsed[0] == pytest.approx(3)
    assert timeouts == pytest.approx([2, 0.8])


def test_health_result_after_the_startup_deadline_cannot_confirm_activation(monkeypatch):
    elapsed = [0.0]
    monkeypatch.setattr(application_activation, "time", SimpleNamespace(monotonic=lambda: elapsed[0]))

    class LateClient(ReadyClient):
        def invoke(self, *_args):
            elapsed[0] += 4
            return {"status": "ready"}

    with pytest.raises(ApplicationActivationError, match="did not become healthy"):
        application_activation._wait_for_health(
            dict(startup_timeout_seconds=3, health_operation_id="health", sha256="a" * 64),
            b"k" * 32, Path("unused.sock"), client_factory=LateClient, sleep=lambda _seconds: None)


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
    assert active["configuration"]["READER_DEVICE_ID"] == (
        "dev_0123456789abcdef0123456789abcdef"
    )
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


def test_uninstall_removes_runtime_files_but_preserves_application_data(tmp_path):
    instance_id = "a" * 24
    root = tmp_path / "apps"
    key_root = tmp_path / "keys"
    instance_root = root / instance_id
    data_root = instance_root / "data"
    (instance_root / "releases/release").mkdir(parents=True)
    (instance_root / "run").mkdir()
    data_root.mkdir()
    key_root.mkdir()
    (instance_root / "active.json").write_text("{}", encoding="utf-8")
    (instance_root / "releases/release/service.whl").write_bytes(b"wheel")
    (instance_root / "run/service.sock").write_text("socket", encoding="utf-8")
    (data_root / "state.sqlite3").write_bytes(b"application-data")
    (key_root / f"{instance_id}.key").write_bytes(b"s" * 32)
    supervisor = Supervisor()

    uninstall_application_instance(
        instance_id,
        root=root,
        key_root=key_root,
        supervisor=supervisor,
    )

    assert supervisor.calls == [("stop", instance_id)]
    assert (data_root / "state.sqlite3").read_bytes() == b"application-data"
    assert not (instance_root / "active.json").exists()
    assert not (instance_root / "releases").exists()
    assert not (instance_root / "run").exists()
    assert not (key_root / f"{instance_id}.key").exists()


@pytest.mark.skipif(os.name != "posix", reason="Native FD-anchored erasure")
def test_erasing_preserved_data_requires_an_uninstalled_service(tmp_path):
    instance_id = "a" * 24
    root = tmp_path / "apps"
    data_root = root / instance_id / "data"
    data_root.mkdir(parents=True)
    (data_root / "state.sqlite3").write_bytes(b"application-data")

    with pytest.raises(ApplicationActivationError, match="cannot be erased"):
        erase_application_instance_data(
            instance_id,
            root=root,
            supervisor=EnabledSupervisor(),
        )
    assert (data_root / "state.sqlite3").exists()

    erase_application_instance_data(
        instance_id,
        root=root,
        supervisor=Supervisor(),
    )
    assert not data_root.exists()


@pytest.mark.skipif(os.name != "posix", reason="Native FD-anchored erasure")
def test_retained_erase_verifies_quiescence_even_when_boot_disabled(tmp_path):
    instance_id = "a" * 24
    root = tmp_path / "apps"
    data = root / instance_id / "data"
    data.mkdir(parents=True)
    (data / "state.sqlite3").write_bytes(b"private data")
    supervisor = Supervisor()
    erase_application_instance_data(instance_id, root=root, supervisor=supervisor)
    assert supervisor.calls == [("is_enabled", instance_id), ("stop", instance_id)]
    assert not data.exists()


@pytest.mark.skipif(os.name != "posix", reason="Native FD-anchored erasure")
@pytest.mark.parametrize("evidence", [None, {}, dict(LoadState="loaded", ActiveState="active",
    SubState="running", UnitFileState="disabled", MainPID="42", Job="")])
def test_retained_erase_refuses_unknown_or_running_unit(tmp_path, evidence):
    instance_id = "a" * 24
    root = tmp_path / "apps"
    data = root / instance_id / "data"
    data.mkdir(parents=True)
    sentinel = data / "state.sqlite3"
    sentinel.write_bytes(b"keep")
    class Unknown(Supervisor):
        def recover_disabled(self, _instance):
            return evidence
    with pytest.raises(ApplicationActivationError, match="confirmed stopped"):
        erase_application_instance_data(instance_id, root=root, supervisor=Unknown())
    assert sentinel.read_bytes() == b"keep"


@pytest.mark.skipif(os.name != "posix", reason="Native FD-anchored erasure")
def test_retained_erase_refuses_failed_stop_and_pending_rollback(tmp_path):
    instance_id = "a" * 24
    root = tmp_path / "apps"
    data = root / instance_id / "data"
    data.mkdir(parents=True)
    sentinel = data / "state.sqlite3"
    sentinel.write_bytes(b"keep")
    class Broken(Supervisor):
        def recover_disabled(self, _instance):
            raise ApplicationActivationError("Unknown stop outcome")
    with pytest.raises(ApplicationActivationError, match="Unknown stop"):
        erase_application_instance_data(instance_id, root=root, supervisor=Broken())
    marker = root / instance_id / (".activation-" + "b" * 32 + ".rollback")
    marker.mkdir()
    supervisor = Supervisor()
    with pytest.raises(ApplicationActivationError, match="unfinished rollback"):
        erase_application_instance_data(instance_id, root=root, supervisor=supervisor)
    assert not supervisor.calls and sentinel.read_bytes() == b"keep"


@pytest.mark.skipif(os.name != "posix", reason="Native FD-anchored erasure")
@pytest.mark.parametrize("position", ["ancestor", "instance", "data"])
def test_retained_erase_never_follows_symlink_outside_instance(tmp_path, position):
    instance_id = "a" * 24
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_bytes(b"outside data")
    root = tmp_path / "apps"
    if position == "ancestor":
        root.symlink_to(outside, target_is_directory=True)
    elif position == "instance":
        root.mkdir()
        (root / instance_id).symlink_to(outside, target_is_directory=True)
    else:
        (root / instance_id).mkdir(parents=True)
        (root / instance_id / "data").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ApplicationActivationError, match="directory is invalid"):
        erase_application_instance_data(instance_id, root=root, supervisor=Supervisor())
    assert sentinel.read_bytes() == b"outside data"


@pytest.mark.skipif(os.name != "posix", reason="Native FD-anchored erasure")
@pytest.mark.parametrize("fault", ["raise", "silent_noop"])
def test_retained_erase_does_not_report_failed_deletion_as_success(tmp_path, monkeypatch, fault):
    instance_id = "a" * 24
    root = tmp_path / "apps"
    data = root / instance_id / "data"
    data.mkdir(parents=True)
    sentinel = data / "state.sqlite3"
    sentinel.write_bytes(b"keep")
    def fail(*_args, **_kwargs):
        if fault == "raise":
            raise PermissionError("private filesystem detail")
    fail.avoids_symlink_attacks = True
    monkeypatch.setattr(application_activation.shutil, "rmtree", fail)
    with pytest.raises(ApplicationActivationError):
        erase_application_instance_data(instance_id, root=root, supervisor=Supervisor())
    assert sentinel.read_bytes() == b"keep"


@pytest.mark.skipif(os.name != "posix", reason="Native FD-anchored erasure")
def test_missing_retained_directory_still_requires_runtime_quiescence(tmp_path):
    supervisor = Supervisor()
    erase_application_instance_data("a" * 24, root=tmp_path / "missing", supervisor=supervisor)
    assert supervisor.calls == [("is_enabled", "a" * 24), ("stop", "a" * 24)]
