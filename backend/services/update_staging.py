"""Verified, bounded staging for immutable 3mm system updates."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import shutil
import sqlite3
import subprocess
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Callable, Literal, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.config import BackendSettings, FrontendSettings, UpdateCatalogSettings
from backend.services.system_updates import (
    PACKAGE_PATTERN,
    SEMVER_PATTERN,
    SHA256_PATTERN,
    UpdateArtifact,
    UpdateChannel,
    check_update_catalog,
)

MAX_ARCHIVE_MEMBERS = 20_000
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024
TRUSTED_DOWNLOAD_HOSTS = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
)
REQUIRED_RELEASE_FILES = frozenset(
    {
        ".3mm-release.json",
        "backend/requirements.txt",
        "backend/services/update_staging.py",
        "deployment/apply_staged_update.py",
        "deployment/install-systemd.sh",
        "deployment/migrate_database.py",
        "deployment/release-dependencies.json",
        "deployment/systemd/3mm-agent.service",
        "deployment/systemd/3mm-core.service",
        "deployment/systemd/3mm-update-helper.service",
        "deployment/systemd/3mm-web.service",
        "deployment/update-dependency-allowlist.json",
        "frontend/dist/index.html",
        "three_mm_runtime/update_helper.py",
    }
)


class UpdateStagingError(RuntimeError):
    """Raised when an update cannot be safely staged or approved."""


class DependencyPlanItem(BaseModel):
    name: str
    installed: bool
    action: Literal["keep", "install"]

    model_config = ConfigDict(extra="forbid")


class PreflightCheck(BaseModel):
    name: str
    passed: bool
    detail: str

    model_config = ConfigDict(extra="forbid")


class StagedUpdate(BaseModel):
    schema_version: Literal[1] = 1
    release_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", max_length=160)
    version: str = Field(pattern=SEMVER_PATTERN)
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    channel: UpdateChannel = "stable"
    architecture: Literal["aarch64", "armv7l", "x86_64"]
    artifact_filename: str = Field(pattern=r"^[A-Za-z0-9._-]+\.tar\.gz$")
    artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    artifact_size_bytes: int = Field(gt=0)
    dependencies: list[str] = Field(default_factory=list, max_length=100)
    dependency_plan: list[DependencyPlanItem] = Field(default_factory=list)
    frontend_origin: str = Field(pattern=r"^https?://[A-Za-z0-9.-]+(?::\d{1,5})?$")
    staged_at: datetime
    approval_expires_at: datetime
    approval_nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    preflight: list[PreflightCheck]

    model_config = ConfigDict(extra="forbid")


class StagedUpdateResponse(BaseModel):
    status: Literal["ready"] = "ready"
    message: str = "The update is downloaded, verified and ready for approval"
    staged: StagedUpdate

    model_config = ConfigDict(extra="forbid")


class UpdateApplyRequest(BaseModel):
    release_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", max_length=160)
    approval_nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmation: str = Field(min_length=1, max_length=200)
    maintenance_override: bool = False

    model_config = ConfigDict(extra="forbid")


OperationState = Literal["idle", "ready", "queued", "applying", "succeeded", "failed"]


class UpdateOperationStatus(BaseModel):
    schema_version: Literal[1] = 1
    state: OperationState
    message: str
    release_id: str | None = None
    version: str | None = None
    commit: str | None = None
    requested_by_user_id: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None

    model_config = ConfigDict(extra="forbid")


CatalogChecker = Callable[..., object]
ArtifactDownloader = Callable[[UpdateArtifact, Path, UpdateCatalogSettings], None]
DependencyInspector = Callable[[Sequence[str]], dict[str, bool]]
DiskUsageReader = Callable[[Path], shutil._ntuple_diskusage]
ApplyScheduler = Callable[[str, str, int], None]


def _current_architecture() -> str:
    architecture = platform.machine().lower()
    return {"amd64": "x86_64", "arm64": "aarch64"}.get(
        architecture, architecture or "unknown"
    )


def _safe_archive_path(name: str) -> str:
    normalized = name.rstrip("/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or name.startswith("/")
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise UpdateStagingError(f"Release archive contains an unsafe path: {name}")
    return path.as_posix()


def _atomic_json_write(
    path: Path,
    payload: BaseModel | dict[str, object],
    *,
    mode: int = 0o600,
    owner: tuple[int, int] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    data = (
        payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    )
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(data, output, ensure_ascii=False, sort_keys=True, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        if owner is not None:
            os.chown(temporary, *owner)
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise UpdateStagingError("Update staging state could not be written") from exc


def read_dependency_allowlist(path: Path) -> frozenset[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateStagingError("Update dependency allowlist is unavailable") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "apt_packages",
    }:
        raise UpdateStagingError("Update dependency allowlist is invalid")
    packages = payload.get("apt_packages")
    if (
        payload.get("schema_version") != 1
        or not isinstance(packages, list)
        or len(packages) > 100
        or any(not isinstance(item, str) for item in packages)
        or len(packages) != len(set(packages))
        or packages != sorted(packages)
        or any(not PACKAGE_PATTERN.fullmatch(item) for item in packages)
    ):
        raise UpdateStagingError("Update dependency allowlist is invalid")
    return frozenset(packages)


def inspect_installed_dependencies(packages: Sequence[str]) -> dict[str, bool]:
    installed: dict[str, bool] = {}
    for package in packages:
        try:
            result = subprocess.run(
                ("/usr/bin/dpkg-query", "-W", "-f=${db:Status-Abbrev}", package),
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
                env={**os.environ, "LC_ALL": "C"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UpdateStagingError(
                "Installed dependency state could not be inspected"
            ) from exc
        installed[package] = result.returncode == 0 and result.stdout.startswith("ii ")
    return installed


def _validate_download_url(url: str, repository: str, *, redirected: bool) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise UpdateStagingError("Update artifact download URL is not trusted")
    if redirected:
        if parsed.hostname not in TRUSTED_DOWNLOAD_HOSTS:
            raise UpdateStagingError("Update artifact redirect is not trusted")
        return
    expected_prefix = f"/{repository}/releases/download/"
    if parsed.hostname != "github.com" or not parsed.path.startswith(expected_prefix):
        raise UpdateStagingError("Update artifact download URL is not trusted")


def download_artifact(
    artifact: UpdateArtifact,
    destination: Path,
    settings: UpdateCatalogSettings,
) -> None:
    url = str(artifact.download_url)
    _validate_download_url(url, settings.repository, redirected=False)
    if artifact.size_bytes > settings.max_artifact_bytes:
        raise UpdateStagingError("Update artifact exceeds the configured size limit")

    request = Request(url, headers={"User-Agent": "3mm-update-staging/1"})
    temporary = destination.with_suffix(destination.suffix + ".download")
    temporary.unlink(missing_ok=True)
    digest = hashlib.sha256()
    received = 0
    try:
        with urlopen(request, timeout=settings.timeout_seconds) as response:
            _validate_download_url(
                response.geturl(), settings.repository, redirected=True
            )
            content_length = response.headers.get("Content-Length")
            if (
                content_length is not None
                and int(content_length) != artifact.size_bytes
            ):
                raise UpdateStagingError("Update artifact size changed during download")
            with temporary.open("xb") as output:
                os.chmod(temporary, 0o600)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > artifact.size_bytes:
                        raise UpdateStagingError(
                            "Update artifact exceeded its declared size"
                        )
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
    except UpdateStagingError:
        temporary.unlink(missing_ok=True)
        raise
    except (HTTPError, URLError, OSError, TimeoutError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise UpdateStagingError("Update artifact download failed") from exc

    if received != artifact.size_bytes:
        temporary.unlink(missing_ok=True)
        raise UpdateStagingError("Update artifact size does not match the manifest")
    if digest.hexdigest() != artifact.sha256:
        temporary.unlink(missing_ok=True)
        raise UpdateStagingError("Update artifact checksum does not match the manifest")
    os.replace(temporary, destination)


def verify_release_archive(
    archive_path: Path,
    *,
    release_id: str,
    version: str,
    commit: str,
    architecture: str,
    dependencies: Sequence[str] | None = None,
) -> None:
    names: set[str] = set()
    total_size = 0
    metadata: object | None = None
    archive_dependencies: object | None = None
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise UpdateStagingError("Update archive contains too many entries")
            for member in members:
                name = _safe_archive_path(member.name)
                if name in names:
                    raise UpdateStagingError(
                        f"Update archive contains a duplicate path: {name}"
                    )
                names.add(name)
                if member.isdir():
                    continue
                if not member.isfile():
                    raise UpdateStagingError(
                        f"Update archive contains an unsupported entry: {name}"
                    )
                total_size += member.size
                if total_size > MAX_EXPANDED_BYTES:
                    raise UpdateStagingError("Expanded update archive is too large")
                if name == ".3mm-release.json":
                    if member.size > MAX_METADATA_BYTES:
                        raise UpdateStagingError("Release metadata is too large")
                    source = archive.extractfile(member)
                    if source is None:
                        raise UpdateStagingError("Release metadata could not be read")
                    metadata = json.loads(source.read().decode("utf-8"))
                elif name == "deployment/release-dependencies.json":
                    if member.size > MAX_METADATA_BYTES:
                        raise UpdateStagingError(
                            "Release dependency declaration is too large"
                        )
                    source = archive.extractfile(member)
                    if source is None:
                        raise UpdateStagingError(
                            "Release dependency declaration could not be read"
                        )
                    archive_dependencies = json.loads(source.read().decode("utf-8"))
    except UpdateStagingError:
        raise
    except (OSError, tarfile.TarError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateStagingError("Update archive is invalid") from exc

    missing = sorted(REQUIRED_RELEASE_FILES - names)
    if missing:
        raise UpdateStagingError(f"Update archive is incomplete: {', '.join(missing)}")
    if not isinstance(metadata, dict) or metadata != {
        "architecture": architecture,
        "branch": "main",
        "commit": commit,
        "created_at": (
            metadata.get("created_at") if isinstance(metadata, dict) else None
        ),
        "includes_working_tree": False,
        "release_id": release_id,
        "version": version,
    }:
        raise UpdateStagingError(
            "Embedded release identity does not match the manifest"
        )
    created_at = metadata.get("created_at")
    if not isinstance(created_at, str):
        raise UpdateStagingError("Embedded release timestamp is invalid")
    try:
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UpdateStagingError("Embedded release timestamp is invalid") from exc
    if not isinstance(archive_dependencies, dict) or set(archive_dependencies) != {
        "schema_version",
        "apt_packages",
    }:
        raise UpdateStagingError("Embedded release dependencies are invalid")
    embedded_packages = archive_dependencies.get("apt_packages")
    if (
        archive_dependencies.get("schema_version") != 1
        or not isinstance(embedded_packages, list)
        or any(not isinstance(item, str) for item in embedded_packages)
        or embedded_packages != sorted(set(embedded_packages))
        or any(not PACKAGE_PATTERN.fullmatch(item) for item in embedded_packages)
    ):
        raise UpdateStagingError("Embedded release dependencies are invalid")
    if dependencies is not None and embedded_packages != list(dependencies):
        raise UpdateStagingError(
            "Embedded release dependencies do not match the trusted manifest"
        )


def inspect_database(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise UpdateStagingError("OTA preflight currently supports SQLite only")
    database_path = Path(database_url.removeprefix(prefix))
    if not database_path.exists():
        return "A new SQLite database will be initialized"
    try:
        connection = sqlite3.connect(
            f"file:{database_path.as_posix()}?mode=ro", uri=True
        )
        try:
            result = connection.execute("PRAGMA quick_check").fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise UpdateStagingError(
            "The current SQLite database failed preflight"
        ) from exc
    if result != ("ok",):
        raise UpdateStagingError("The current SQLite database failed preflight")
    return f"SQLite quick check passed; backup requires {database_path.stat().st_size} bytes"


def _stage_record_path(settings: UpdateCatalogSettings) -> Path:
    return settings.staging_dir / "stage.json"


def _stage_archive_path(settings: UpdateCatalogSettings) -> Path:
    return settings.staging_dir / "staged-release.tar.gz"


def read_staged_update(settings: UpdateCatalogSettings) -> StagedUpdate | None:
    path = _stage_record_path(settings)
    if not path.is_file():
        return None
    try:
        return StagedUpdate.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        raise UpdateStagingError("Staged update state is invalid") from exc


def validate_staged_payload(
    staging_dir: Path,
    dependency_allowlist_file: Path,
    *,
    release_id: str,
    approval_nonce: str,
    expected_owner_uid: int | None = None,
) -> StagedUpdate:
    record_path = staging_dir / "stage.json"
    archive_path = staging_dir / "staged-release.tar.gz"
    try:
        resolved_root = staging_dir.resolve(strict=True)
        resolved_record = record_path.resolve(strict=True)
        resolved_archive = archive_path.resolve(strict=True)
    except OSError as exc:
        raise UpdateStagingError("Staged update files are unavailable") from exc
    if (
        resolved_record.parent != resolved_root
        or resolved_archive.parent != resolved_root
        or record_path.is_symlink()
        or archive_path.is_symlink()
        or not record_path.is_file()
        or not archive_path.is_file()
    ):
        raise UpdateStagingError("Staged update paths are unsafe")
    if expected_owner_uid is not None and (
        record_path.stat().st_uid != expected_owner_uid
        or archive_path.stat().st_uid != expected_owner_uid
    ):
        raise UpdateStagingError("Staged update ownership is invalid")

    try:
        staged = StagedUpdate.model_validate_json(record_path.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        raise UpdateStagingError("Staged update state is invalid") from exc
    if staged.release_id != release_id or not secrets.compare_digest(
        staged.approval_nonce, approval_nonce
    ):
        raise UpdateStagingError("Staged update approval does not match")
    if staged.approval_expires_at < datetime.now(UTC):
        raise UpdateStagingError("Staged update approval has expired")
    if archive_path.stat().st_size != staged.artifact_size_bytes:
        raise UpdateStagingError("Staged update size changed after verification")
    digest_builder = hashlib.sha256()
    try:
        with archive_path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest_builder.update(chunk)
    except OSError as exc:
        raise UpdateStagingError(
            "Staged update checksum could not be verified"
        ) from exc
    digest = digest_builder.hexdigest()
    if not secrets.compare_digest(digest, staged.artifact_sha256):
        raise UpdateStagingError("Staged update checksum changed after verification")
    verify_release_archive(
        archive_path,
        release_id=staged.release_id,
        version=staged.version,
        commit=staged.commit,
        architecture=staged.architecture,
        dependencies=staged.dependencies,
    )
    allowlist = read_dependency_allowlist(dependency_allowlist_file)
    unapproved = sorted(set(staged.dependencies) - allowlist)
    if unapproved:
        raise UpdateStagingError(
            "Staged dependencies are outside the installed allowlist"
        )
    return staged


def stage_latest_update(
    settings: UpdateCatalogSettings,
    backend: BackendSettings,
    frontend: FrontendSettings,
    *,
    channel: UpdateChannel = "stable",
    catalog_checker: CatalogChecker = check_update_catalog,
    downloader: ArtifactDownloader = download_artifact,
    dependency_inspector: DependencyInspector = inspect_installed_dependencies,
    disk_usage_reader: DiskUsageReader = shutil.disk_usage,
) -> StagedUpdateResponse:
    current_operation = read_operation_status(settings)
    if current_operation.state in {"queued", "applying"}:
        raise UpdateStagingError("An update operation is already running")
    catalog = catalog_checker(settings, channel=channel)
    latest = getattr(catalog, "latest", None)
    if latest is None or not latest.manifest_validated:
        raise UpdateStagingError("No validated release is available for staging")
    if latest.channel != channel:
        raise UpdateStagingError("The release does not match the selected channel")
    catalog_status = getattr(catalog, "status", None)
    if catalog_status != "update_available":
        if catalog_status == "up_to_date":
            raise UpdateStagingError("The latest release is already installed")
        if catalog_status == "not_newer":
            raise UpdateStagingError(
                "The published release is not newer than the installed version"
            )
        raise UpdateStagingError("The release is not eligible for installation")
    architecture = _current_architecture()
    artifact = next(
        (item for item in latest.artifacts if item.architecture == architecture), None
    )
    if artifact is None:
        raise UpdateStagingError("No release artifact supports this architecture")

    allowlist = read_dependency_allowlist(settings.dependency_allowlist_file)
    requested_packages = latest.dependencies.apt_packages
    unapproved = sorted(set(requested_packages) - allowlist)
    if unapproved:
        raise UpdateStagingError(
            f"Release requests dependencies outside the allowlist: {', '.join(unapproved)}"
        )
    installed = dependency_inspector(requested_packages)
    if set(installed) != set(requested_packages):
        raise UpdateStagingError("Installed dependency inspection was incomplete")
    dependency_plan = [
        DependencyPlanItem(
            name=package,
            installed=installed[package],
            action="keep" if installed[package] else "install",
        )
        for package in requested_packages
    ]

    settings.staging_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(settings.staging_dir, 0o700)
    database_detail = inspect_database(backend.database_url)
    free_bytes = disk_usage_reader(settings.staging_dir).free
    database_path = Path(backend.database_url.removeprefix("sqlite:///"))
    database_bytes = database_path.stat().st_size if database_path.is_file() else 0
    required_bytes = max(
        settings.minimum_free_bytes,
        artifact.size_bytes * 4 + database_bytes * 2,
    )
    if free_bytes < required_bytes:
        raise UpdateStagingError(
            "Insufficient free space to stage and roll back update"
        )

    archive_path = _stage_archive_path(settings)
    candidate_path = settings.staging_dir / "candidate-release.tar.gz"
    candidate_path.unlink(missing_ok=True)
    downloader(artifact, candidate_path, settings)
    try:
        verify_release_archive(
            candidate_path,
            release_id=latest.release_id,
            version=latest.version,
            commit=latest.commit,
            architecture=architecture,
            dependencies=requested_packages,
        )
    except Exception:
        candidate_path.unlink(missing_ok=True)
        raise
    os.replace(candidate_path, archive_path)

    now = datetime.now(UTC)
    staged = StagedUpdate(
        release_id=latest.release_id,
        version=latest.version,
        commit=latest.commit,
        channel=channel,
        architecture=architecture,
        artifact_filename=artifact.filename,
        artifact_sha256=artifact.sha256,
        artifact_size_bytes=artifact.size_bytes,
        dependencies=requested_packages,
        dependency_plan=dependency_plan,
        frontend_origin=frontend.frontend_url,
        staged_at=now,
        approval_expires_at=now + timedelta(seconds=settings.approval_ttl_seconds),
        approval_nonce=secrets.token_hex(32),
        preflight=[
            PreflightCheck(
                name="archive.identity",
                passed=True,
                detail="SHA-256, size, structure and release identity verified",
            ),
            PreflightCheck(
                name="storage.free",
                passed=True,
                detail=f"{free_bytes} bytes free; {required_bytes} bytes required",
            ),
            PreflightCheck(
                name="database.backup",
                passed=True,
                detail=database_detail,
            ),
            PreflightCheck(
                name="migration.entrypoint",
                passed=True,
                detail="Migration entrypoint is present; installer rollback remains authoritative",
            ),
            PreflightCheck(
                name="dependencies.allowlist",
                passed=True,
                detail="Every declared APT package is allowlisted by the installed release",
            ),
        ],
    )
    _atomic_json_write(_stage_record_path(settings), staged)
    return StagedUpdateResponse(staged=staged)


def revalidate_official_release(
    staged: StagedUpdate,
    *,
    repository: str,
    manifest_asset_name: str,
    release_metadata_file: Path = Path("/opt/3mm/current/.3mm-release.json"),
    catalog_checker: CatalogChecker = check_update_catalog,
) -> None:
    trusted_settings = UpdateCatalogSettings(
        repository=repository,
        manifest_asset_name=manifest_asset_name,
        release_metadata_file=release_metadata_file,
    )
    catalog = catalog_checker(trusted_settings, channel=staged.channel)
    if getattr(catalog, "status", None) != "update_available":
        raise UpdateStagingError(
            "Official release is not eligible for installation on this device"
        )
    latest = getattr(catalog, "latest", None)
    if latest is None or not latest.manifest_validated:
        raise UpdateStagingError("Official release manifest could not be revalidated")
    artifact = next(
        (item for item in latest.artifacts if item.architecture == staged.architecture),
        None,
    )
    if (
        latest.release_id != staged.release_id
        or latest.version != staged.version
        or latest.commit != staged.commit
        or latest.channel != staged.channel
        or artifact is None
        or artifact.filename != staged.artifact_filename
        or artifact.sha256 != staged.artifact_sha256
        or artifact.size_bytes != staged.artifact_size_bytes
        or latest.dependencies.apt_packages != staged.dependencies
    ):
        raise UpdateStagingError(
            "Staged update no longer matches the official selected-channel release"
        )


def write_operation_status(
    path: Path,
    status: UpdateOperationStatus,
    *,
    owner: tuple[int, int] | None = None,
) -> None:
    _atomic_json_write(path, status, mode=0o640 if owner else 0o600, owner=owner)


def read_operation_status(settings: UpdateCatalogSettings) -> UpdateOperationStatus:
    path = settings.helper_status_file
    if path.is_file():
        try:
            return UpdateOperationStatus.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, ValidationError) as exc:
            raise UpdateStagingError("Update operation status is invalid") from exc
    staged = read_staged_update(settings)
    if staged is None:
        return UpdateOperationStatus(state="idle", message="No update is staged")
    if staged.approval_expires_at < datetime.now(UTC):
        return UpdateOperationStatus(
            state="failed",
            message="The staged update approval has expired",
            release_id=staged.release_id,
            version=staged.version,
            commit=staged.commit,
            error_code="approval_expired",
        )
    return UpdateOperationStatus(
        state="ready",
        message="The verified update is ready for administrator approval",
        release_id=staged.release_id,
        version=staged.version,
        commit=staged.commit,
    )


def approve_staged_update(
    settings: UpdateCatalogSettings,
    request: UpdateApplyRequest,
    *,
    requested_by_user_id: int,
    scheduler: ApplyScheduler,
) -> UpdateOperationStatus:
    staged = read_staged_update(settings)
    if staged is None:
        raise UpdateStagingError("No verified update is staged")
    if staged.approval_expires_at < datetime.now(UTC):
        raise UpdateStagingError("The staged update approval has expired")
    if request.release_id != staged.release_id:
        raise UpdateStagingError("The staged release changed; review it again")
    if not secrets.compare_digest(request.approval_nonce, staged.approval_nonce):
        raise UpdateStagingError("The staged approval is no longer valid")
    if request.confirmation != f"INSTALL {staged.version}":
        raise UpdateStagingError("Explicit version confirmation is required")
    current = read_operation_status(settings)
    if current.state in {"queued", "applying"}:
        raise UpdateStagingError("An update operation is already running")
    scheduler(staged.release_id, staged.approval_nonce, requested_by_user_id)
    return UpdateOperationStatus(
        state="queued",
        message="The verified update was accepted and queued",
        release_id=staged.release_id,
        version=staged.version,
        commit=staged.commit,
        requested_by_user_id=requested_by_user_id,
        started_at=datetime.now(UTC),
    )
