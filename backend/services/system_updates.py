"""Read-only catalog checks for future immutable 3mm OTA releases."""

from __future__ import annotations

import json
import platform
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, ValidationError

from backend.config import UpdateCatalogSettings

MAX_JSON_BYTES = 1024 * 1024
COMMIT_PATTERN = r"^[0-9a-f]{40}$"
SEMVER_PATTERN = r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
PACKAGE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9+.:~-]*$")
UpdateChannel = Literal["stable", "beta", "test"]


class UpdateCatalogError(RuntimeError):
    """Raised when catalog data cannot be trusted or read safely."""


class UpdateCatalogNotFound(UpdateCatalogError):
    """Raised when GitHub has no matching published resource."""


class UpdateDependencies(BaseModel):
    apt_packages: list[str] = Field(default_factory=list, max_length=100)

    model_config = ConfigDict(extra="forbid")

    def model_post_init(self, __context: object) -> None:
        if len(set(self.apt_packages)) != len(self.apt_packages):
            raise ValueError("APT dependency names must be unique")
        if any(not PACKAGE_PATTERN.fullmatch(item) for item in self.apt_packages):
            raise ValueError("APT dependency name is invalid")


class UpdateArtifact(BaseModel):
    architecture: Literal["aarch64", "armv7l", "x86_64"]
    filename: str = Field(pattern=r"^[A-Za-z0-9._-]+\.tar\.gz$")
    download_url: AnyHttpUrl
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0)

    model_config = ConfigDict(extra="forbid")


class UpdateManifest(BaseModel):
    schema_version: Literal[1]
    version: str = Field(pattern=SEMVER_PATTERN)
    release_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    commit: str = Field(pattern=COMMIT_PATTERN)
    channel: UpdateChannel = "stable"
    artifacts: list[UpdateArtifact] = Field(min_length=1, max_length=10)
    dependencies: UpdateDependencies = Field(default_factory=UpdateDependencies)

    model_config = ConfigDict(extra="forbid")

    def model_post_init(self, __context: object) -> None:
        architectures = [artifact.architecture for artifact in self.artifacts]
        filenames = [artifact.filename for artifact in self.artifacts]
        if len(set(architectures)) != len(architectures):
            raise ValueError("Artifact architectures must be unique")
        if len(set(filenames)) != len(filenames):
            raise ValueError("Artifact filenames must be unique")


class CurrentRelease(BaseModel):
    release_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", max_length=160)
    commit: str | None = None
    branch: str | None = None
    version: str | None = None
    created_at: datetime | None = None
    includes_working_tree: bool | None = None
    metadata_available: bool

    model_config = ConfigDict(extra="forbid")


class LatestRelease(BaseModel):
    tag: str
    name: str
    published_at: datetime | None
    html_url: AnyHttpUrl
    manifest_validated: bool
    version: str | None = None
    release_id: str | None = None
    commit: str | None = None
    channel: UpdateChannel | None = None
    artifacts: list[UpdateArtifact] = Field(default_factory=list)
    dependencies: UpdateDependencies = Field(default_factory=UpdateDependencies)

    model_config = ConfigDict(extra="forbid")


UpdateCheckStatus = Literal[
    "not_checked",
    "no_release",
    "manifest_missing",
    "update_available",
    "up_to_date",
    "not_newer",
    "current_unknown",
    "unsupported_architecture",
    "error",
]


class UpdateCheckResponse(BaseModel):
    status: UpdateCheckStatus
    message: str
    repository: str
    repository_url: AnyHttpUrl
    architecture: str
    current: CurrentRelease
    latest: LatestRelease | None = None
    update_available: bool | None = None
    checked_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")


JsonFetcher = Callable[[str, int], object]


def _fetch_json(url: str, timeout_seconds: int) -> object:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "3mm-update-catalog/1",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read(MAX_JSON_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 404:
            raise UpdateCatalogNotFound(
                "No published GitHub release was found"
            ) from exc
        if exc.code in {403, 429}:
            raise UpdateCatalogError(
                "GitHub update checks are temporarily rate limited"
            ) from exc
        raise UpdateCatalogError("GitHub update catalog request failed") from exc
    except (OSError, TimeoutError, URLError) as exc:
        raise UpdateCatalogError("GitHub update catalog is unavailable") from exc

    if len(payload) > MAX_JSON_BYTES:
        raise UpdateCatalogError("GitHub update catalog response is too large")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateCatalogError("GitHub update catalog returned invalid JSON") from exc


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UpdateCatalogError(f"GitHub release is missing {field}")
    return value.strip()


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise UpdateCatalogError("GitHub release date is invalid")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UpdateCatalogError("GitHub release date is invalid") from exc


def read_current_release(metadata_file: Path) -> CurrentRelease:
    resolved_file = metadata_file.resolve()
    release_id = resolved_file.parent.name or "development"
    if not resolved_file.is_file():
        return CurrentRelease(
            release_id=release_id,
            metadata_available=False,
        )
    try:
        payload = json.loads(resolved_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateCatalogError("Current release metadata is invalid") from exc
    if not isinstance(payload, dict):
        raise UpdateCatalogError("Current release metadata is invalid")

    commit = payload.get("commit")
    if commit is not None and (
        not isinstance(commit, str) or not re.fullmatch(COMMIT_PATTERN, commit)
    ):
        raise UpdateCatalogError("Current release commit is invalid")
    created_at = _optional_datetime(payload.get("created_at"))
    includes_working_tree = payload.get("includes_working_tree")
    if includes_working_tree is not None and not isinstance(
        includes_working_tree, bool
    ):
        raise UpdateCatalogError("Current release metadata is invalid")

    def optional_string(name: str) -> str | None:
        value = payload.get(name)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise UpdateCatalogError("Current release metadata is invalid")
        return value.strip()

    version = optional_string("version")
    if version is not None and not re.fullmatch(SEMVER_PATTERN, version):
        raise UpdateCatalogError("Current release version is invalid")

    return CurrentRelease(
        release_id=optional_string("release_id") or release_id,
        commit=commit,
        branch=optional_string("branch"),
        version=version,
        created_at=created_at,
        includes_working_tree=includes_working_tree,
        metadata_available=True,
    )


def _semver_key(version: str) -> tuple[tuple[int, int, int], tuple[object, ...]]:
    core_text, separator, prerelease_text = version.partition("-")
    core = tuple(int(item) for item in core_text.split("."))
    if not separator:
        return core, (1,)
    prerelease = tuple(
        (0, int(item)) if item.isdigit() else (1, item.lower())
        for item in prerelease_text.split(".")
    )
    return core, (0, prerelease)


def _base_response(
    settings: UpdateCatalogSettings,
    current: CurrentRelease,
    *,
    status: UpdateCheckStatus,
    message: str,
    latest: LatestRelease | None = None,
    update_available: bool | None = None,
    checked_at: datetime | None = None,
) -> UpdateCheckResponse:
    return UpdateCheckResponse(
        status=status,
        message=message,
        repository=settings.repository,
        repository_url=f"https://github.com/{settings.repository}",
        architecture=_current_architecture(),
        current=current,
        latest=latest,
        update_available=update_available,
        checked_at=checked_at,
    )


def read_local_update_status(settings: UpdateCatalogSettings) -> UpdateCheckResponse:
    try:
        current = read_current_release(settings.release_metadata_file)
    except UpdateCatalogError as exc:
        current = CurrentRelease(release_id="unknown", metadata_available=False)
        return _base_response(settings, current, status="error", message=str(exc))
    return _base_response(
        settings,
        current,
        status="not_checked",
        message="The GitHub release catalog has not been checked yet",
    )


def _safe_release_asset_url(url: str, repository: str) -> bool:
    parsed = urlparse(url)
    prefix = f"/{repository}/releases/download/"
    return (
        parsed.scheme == "https"
        and parsed.netloc == "github.com"
        and parsed.path.startswith(prefix)
    )


def _safe_release_page_url(url: str, repository: str) -> bool:
    parsed = urlparse(url)
    prefix = f"/{repository}/releases/tag/"
    return (
        parsed.scheme == "https"
        and parsed.netloc == "github.com"
        and parsed.path.startswith(prefix)
    )


def _current_architecture() -> str:
    architecture = platform.machine().lower()
    return {
        "amd64": "x86_64",
        "arm64": "aarch64",
    }.get(architecture, architecture or "unknown")


def _tag_channel(tag: str) -> UpdateChannel | None:
    version = tag[1:] if tag.startswith("v") else tag
    if not re.fullmatch(SEMVER_PATTERN, version):
        return None
    _core, separator, prerelease = version.partition("-")
    if not separator:
        return "stable"
    return "test" if prerelease.split(".", 1)[0].lower() == "test" else "beta"


def _latest_release_shell(
    payload: dict[str, object],
    repository: str,
    *,
    channel: UpdateChannel,
) -> LatestRelease:
    if payload.get("draft") is True:
        raise UpdateCatalogError("GitHub returned an unpublished release")
    tag = _required_string(payload.get("tag_name"), "tag_name")
    if _tag_channel(tag) != channel:
        raise UpdateCatalogError("Release tag does not match the selected channel")
    is_prerelease = payload.get("prerelease") is True
    if is_prerelease != (channel != "stable"):
        raise UpdateCatalogError("GitHub release state does not match its channel")
    html_url = _required_string(payload.get("html_url"), "html_url")
    if not _safe_release_page_url(html_url, repository):
        raise UpdateCatalogError("Release page URL is outside the selected repository")
    return LatestRelease(
        tag=tag,
        name=_required_string(payload.get("name") or payload.get("tag_name"), "name"),
        published_at=_optional_datetime(payload.get("published_at")),
        html_url=html_url,
        manifest_validated=False,
    )


def check_update_catalog(
    settings: UpdateCatalogSettings,
    *,
    channel: UpdateChannel = "stable",
    fetch_json: JsonFetcher = _fetch_json,
) -> UpdateCheckResponse:
    checked_at = datetime.now(UTC)
    try:
        current = read_current_release(settings.release_metadata_file)
    except UpdateCatalogError as exc:
        current = CurrentRelease(release_id="unknown", metadata_available=False)
        return _base_response(
            settings,
            current,
            status="error",
            message=str(exc),
            checked_at=checked_at,
        )

    release_api_url = f"https://api.github.com/repos/{settings.repository}/releases/latest"
    if channel != "stable":
        release_api_url = (
            f"https://api.github.com/repos/{settings.repository}/releases?per_page=20"
        )
    try:
        release_payload = fetch_json(release_api_url, settings.timeout_seconds)
    except UpdateCatalogNotFound:
        return _base_response(
            settings,
            current,
            status="no_release",
            message="No published GitHub release is available",
            checked_at=checked_at,
        )
    except UpdateCatalogError as exc:
        return _base_response(
            settings,
            current,
            status="error",
            message=str(exc),
            checked_at=checked_at,
        )

    if channel != "stable":
        if not isinstance(release_payload, list):
            return _base_response(
                settings,
                current,
                status="error",
                message="GitHub release response is invalid",
                checked_at=checked_at,
            )
        matching_releases = [
            item
            for item in release_payload
            if isinstance(item, dict)
            and item.get("draft") is not True
            and isinstance(item.get("tag_name"), str)
            and _tag_channel(item["tag_name"]) == channel
        ]
        if not matching_releases:
            return _base_response(
                settings,
                current,
                status="no_release",
                message=f"No published {channel} release is available",
                checked_at=checked_at,
            )
        release_payload = matching_releases[0]

    if not isinstance(release_payload, dict):
        return _base_response(
            settings,
            current,
            status="error",
            message="GitHub release response is invalid",
            checked_at=checked_at,
        )

    try:
        latest = _latest_release_shell(
            release_payload,
            settings.repository,
            channel=channel,
        )
        assets = release_payload.get("assets")
        if not isinstance(assets, list):
            raise UpdateCatalogError("GitHub release assets are invalid")
        named_assets = [
            item
            for item in assets
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        asset_names = [item["name"] for item in named_assets]
        if len(asset_names) != len(set(asset_names)):
            raise UpdateCatalogError("GitHub release contains duplicate asset names")
        assets_by_name = {item["name"]: item for item in named_assets}
        manifest_asset = assets_by_name.get(settings.manifest_asset_name)
        if manifest_asset is None:
            return _base_response(
                settings,
                current,
                status="manifest_missing",
                message="Latest release has no validated 3mm update manifest",
                latest=latest,
                checked_at=checked_at,
            )
        manifest_url = _required_string(
            manifest_asset.get("browser_download_url"), "manifest download URL"
        )
        if not _safe_release_asset_url(manifest_url, settings.repository):
            raise UpdateCatalogError(
                "Update manifest URL is outside the selected repository"
            )
        manifest_payload = fetch_json(manifest_url, settings.timeout_seconds)
        try:
            manifest = UpdateManifest.model_validate(manifest_payload)
        except ValidationError as exc:
            raise UpdateCatalogError("Latest release manifest is invalid") from exc
        if latest.tag not in {manifest.version, f"v{manifest.version}"}:
            raise UpdateCatalogError(
                "Release tag and update manifest version do not match"
            )
        if manifest.channel != channel:
            raise UpdateCatalogError(
                "Release manifest does not match the selected update channel"
            )

        for artifact in manifest.artifacts:
            release_asset = assets_by_name.get(artifact.filename)
            if not isinstance(release_asset, dict):
                raise UpdateCatalogError(
                    "Manifest references a missing release artifact"
                )
            asset_url = _required_string(
                release_asset.get("browser_download_url"), "artifact download URL"
            )
            if not _safe_release_asset_url(asset_url, settings.repository):
                raise UpdateCatalogError(
                    "Release artifact URL is outside the selected repository"
                )
            if str(artifact.download_url) != asset_url:
                raise UpdateCatalogError("Manifest artifact URL does not match GitHub")
            if release_asset.get("size") != artifact.size_bytes:
                raise UpdateCatalogError("Manifest artifact size does not match GitHub")
            digest = release_asset.get("digest")
            if digest is not None and digest != f"sha256:{artifact.sha256}":
                raise UpdateCatalogError(
                    "Manifest artifact digest does not match GitHub"
                )

        latest = LatestRelease(
            tag=latest.tag,
            name=latest.name,
            published_at=latest.published_at,
            html_url=latest.html_url,
            manifest_validated=True,
            version=manifest.version,
            release_id=manifest.release_id,
            commit=manifest.commit,
            channel=manifest.channel,
            artifacts=manifest.artifacts,
            dependencies=manifest.dependencies,
        )
        architecture = _current_architecture()
        if architecture not in {
            artifact.architecture for artifact in manifest.artifacts
        }:
            return _base_response(
                settings,
                current,
                status="unsupported_architecture",
                message="Latest release has no artifact for this architecture",
                latest=latest,
                update_available=None,
                checked_at=checked_at,
            )
        if current.commit is None:
            return _base_response(
                settings,
                current,
                status="current_unknown",
                message="Current commit is unknown; comparison is unavailable",
                latest=latest,
                update_available=None,
                checked_at=checked_at,
            )
        if current.commit == manifest.commit:
            return _base_response(
                settings,
                current,
                status="up_to_date",
                message="The system is up to date",
                latest=latest,
                update_available=False,
                checked_at=checked_at,
            )
        if current.version is not None and _semver_key(manifest.version) <= _semver_key(
            current.version
        ):
            return _base_response(
                settings,
                current,
                status="not_newer",
                message="Published release is not newer than the installed version",
                latest=latest,
                update_available=False,
                checked_at=checked_at,
            )
        return _base_response(
            settings,
            current,
            status="update_available",
            message="A validated update is available",
            latest=latest,
            update_available=True,
            checked_at=checked_at,
        )
    except UpdateCatalogError as exc:
        return _base_response(
            settings,
            current,
            status="error",
            message=str(exc),
            checked_at=checked_at,
        )
