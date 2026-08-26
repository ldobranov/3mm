import json
from pathlib import Path

import pytest

from backend.config import UpdateCatalogSettings
from backend.services.system_updates import (
    UpdateCatalogNotFound,
    check_update_catalog,
    read_local_update_status,
)


CURRENT_COMMIT = "a" * 40
LATEST_COMMIT = "b" * 40
ARTIFACT_SHA256 = "c" * 64


def write_release_metadata(
    path: Path,
    *,
    commit: str = CURRENT_COMMIT,
    version: str | None = None,
) -> None:
    payload = {
        "release_id": "current-release",
        "branch": "main",
        "commit": commit,
        "created_at": "2026-08-26T08:00:00Z",
        "includes_working_tree": False,
    }
    if version is not None:
        payload["version"] = version
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def catalog_payloads() -> tuple[dict, dict]:
    release_base = "https://github.com/ldobranov/3mm/releases/download/v1.2.0"
    release = {
        "tag_name": "v1.2.0",
        "name": "3mm 1.2.0",
        "published_at": "2026-08-26T08:30:00Z",
        "html_url": "https://github.com/ldobranov/3mm/releases/tag/v1.2.0",
        "assets": [
            {
                "name": "3mm-update-manifest.json",
                "browser_download_url": f"{release_base}/3mm-update-manifest.json",
                "size": 500,
            },
            {
                "name": "3mm-1.2.0-aarch64.tar.gz",
                "browser_download_url": f"{release_base}/3mm-1.2.0-aarch64.tar.gz",
                "size": 1234,
                "digest": f"sha256:{ARTIFACT_SHA256}",
            },
        ],
    }
    manifest = {
        "schema_version": 1,
        "version": "1.2.0",
        "release_id": "v1.2.0",
        "commit": LATEST_COMMIT,
        "channel": "stable",
        "artifacts": [
            {
                "architecture": "aarch64",
                "filename": "3mm-1.2.0-aarch64.tar.gz",
                "download_url": f"{release_base}/3mm-1.2.0-aarch64.tar.gz",
                "sha256": ARTIFACT_SHA256,
                "size_bytes": 1234,
            }
        ],
        "dependencies": {"apt_packages": ["rsync"]},
    }
    return release, manifest


def make_settings(metadata_file: Path) -> UpdateCatalogSettings:
    return UpdateCatalogSettings(release_metadata_file=metadata_file)


def test_local_status_does_not_call_the_network(tmp_path: Path) -> None:
    metadata_file = tmp_path / ".3mm-release.json"
    write_release_metadata(metadata_file)

    response = read_local_update_status(make_settings(metadata_file))

    assert response.status == "not_checked"
    assert response.current.release_id == "current-release"
    assert response.current.commit == CURRENT_COMMIT
    assert response.checked_at is None


def test_no_published_release_is_a_normal_catalog_state(tmp_path: Path) -> None:
    metadata_file = tmp_path / ".3mm-release.json"
    write_release_metadata(metadata_file)

    def not_found(_url: str, _timeout: int) -> object:
        raise UpdateCatalogNotFound("not found")

    response = check_update_catalog(make_settings(metadata_file), fetch_json=not_found)

    assert response.status == "no_release"
    assert response.update_available is None
    assert response.checked_at is not None


def test_valid_manifest_reports_an_available_update(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metadata_file = tmp_path / ".3mm-release.json"
    write_release_metadata(metadata_file)
    release, manifest = catalog_payloads()
    responses = iter([release, manifest])
    monkeypatch.setattr(
        "backend.services.system_updates.platform.machine", lambda: "aarch64"
    )

    response = check_update_catalog(
        make_settings(metadata_file),
        fetch_json=lambda _url, _timeout: next(responses),
    )

    assert response.status == "update_available"
    assert response.update_available is True
    assert response.latest is not None
    assert response.latest.manifest_validated is True
    assert response.latest.version == "1.2.0"
    assert response.latest.dependencies.apt_packages == ["rsync"]


def test_matching_commit_reports_up_to_date(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metadata_file = tmp_path / ".3mm-release.json"
    write_release_metadata(metadata_file, commit=LATEST_COMMIT)
    release, manifest = catalog_payloads()
    responses = iter([release, manifest])
    monkeypatch.setattr(
        "backend.services.system_updates.platform.machine", lambda: "aarch64"
    )

    response = check_update_catalog(
        make_settings(metadata_file),
        fetch_json=lambda _url, _timeout: next(responses),
    )

    assert response.status == "up_to_date"
    assert response.update_available is False


@pytest.mark.parametrize("installed_version", ["1.2.0", "1.3.0"])
def test_same_or_older_published_version_cannot_be_offered_as_an_update(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    installed_version: str,
) -> None:
    metadata_file = tmp_path / ".3mm-release.json"
    write_release_metadata(metadata_file, version=installed_version)
    release, manifest = catalog_payloads()
    responses = iter([release, manifest])
    monkeypatch.setattr(
        "backend.services.system_updates.platform.machine", lambda: "aarch64"
    )

    response = check_update_catalog(
        make_settings(metadata_file),
        fetch_json=lambda _url, _timeout: next(responses),
    )

    assert response.status == "not_newer"
    assert response.update_available is False


def test_stable_release_is_newer_than_an_installed_prerelease(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metadata_file = tmp_path / ".3mm-release.json"
    write_release_metadata(metadata_file, version="1.2.0-beta.2")
    release, manifest = catalog_payloads()
    responses = iter([release, manifest])
    monkeypatch.setattr(
        "backend.services.system_updates.platform.machine", lambda: "aarch64"
    )

    response = check_update_catalog(
        make_settings(metadata_file),
        fetch_json=lambda _url, _timeout: next(responses),
    )

    assert response.status == "update_available"
    assert response.update_available is True


def test_invalid_installed_version_is_rejected(tmp_path: Path) -> None:
    metadata_file = tmp_path / ".3mm-release.json"
    write_release_metadata(metadata_file, version="latest")

    response = read_local_update_status(make_settings(metadata_file))

    assert response.status == "error"
    assert response.message == "Current release version is invalid"


def test_manifest_is_required_for_a_trusted_update(tmp_path: Path) -> None:
    metadata_file = tmp_path / ".3mm-release.json"
    write_release_metadata(metadata_file)
    release, _manifest = catalog_payloads()
    release["assets"] = []

    response = check_update_catalog(
        make_settings(metadata_file),
        fetch_json=lambda _url, _timeout: release,
    )

    assert response.status == "manifest_missing"
    assert response.latest is not None
    assert response.latest.manifest_validated is False


def test_mismatched_artifact_metadata_is_rejected(tmp_path: Path) -> None:
    metadata_file = tmp_path / ".3mm-release.json"
    write_release_metadata(metadata_file)
    release, manifest = catalog_payloads()
    release["assets"][1]["size"] = 999
    responses = iter([release, manifest])

    response = check_update_catalog(
        make_settings(metadata_file),
        fetch_json=lambda _url, _timeout: next(responses),
    )

    assert response.status == "error"
    assert "size does not match" in response.message
