from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.config import BackendSettings, FrontendSettings, UpdateCatalogSettings
from backend.services.system_updates import (
    CurrentRelease,
    LatestRelease,
    UpdateArtifact,
    UpdateCheckResponse,
    UpdateDependencies,
)
from backend.services.update_staging import (
    REQUIRED_RELEASE_FILES,
    StagedUpdate,
    UpdateApplyRequest,
    UpdateOperationStatus,
    UpdateStagingError,
    approve_staged_update,
    read_operation_status,
    revalidate_official_release,
    stage_latest_update,
    validate_staged_payload,
    write_operation_status,
)

COMMIT = "b" * 40


def write_allowlist(path: Path, packages: list[str] | None = None) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "apt_packages": packages or ["ca-certificates", "python3"],
            }
        ),
        encoding="utf-8",
    )


def write_release_archive(
    path: Path,
    *,
    release_id: str = "v1.2.0",
    version: str = "1.2.0",
    commit: str = COMMIT,
    architecture: str = "aarch64",
    extra_entries: dict[str, bytes] | None = None,
) -> None:
    files = {
        name: b"placeholder\n"
        for name in REQUIRED_RELEASE_FILES
        if name != ".3mm-release.json"
    }
    files["frontend/dist/assets/main.js"] = b"console.log('3mm')\n"
    files["deployment/release-dependencies.json"] = json.dumps(
        {
            "schema_version": 1,
            "apt_packages": ["ca-certificates", "python3"],
        }
    ).encode("utf-8")
    files[".3mm-release.json"] = json.dumps(
        {
            "architecture": architecture,
            "branch": "main",
            "commit": commit,
            "created_at": "2026-08-26T08:00:00+00:00",
            "includes_working_tree": False,
            "release_id": release_id,
            "version": version,
        }
    ).encode("utf-8")
    files.update(extra_entries or {})
    with tarfile.open(path, "w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def settings(tmp_path: Path) -> UpdateCatalogSettings:
    allowlist = tmp_path / "allowlist.json"
    write_allowlist(allowlist)
    return UpdateCatalogSettings(
        release_metadata_file=tmp_path / ".3mm-release.json",
        staging_dir=tmp_path / "staging",
        dependency_allowlist_file=allowlist,
        helper_socket=tmp_path / "helper.sock",
        helper_status_file=tmp_path / "helper-status.json",
        minimum_free_bytes=64 * 1024 * 1024,
    )


def catalog_for(
    archive: Path, packages: list[str] | None = None
) -> UpdateCheckResponse:
    data = archive.read_bytes()
    artifact = UpdateArtifact(
        architecture="aarch64",
        filename="3mm-1.2.0-aarch64.tar.gz",
        download_url=(
            "https://github.com/ldobranov/3mm/releases/download/"
            "v1.2.0/3mm-1.2.0-aarch64.tar.gz"
        ),
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
    )
    return UpdateCheckResponse(
        status="update_available",
        message="available",
        repository="ldobranov/3mm",
        repository_url="https://github.com/ldobranov/3mm",
        architecture="aarch64",
        current=CurrentRelease(
            release_id="v1.1.0",
            commit="a" * 40,
            metadata_available=True,
        ),
        latest=LatestRelease(
            tag="v1.2.0",
            name="3mm 1.2.0",
            published_at=datetime.now(UTC),
            html_url="https://github.com/ldobranov/3mm/releases/tag/v1.2.0",
            manifest_validated=True,
            version="1.2.0",
            release_id="v1.2.0",
            commit=COMMIT,
            channel="stable",
            artifacts=[artifact],
            dependencies=UpdateDependencies(
                apt_packages=packages or ["ca-certificates", "python3"]
            ),
        ),
        update_available=True,
        checked_at=datetime.now(UTC),
    )


def stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    packages: list[str] | None = None,
) -> tuple[UpdateCatalogSettings, Path, object]:
    source = tmp_path / "source.tar.gz"
    write_release_archive(source)
    update_settings = settings(tmp_path)
    catalog = catalog_for(source, packages)
    monkeypatch.setattr(
        "backend.services.update_staging.platform.machine", lambda: "aarch64"
    )

    def copy_artifact(_artifact, destination, _settings) -> None:
        shutil.copyfile(source, destination)
        os.chmod(destination, 0o600)

    result = stage_latest_update(
        update_settings,
        BackendSettings(database_url=f"sqlite:///{tmp_path / 'new.db'}"),
        FrontendSettings(frontend_url="http://192.168.1.88:8080"),
        catalog_checker=lambda _settings: catalog,
        downloader=copy_artifact,
        dependency_inspector=lambda requested: {
            name: name == "ca-certificates" for name in requested
        },
        disk_usage_reader=lambda _path: SimpleNamespace(free=1024 * 1024 * 1024),
    )
    return update_settings, source, result


def test_stage_downloads_one_architecture_and_records_reviewable_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    update_settings, _source, result = stage(tmp_path, monkeypatch)

    assert result.status == "ready"
    assert result.staged.release_id == "v1.2.0"
    assert result.staged.approval_nonce not in result.staged.model_dump_json(
        exclude={"approval_nonce"}
    )
    assert [(item.name, item.action) for item in result.staged.dependency_plan] == [
        ("ca-certificates", "keep"),
        ("python3", "install"),
    ]
    assert all(check.passed for check in result.staged.preflight)
    assert (update_settings.staging_dir / "staged-release.tar.gz").is_file()
    assert (update_settings.staging_dir / "stage.json").is_file()


def test_stage_rejects_dependency_outside_installed_allowlist_before_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.tar.gz"
    write_release_archive(source)
    update_settings = settings(tmp_path)
    catalog = catalog_for(source, ["curl"])
    monkeypatch.setattr(
        "backend.services.update_staging.platform.machine", lambda: "aarch64"
    )
    downloaded = False

    def downloader(*_arguments) -> None:
        nonlocal downloaded
        downloaded = True

    with pytest.raises(UpdateStagingError, match="outside the allowlist"):
        stage_latest_update(
            update_settings,
            BackendSettings(database_url=f"sqlite:///{tmp_path / 'new.db'}"),
            FrontendSettings(frontend_url="http://192.168.1.88:8080"),
            catalog_checker=lambda _settings: catalog,
            downloader=downloader,
            dependency_inspector=lambda _packages: {},
            disk_usage_reader=lambda _path: SimpleNamespace(free=1024**3),
        )

    assert downloaded is False


def test_stage_rejects_a_release_that_is_not_newer_before_download(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tar.gz"
    write_release_archive(source)
    update_settings = settings(tmp_path)
    catalog = catalog_for(source).model_copy(
        update={"status": "not_newer", "update_available": False}
    )
    downloaded = False

    def downloader(*_arguments) -> None:
        nonlocal downloaded
        downloaded = True

    with pytest.raises(UpdateStagingError, match="not newer"):
        stage_latest_update(
            update_settings,
            BackendSettings(database_url=f"sqlite:///{tmp_path / 'new.db'}"),
            FrontendSettings(frontend_url="http://192.168.1.88:8080"),
            catalog_checker=lambda _settings: catalog,
            downloader=downloader,
        )

    assert downloaded is False


def test_privileged_revalidation_rejects_a_tampered_staged_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    update_settings, _source, result = stage(tmp_path, monkeypatch)
    archive = update_settings.staging_dir / "staged-release.tar.gz"
    archive.write_bytes(archive.read_bytes() + b"tampered")

    with pytest.raises(UpdateStagingError, match="size changed"):
        validate_staged_payload(
            update_settings.staging_dir,
            update_settings.dependency_allowlist_file,
            release_id=result.staged.release_id,
            approval_nonce=result.staged.approval_nonce,
        )


def test_apply_requires_exact_version_confirmation_and_schedules_only_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    update_settings, _source, result = stage(tmp_path, monkeypatch)
    staged = result.staged
    scheduled: list[tuple[str, str, int]] = []

    with pytest.raises(UpdateStagingError, match="Explicit version confirmation"):
        approve_staged_update(
            update_settings,
            UpdateApplyRequest(
                release_id=staged.release_id,
                approval_nonce=staged.approval_nonce,
                confirmation="yes",
            ),
            requested_by_user_id=7,
            scheduler=lambda *arguments: scheduled.append(arguments),
        )

    queued = approve_staged_update(
        update_settings,
        UpdateApplyRequest(
            release_id=staged.release_id,
            approval_nonce=staged.approval_nonce,
            confirmation="INSTALL 1.2.0",
        ),
        requested_by_user_id=7,
        scheduler=lambda *arguments: scheduled.append(arguments),
    )

    assert queued.state == "queued"
    assert scheduled == [(staged.release_id, staged.approval_nonce, 7)]


def test_expired_stage_cannot_be_approved(tmp_path: Path) -> None:
    update_settings = settings(tmp_path)
    update_settings.staging_dir.mkdir()
    expired = StagedUpdate(
        release_id="v1.2.0",
        version="1.2.0",
        commit=COMMIT,
        architecture="aarch64",
        artifact_filename="3mm-1.2.0-aarch64.tar.gz",
        artifact_sha256="c" * 64,
        artifact_size_bytes=123,
        frontend_origin="http://192.168.1.88:8080",
        staged_at=datetime.now(UTC) - timedelta(hours=2),
        approval_expires_at=datetime.now(UTC) - timedelta(hours=1),
        approval_nonce="d" * 64,
        preflight=[],
    )
    (update_settings.staging_dir / "stage.json").write_text(
        expired.model_dump_json(), encoding="utf-8"
    )

    with pytest.raises(UpdateStagingError, match="expired"):
        approve_staged_update(
            update_settings,
            UpdateApplyRequest(
                release_id=expired.release_id,
                approval_nonce=expired.approval_nonce,
                confirmation="INSTALL 1.2.0",
            ),
            requested_by_user_id=7,
            scheduler=lambda *_arguments: None,
        )


def test_operation_status_is_strict_and_reports_persisted_result(
    tmp_path: Path,
) -> None:
    update_settings = settings(tmp_path)
    completed = UpdateOperationStatus(
        state="succeeded",
        message="healthy",
        release_id="v1.2.0",
        version="1.2.0",
        commit=COMMIT,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    write_operation_status(update_settings.helper_status_file, completed)

    assert read_operation_status(update_settings) == completed


def test_root_revalidation_rejects_staging_state_that_differs_from_official_catalog(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tar.gz"
    write_release_archive(source)
    official = catalog_for(source)
    staged = StagedUpdate(
        release_id="v1.2.0",
        version="1.2.0",
        commit=COMMIT,
        architecture="aarch64",
        artifact_filename="3mm-1.2.0-aarch64.tar.gz",
        artifact_sha256="f" * 64,
        artifact_size_bytes=1234,
        dependencies=["ca-certificates", "python3"],
        frontend_origin="http://192.168.1.88:8080",
        staged_at=datetime.now(UTC),
        approval_expires_at=datetime.now(UTC) + timedelta(minutes=30),
        approval_nonce="d" * 64,
        preflight=[],
    )

    with pytest.raises(UpdateStagingError, match="no longer matches"):
        revalidate_official_release(
            staged,
            repository="ldobranov/3mm",
            manifest_asset_name="3mm-update-manifest.json",
            release_metadata_file=tmp_path / ".3mm-release.json",
            catalog_checker=lambda _settings: official,
        )


def test_root_revalidation_rejects_an_official_release_that_is_not_newer(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tar.gz"
    write_release_archive(source)
    official = catalog_for(source).model_copy(
        update={"status": "not_newer", "update_available": False}
    )
    staged = StagedUpdate(
        release_id="v1.2.0",
        version="1.2.0",
        commit=COMMIT,
        architecture="aarch64",
        artifact_filename="3mm-1.2.0-aarch64.tar.gz",
        artifact_sha256=official.latest.artifacts[0].sha256,
        artifact_size_bytes=official.latest.artifacts[0].size_bytes,
        dependencies=["ca-certificates", "python3"],
        frontend_origin="http://192.168.1.88:8080",
        staged_at=datetime.now(UTC),
        approval_expires_at=datetime.now(UTC) + timedelta(minutes=30),
        approval_nonce="d" * 64,
        preflight=[],
    )

    with pytest.raises(UpdateStagingError, match="not eligible"):
        revalidate_official_release(
            staged,
            repository="ldobranov/3mm",
            manifest_asset_name="3mm-update-manifest.json",
            release_metadata_file=tmp_path / ".3mm-release.json",
            catalog_checker=lambda _settings: official,
        )
