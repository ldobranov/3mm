"""Actual ZIP/activation/host SDK denial; no live supervisor or device effects."""

import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import sys
import uuid
import zipfile

import pytest

from backend.services.module_packages import validate_module_package
from backend.tests.test_module_packages import (
    application_definition,
    application_manifest,
)
from three_mm_application_sdk import ApplicationFileStorage, ApplicationFileStorageError
from three_mm_protocol.tests.test_application_private_files import file_request
from three_mm_runtime import application_host
from three_mm_runtime.application_activation import (
    ApplicationActivationError,
    activate_application_package,
)
from three_mm_runtime.tests.test_application_activation import (
    BrokenClient,
    EnabledSupervisor,
    ReadyClient,
    Supervisor,
)


@pytest.fixture
def package(monkeypatch, tmp_path):
    module = "file_host_fixture_" + uuid.uuid4().hex
    monkeypatch.setattr(sys, "path", list(sys.path))
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(module + "/__init__.py", "")
        archive.writestr(
            module + "/service.py",
            """
class Service:
    def __init__(self, context):
        self.context = context
    def handle(self, operation_id, payload, context):
        return {"status": "ready"}
def create_service(context):
    return Service(context)
""",
        )
        archive.writestr(
            module + "/migrations.py",
            """
from three_mm_application_sdk import ApplicationMigration
def migrate(connection):
    connection.execute('CREATE TABLE records (id INTEGER PRIMARY KEY)')
def get_migrations():
    return [ApplicationMigration('0001', migrate)]
""",
        )

    def build(request, sdk="1.3"):
        definition = application_definition(routes=[])
        definition["service"].update(
            sdk_version=sdk,
            artifact_sha256=hashlib.sha256(wheel.getvalue()).hexdigest(),
            entrypoint=module + ".service:create_service",
        )
        definition["storage"].update(
            schema_revision="0001",
            migration_entrypoint=module + ".migrations:get_migrations",
        )
        if request is not None:
            definition["storage"]["private_files"] = request
        manifest = application_manifest(
            runtimes=["core"],
            entrypoints={"core": "application-extension.json"},
            configuration_defaults={
                "READER_DEVICE_ID": "dev_0123456789abcdef0123456789abcdef"
            },
        )
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("application-extension.json", json.dumps(definition))
            archive.writestr(definition["service"]["artifact"], wheel.getvalue())
        blob = output.getvalue()
        checked = validate_module_package(blob)
        path = tmp_path / (checked.sha256 + ".zip")
        path.write_bytes(blob)
        return path, checked.sha256

    yield build
    for name in tuple(sys.modules):
        if name == module or name.startswith(module + "."):
            sys.modules.pop(name)


def activate(
    tmp_path, package, request, *, client=ReadyClient, supervisor=None, sdk="1.3"
):
    path, digest = package(request, sdk)
    return activate_application_package(
        path,
        digest,
        root=tmp_path / "apps",
        key_root=tmp_path / "keys",
        supervisor=supervisor or Supervisor(),
        client_factory=client,
        sleep=lambda _: None,
    )


def metadata(tmp_path, activated):
    root = tmp_path / "apps" / activated.instance_id
    return root, json.loads((root / "active.json").read_text())


@pytest.mark.parametrize("mode", ["read", "read_write"])
@pytest.mark.parametrize("present", [False, True])
def test_validated_request_reaches_host_and_all_operations_deny_without_a_grant(
    package, tmp_path, monkeypatch, mode, present
):
    request = file_request(mode=mode, max_file_bytes=8, max_total_bytes=12, max_files=2)
    active = activate(tmp_path, package, request)
    root, saved = metadata(tmp_path, active)
    assert saved["storage"]["private_files"] == request
    expected_digest = "a" * 64
    if present:
        if os.name != "posix":
            pytest.skip("Existing private-file preimage uses POSIX")
        expected_digest = (
            ApplicationFileStorage(root / "data")
            .put("saved", b"keep", expected_sha256=None)
            .sha256
        )
    service = application_host._load_service(saved, root)
    files = service.context.files
    assert files.mode == mode and files.limits.max_file_bytes == 8
    assert files.limits.max_total_bytes == 12 and files.limits.max_files == 2
    assert files is service.context.files
    before = {
        path.relative_to(root / "data"): path.read_bytes()
        for path in (root / "data").rglob("*")
        if path.is_file()
    }

    def forbid_open(*args, **kwargs):
        pytest.fail("Unapproved SDK file operation attempted filesystem access")

    monkeypatch.setattr(ApplicationFileStorage, "_open_data", forbid_open)
    for operation in (
        lambda: files.get("saved"),
        files.list_entries,
        lambda: files.put("new", b"x", expected_sha256=None),
        lambda: files.put("saved", b"x", expected_sha256=expected_digest),
        lambda: files.delete("saved", expected_sha256=expected_digest),
    ):
        with pytest.raises(
            ApplicationFileStorageError, match="applied storage authority"
        ) as error:
            operation()
        assert str(root) not in str(error.value)
    assert {
        path.relative_to(root / "data"): path.read_bytes()
        for path in (root / "data").rglob("*")
        if path.is_file()
    } == before
    assert (root / "data" / "sdk-files").exists() == present


@pytest.mark.parametrize(
    "bad",
    [
        {"approved": True},
        {"path": "/var/lib/3mm/core"},
        {"max_files": True},
        {"max_total_bytes": 0},
        {"namespace": "foreign"},
        {"file_contract_version": 2},
        {"mode": "admin"},
        {"max_file_bytes": 16, "max_total_bytes": 8},
    ],
)
def test_invalid_protected_metadata_is_refused_before_import_or_database(
    package, tmp_path, monkeypatch, bad
):
    active = activate(tmp_path, package, file_request())
    root, saved = metadata(tmp_path, active)
    saved["storage"]["private_files"].update(bad)

    def forbid_import(*args):
        pytest.fail("Invalid file metadata caused package code import")

    monkeypatch.setattr(application_host.importlib, "import_module", forbid_import)
    with pytest.raises(RuntimeError, match="private file metadata is invalid"):
        application_host._load_service(saved, root)
    assert list((root / "data").iterdir()) == []


@pytest.mark.skipif(os.name != "posix", reason="Legacy helper uses real POSIX")
@pytest.mark.parametrize("sdk", ["1.0", "1.1", "1.2", "1.3"])
def test_undeclared_legacy_packages_keep_sdk_file_and_database_behavior(
    package, tmp_path, sdk
):
    active = activate(tmp_path, package, None, sdk=sdk)
    root, saved = metadata(tmp_path, active)
    assert "private_files" not in saved["storage"]
    service = application_host._load_service(saved, root)
    assert type(service.context.files) is ApplicationFileStorage
    item = service.context.files.put("legacy", b"old", expected_sha256=None)
    assert service.context.files.get("legacy") == item
    assert service.context.storage.status()["revision"] == "0001"


@pytest.mark.parametrize("previous_request", [None, file_request(mode="read")])
def test_failed_update_restores_exact_previous_file_policy_without_minting_grants(
    package, tmp_path, previous_request
):
    old = activate(tmp_path, package, previous_request)
    root, saved = metadata(tmp_path, old)
    before = (root / "active.json").read_bytes()
    with pytest.raises(
        ApplicationActivationError, match="previous version was restored"
    ):
        activate(
            tmp_path,
            package,
            file_request(),
            client=BrokenClient,
            supervisor=EnabledSupervisor(),
        )
    assert (root / "active.json").read_bytes() == before
    assert metadata(tmp_path, old)[1]["storage"] == saved["storage"]
    assert not (root / "data" / "sdk-files").exists()
    assert not tuple(root.glob(".activation-*.rollback"))


def test_actual_wheel_host_selects_platform_adapter_not_direct_native_io(package, tmp_path, monkeypatch):
    active = activate(tmp_path, package, file_request())
    root, saved = metadata(tmp_path, active)
    calls = []
    class Platform:
        def __init__(self, path, instance, secret):
            assert path == Path(saved["platform_socket"])
            assert instance == active.instance_id and secret == b"s" * 32
        def _call(self, action, payload):
            calls.append((action, payload))
            value = payload["file_request"]
            return {"receipt": {"request_id": value["request_id"], "operation": "get",
                "file_id": "logo", "outcome": "completed"}, "file_result": {"file": None}}
    monkeypatch.setattr(application_host, "ApplicationPlatformClient", Platform)
    service = application_host._load_service(saved, root, b"s" * 32)
    from three_mm_application_sdk import ApplicationScopedFileStorage
    assert type(service.context.files) is ApplicationScopedFileStorage
    assert service.context.files.platform is service.context.platform
    assert service.context.files.get("logo") is None
    assert len(calls) == 1 and calls[0][0] == "files.execute"
    assert not (root / "data/sdk-files").exists()


@pytest.mark.skipif(os.name != "posix", reason="Actual supervised file socket")
def test_host_starts_worker_before_factory_and_cleans_socket_on_exit(package, monkeypatch):
    from three_mm_runtime.application_file_executor import call_file_executor
    with tempfile.TemporaryDirectory(prefix="3mm-host-") as temporary:
        path = Path(temporary)
        active = activate(path, package, file_request())
        root, saved = metadata(path, active)
        secret = (path / "keys" / (active.instance_id + ".key")).read_bytes()
        calls = []
        original_load = application_host._load_service
        def load(metadata, instance_root, platform_secret):
            hello = call_file_executor(instance_root / "run/files.sock", platform_secret, "hello", {})
            assert hello["instance_id"] == active.instance_id
            calls.append("worker_ready_before_factory")
            return original_load(metadata, instance_root, platform_secret)
        def serve(metadata, instance_root, platform_secret, service, group_id):
            assert service.context.files.platform is service.context.platform
            assert platform_secret == secret
            assert (instance_root / "run/files.sock").is_socket()
            calls.append("handler_ready")
        monkeypatch.setattr(application_host, "_load_service", load)
        monkeypatch.setattr(application_host, "_serve_requests", serve)
        application_host.serve(active.instance_id, path / "apps", path / "keys")
        assert calls == ["worker_ready_before_factory", "handler_ready"]
        assert not (root / "run/files.sock").exists()
        assert not (root / "data/sdk-files").exists()
