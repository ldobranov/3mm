"""HTTP integration selects a trusted installation baseline, never an upload hint."""

import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest
from sqlalchemy import event, select

from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.routes import modules
from backend.services import application_authority_inspection as authority
from backend.tests.test_application_authority_review import CONFIG
from backend.tests.test_module_inspection import (
    api,
)  # noqa: F401 -- shared HTTP/auth fixture
from backend.tests.test_module_packages import (
    application_package,
    application_definition,
    package,
)
from backend.services.module_packages import MAX_PACKAGE_BYTES, validate_module_package
from backend.utils.auth_dep import require_admin


URL = "/api/v1/modules/packages/inspect?include_authority_review=true"


def versioned(blob, version):
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(blob)) as source,
        zipfile.ZipFile(output, "w") as target,
    ):
        for item in source.infolist():
            value = source.read(item.filename)
            if item.filename in {
                "manifest.json",
                "application-extension.json",
                "compiled-ui.json",
            }:
                definition = json.loads(value)
                definition["version"] = version
                value = json.dumps(definition)
            target.writestr(item.filename, value)
    return output.getvalue()


def store_package(api, root, blob):
    validated = validate_module_package(blob)
    archive = root / "modules" / f"{validated.sha256}.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(blob)
    record = ModulePackage(
        module_id=validated.manifest.module_id,
        version=validated.manifest.version,
        sha256=validated.sha256,
        size_bytes=len(blob),
        manifest=validated.manifest.model_dump(mode="json"),
        registrations=[],
        file_path="/never-read-this-catalog-path.zip",
    )
    api.db.add(record)
    api.db.commit()
    return record, archive


@pytest.fixture
def installed(api, monkeypatch, tmp_path):
    root = tmp_path / "uploads"
    monkeypatch.setattr(
        modules,
        "get_settings",
        lambda: SimpleNamespace(backend=SimpleNamespace(uploads_dir=root)),
    )
    record, archive = store_package(api, root, application_package())
    installation = ApplicationExtensionInstallation(
        module_id=record.module_id,
        module_package_id=record.id,
        active_version=record.version,
        status="active",
        enabled=True,
        instance_id="a" * 24,
        socket_path="/not-contacted.sock",
        configuration=dict(CONFIG),
    )
    api.db.add(installation)
    api.db.commit()
    return SimpleNamespace(
        api=api, root=root, package=record, archive=archive, installation=installation
    )


def inspect(api, blob=None, url=URL):
    response = api.client.post(
        url, content=blob or application_package(), headers=api.headers()
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()["authority_review"]


def test_opt_in_uses_installed_pointer_not_latest_catalog_or_client_hint(installed):
    state = installed
    newer, _ = store_package(
        state.api, state.root, versioned(application_package(), "9.0.0")
    )
    candidate = versioned(application_package(), "2.0.0")
    result = inspect(
        state.api,
        candidate,
        URL + f"&baseline_package_id={newer.id}&configuration=untrusted",
    )
    assert result["status"] == "available" and result["review_version"] == 1
    assert result["configuration_source"] == "saved_installation_reused"
    assert result["review"]["previous_version"] == "1.0.0"
    assert result["review"]["candidate_version"] == "2.0.0"
    assert result["review"]["previous_sha256"] == state.package.sha256
    assert result["review"]["baseline"] == "previous_declarations"
    assert result["review"]["artifact_changed"]
    assert result["review"]["changes"] == []
    assert result["review"]["permission_approval"] == "not_evaluated"
    assert state.installation.module_package_id == state.package.id


def test_existing_inspection_remains_opt_in_and_does_not_read_baseline(
    installed, monkeypatch
):
    monkeypatch.setattr(
        authority, "_read_baseline", lambda *_args: pytest.fail("opt-in required")
    )
    result = inspect(installed.api, url="/api/v1/modules/packages/inspect")
    assert result is None


def test_first_install_ignores_uninstalled_catalog_artifacts(
    api, monkeypatch, tmp_path
):
    root = tmp_path / "uploads"
    monkeypatch.setattr(
        modules,
        "get_settings",
        lambda: SimpleNamespace(backend=SimpleNamespace(uploads_dir=root)),
    )
    store_package(api, root, versioned(application_package(), "9.0.0"))
    result = inspect(api)
    assert result["status"] == "available"
    assert result["configuration_source"] == "not_supplied"
    assert result["review"]["baseline"] == "no_previous_package"
    assert result["review"]["previous_sha256"] is None
    assert result["review"]["unresolved"]
    assert all(item["change"] == "added" for item in result["review"]["changes"])


def test_disabled_installation_can_be_compared_without_enable(installed):
    installed.installation.status = "disabled"
    installed.installation.enabled = False
    installed.api.db.commit()
    result = inspect(installed.api)
    assert result["status"] == "available"
    assert result["review"]["changes"] == []
    assert not installed.installation.enabled


@pytest.mark.parametrize("status", ["activating", "disabling", "failed"])
def test_transitional_or_failed_installation_never_looks_like_first_install(
    installed, status
):
    installed.installation.status = status
    installed.api.db.commit()
    result = inspect(installed.api)
    assert result["status"] == "unavailable" and result["review"] is None
    assert result["reason"] == "installation_not_stable"


@pytest.mark.parametrize(
    "problem", ["missing", "corrupt", "wrong_digest", "oversized", "symlink", "fifo"]
)
def test_bad_baseline_is_bounded_unavailable_not_fallback_or_raw_error(
    installed, problem, tmp_path
):
    archive = installed.archive
    if problem == "missing":
        archive.unlink()
    elif problem == "corrupt":
        archive.write_bytes(b"PRIVATE_NOT_A_ZIP")
    elif problem == "wrong_digest":
        archive.write_bytes(versioned(application_package(), "2.0.0"))
    elif problem == "oversized":
        archive.write_bytes(b"x" * (MAX_PACKAGE_BYTES + 1))
    elif problem == "symlink":
        archive.unlink()
        foreign = tmp_path / "PRIVATE_FOREIGN_FILE"
        foreign.write_bytes(application_package())
        archive.symlink_to(foreign)
    elif problem == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("FIFO proof requires Linux")
        archive.unlink()
        os.mkfifo(archive)
    result = inspect(installed.api)
    assert result["status"] == "unavailable" and result["review"] is None
    assert result["reason"] == "baseline_unavailable"
    assert "PRIVATE" not in json.dumps(result)
    assert str(tmp_path) not in json.dumps(result)


def test_candidate_new_required_binding_stays_unresolved_and_configuration_is_private(
    installed,
):
    definition = application_definition()
    definition["event_subscriptions"][0][
        "device_scope_config_key"
    ] = "NEW_READER_DEVICE_ID"
    manifest = dict(installed.package.manifest)
    manifest["configuration_schema"] = {
        **manifest["configuration_schema"],
        "properties": {
            **manifest["configuration_schema"]["properties"],
            "NEW_READER_DEVICE_ID": {"type": "string"},
        },
    }
    result = inspect(
        installed.api,
        application_package(definition=definition, manifest_value=manifest),
    )
    assert result["status"] == "available"
    assert any(
        item["side"] == "candidate" and "configuration" in item["reason"]
        for item in result["review"]["unresolved"]
    )
    assert installed.installation.configuration == CONFIG
    installed.installation.configuration = {
        **CONFIG,
        "BUSINESS_API_CREDENTIAL": "PRIVATE_PASSWORD_VALUE",
    }
    installed.api.db.commit()
    response = installed.api.client.post(
        URL, content=application_package(), headers=installed.api.headers()
    )
    assert response.status_code == 200
    assert "PRIVATE_PASSWORD_VALUE" not in response.text


@pytest.mark.parametrize("subject,status", [(None, 401), (2, 403), (3, 401)])
def test_opt_in_retains_real_admin_auth_before_any_archive_read(
    installed, monkeypatch, subject, status
):
    monkeypatch.setattr(
        authority,
        "_read_baseline",
        lambda *_args: pytest.fail("unauthorized baseline read"),
    )
    headers = (
        installed.api.headers(subject)
        if subject is not None
        else {"Content-Type": "application/zip"}
    )
    response = installed.api.client.post(
        URL, content=application_package(), headers=headers
    )
    assert response.status_code == status


def test_non_application_review_does_not_read_installed_artifact(
    installed, monkeypatch
):
    monkeypatch.setattr(
        authority,
        "_read_baseline",
        lambda *_args: pytest.fail("non-application baseline read"),
    )
    result = inspect(installed.api, package())
    assert (
        result["status"] == "not_applicable" and result["reason"] == "application_only"
    )


def test_opt_in_never_flushes_writes_builds_extracts_or_executes(
    installed, monkeypatch
):
    api = installed.api
    api.app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1)
    api.db.add(ModulePackage(module_id="org.example.pending", version="1.0.0"))

    def forbidden(*_args, **_kwargs):
        pytest.fail("inspection must not mutate state or execute code")

    def only_select(_connection, _cursor, statement, *_args):
        assert statement.lstrip().upper().startswith("SELECT"), statement

    event.listen(api.engine, "before_cursor_execute", only_select)
    monkeypatch.setattr(modules, "compile_ui_package", forbidden)
    for name in ("add", "commit", "flush", "delete"):
        monkeypatch.setattr(api.db, name, forbidden)
    for name in ("write_bytes", "write_text", "mkdir"):
        monkeypatch.setattr(Path, name, forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", forbidden)
    monkeypatch.setattr(authority.os, "system", forbidden)
    try:
        first = inspect(api)
        second = inspect(api)
        assert first == second
        with api.db.no_autoflush:
            row = api.db.execute(
                select(
                    ApplicationExtensionInstallation.configuration,
                    ApplicationExtensionInstallation.status,
                    ApplicationExtensionInstallation.enabled,
                )
            ).one()
        assert row == (CONFIG, "active", True)
    finally:
        event.remove(api.engine, "before_cursor_execute", only_select)
