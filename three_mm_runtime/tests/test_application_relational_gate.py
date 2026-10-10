"""No unimplemented DB profile may fall back to the legacy writable host."""

import io
import json
import zipfile

import pytest

from backend.services.module_packages import validate_module_package
from three_mm_application_sdk import ApplicationStorage
from three_mm_protocol.tests.test_application_private_files import file_request
from three_mm_protocol.tests.test_application_relational_storage import (
    relational_request,
)
from three_mm_runtime import application_activation as activation
from three_mm_runtime import application_host as host
from three_mm_runtime.tests.test_application_file_host import (
    activate,
    metadata,
)
from three_mm_runtime.tests.test_application_file_host import package as legacy_package


@pytest.mark.parametrize("mode", ["read", "read_write"])
@pytest.mark.parametrize("existing", [False, True])
def test_activation_denies_before_any_runtime_change(
    legacy_package, tmp_path, monkeypatch, mode, existing
):
    path, _ = legacy_package(None)
    if existing:
        previous = activate(tmp_path, legacy_package, None)
        root, saved = metadata(tmp_path, previous)
        host._load_service(saved, root)
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    output = io.BytesIO()
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(output, "w") as target:
        for item in source.infolist():
            payload = source.read(item)
            if item.filename == "application-extension.json":
                definition = json.loads(payload)
                definition["storage"]["relational"] = relational_request(mode=mode)
                payload = json.dumps(definition)
            target.writestr(item, payload)
    checked = validate_module_package(output.getvalue())
    candidate = tmp_path / (checked.sha256 + ".zip")
    candidate.write_bytes(output.getvalue())
    before[candidate.relative_to(tmp_path)] = output.getvalue()

    def forbidden(*args, **kwargs):
        pytest.fail("Unsupported DB declaration reached runtime effects")

    monkeypatch.setattr(activation, "_prepare_directory", forbidden)
    monkeypatch.setattr(activation, "_stop_for_data", forbidden)
    monkeypatch.setattr(activation, "_write_atomic", forbidden)
    with pytest.raises(
        activation.ApplicationActivationError,
        match="relational storage runtime is not implemented",
    ):
        activation.activate_application_package(
            candidate,
            checked.sha256,
            root=tmp_path / "apps",
            key_root=tmp_path / "keys",
            supervisor=object(),
        )
    assert {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == before
    if not existing:
        assert not (tmp_path / "apps").exists() and not (tmp_path / "keys").exists()


@pytest.mark.parametrize(
    "profile",
    [
        relational_request(),
        {},
        False,
        "",
        {"approved": True, "path": "/var/lib/3mm/core"},
    ],
)
def test_host_cannot_import_or_open_database_from_unsupported_metadata(
    legacy_package, tmp_path, monkeypatch, profile
):
    previous = activate(tmp_path, legacy_package, None)
    root, saved = metadata(tmp_path, previous)
    saved["storage"]["relational"] = profile

    def forbidden(*args, **kwargs):
        pytest.fail("DB profile bypassed the host gate")

    monkeypatch.setattr(host.importlib, "import_module", forbidden)
    monkeypatch.setattr(ApplicationStorage, "_connect", forbidden)
    with pytest.raises(
        RuntimeError, match="relational storage runtime is not implemented"
    ):
        host._load_service(saved, root)
    with pytest.raises(
        RuntimeError, match="relational storage runtime is not implemented"
    ):
        host._serve_requests(saved, root, b"s" * 32, object(), None)
    assert list((root / "data").iterdir()) == []


def test_serve_refuses_db_profile_before_starting_file_executor(
    legacy_package, tmp_path, monkeypatch
):
    previous = activate(tmp_path, legacy_package, file_request())
    root, saved = metadata(tmp_path, previous)
    saved["storage"]["relational"] = relational_request()
    (root / "active.json").write_text(json.dumps(saved), encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("Unsupported relational profile started a file worker/service")

    monkeypatch.setattr(host, "ApplicationFileExecutor", forbidden)
    monkeypatch.setattr(host, "_load_service", forbidden)
    with pytest.raises(
        RuntimeError, match="relational storage runtime is not implemented"
    ):
        host.serve(previous.instance_id, tmp_path / "apps", tmp_path / "keys")
    assert not (root / "run/files.sock").exists()
    assert list((root / "data").iterdir()) == []
