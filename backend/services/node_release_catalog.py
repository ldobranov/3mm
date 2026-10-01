"""Trusted catalog for published ARMv6 3mm Node releases."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Callable, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
)

from backend.config import UpdateCatalogSettings


MAX_JSON_BYTES = 1024 * 1024

TRUSTED_NODE_DOWNLOAD_HOSTS = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
)

SEMVER_PATTERN = (
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$"
)

COMMIT_PATTERN = r"^[0-9a-f]{40}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"

NodeUpdateChannel = Literal[
    "stable",
    "beta",
    "test",
]


class NodeReleaseCatalogError(RuntimeError):
    pass


class NodeReleaseDependencies(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    apt_packages: list[str] = Field(
        default_factory=list,
        max_length=100,
    )


class NodeReleaseArtifact(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    architecture: Literal["armv6l"]
    python: Literal["3.13"]

    filename: str = Field(
        pattern=(
            r"^[A-Za-z0-9._-]+"
            r"\.tar\.gz$"
        )
    )

    sha256: str = Field(
        pattern=SHA256_PATTERN
    )

    size_bytes: int = Field(
        gt=0
    )

    download_url: AnyHttpUrl


class NodeReleaseManifest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    schema_version: Literal[1]
    profile: Literal["node"]

    version: str = Field(
        pattern=SEMVER_PATTERN
    )

    release_id: str = Field(
        pattern=r"^v[A-Za-z0-9._-]+$",
        max_length=80,
    )

    commit: str = Field(
        pattern=COMMIT_PATTERN
    )

    channel: NodeUpdateChannel

    dependencies: NodeReleaseDependencies

    artifacts: list[
        NodeReleaseArtifact
    ] = Field(
        min_length=1,
        max_length=1,
    )


class PublishedNodeRelease(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    tag: str
    manifest: NodeReleaseManifest
    artifact: NodeReleaseArtifact


JsonFetcher = Callable[
    [str, int],
    object,
]


def _safe_release_asset_url(
    url: str,
    repository: str,
) -> bool:
    parsed = urlparse(url)

    return (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and parsed.hostname == "github.com"
        and parsed.path.startswith(
            f"/{repository}/releases/download/"
        )
    )


def _validate_node_download_url(
    url: str,
    repository: str,
    *,
    redirected: bool,
) -> None:
    parsed = urlparse(url)

    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
    ):
        raise NodeReleaseCatalogError(
            "Node archive download URL is not trusted"
        )

    if redirected:
        if parsed.hostname not in TRUSTED_NODE_DOWNLOAD_HOSTS:
            raise NodeReleaseCatalogError(
                "Node archive redirect is not trusted"
            )
        return

    expected_prefix = f"/{repository}/releases/download/"

    if (
        parsed.hostname != "github.com"
        or not parsed.path.startswith(expected_prefix)
    ):
        raise NodeReleaseCatalogError(
            "Node archive download URL is not trusted"
        )
        

def _tag_channel(
    tag: str,
) -> NodeUpdateChannel | None:
    version = (
        tag[1:]
        if tag.startswith("v")
        else tag
    )

    if not re.fullmatch(
        SEMVER_PATTERN,
        version,
    ):
        return None

    _, separator, prerelease = (
        version.partition("-")
    )

    if not separator:
        return "stable"

    prefix = prerelease.split(
        ".",
        1,
    )[0].lower()

    return (
        "test"
        if prefix == "test"
        else "beta"
    )


def _fetch_json(
    url: str,
    timeout_seconds: int,
) -> object:
    request = Request(
        url,
        headers={
            "Accept":
                "application/vnd.github+json",
            "X-GitHub-Api-Version":
                "2022-11-28",
            "User-Agent":
                "3mm-node-update-catalog/1",
        },
    )

    try:
        with urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            payload = response.read(
                MAX_JSON_BYTES + 1
            )

    except HTTPError as exc:
        raise NodeReleaseCatalogError(
            "Published Node release could not be read"
        ) from exc

    except (
        URLError,
        OSError,
        TimeoutError,
    ) as exc:
        raise NodeReleaseCatalogError(
            "Published Node release catalog is unavailable"
        ) from exc

    if len(payload) > MAX_JSON_BYTES:
        raise NodeReleaseCatalogError(
            "Published Node release response is too large"
        )

    try:
        return json.loads(
            payload.decode("utf-8")
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise NodeReleaseCatalogError(
            "Published Node release JSON is invalid"
        ) from exc


def _required_string(
    value: object,
    field: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise NodeReleaseCatalogError(
            f"GitHub release is missing {field}"
        )

    return value.strip()


def find_published_node_release(
    settings: UpdateCatalogSettings,
    *,
    channel: NodeUpdateChannel = "beta",
    fetch_json: JsonFetcher = _fetch_json,
) -> PublishedNodeRelease:
    repository = settings.repository

    if channel == "stable":
        releases_url = (
            f"https://api.github.com/repos/"
            f"{repository}/releases/latest"
        )
    else:
        releases_url = (
            f"https://api.github.com/repos/"
            f"{repository}/releases?per_page=20"
        )

    payload = fetch_json(
        releases_url,
        settings.timeout_seconds,
    )

    if channel == "stable":
        candidates = (
            [payload]
            if isinstance(payload, dict)
            else []
        )
    else:
        candidates = (
            payload
            if isinstance(payload, list)
            else []
        )

    release = next(
        (
            item
            for item in candidates
            if isinstance(item, dict)
            and item.get("draft") is not True
            and isinstance(
                item.get("tag_name"),
                str,
            )
            and _tag_channel(
                item["tag_name"]
            )
            == channel
        ),
        None,
    )

    if release is None:
        raise NodeReleaseCatalogError(
            f"No published {channel} Node release is available"
        )

    tag = _required_string(
        release.get("tag_name"),
        "tag_name",
    )

    expected_prerelease = (
        channel != "stable"
    )

    if (
        release.get("prerelease") is True
    ) != expected_prerelease:
        raise NodeReleaseCatalogError(
            "GitHub release prerelease state is invalid"
        )

    assets = release.get("assets")

    if not isinstance(
        assets,
        list,
    ):
        raise NodeReleaseCatalogError(
            "GitHub release assets are invalid"
        )

    named_assets = {
        item["name"]: item
        for item in assets
        if isinstance(item, dict)
        and isinstance(
            item.get("name"),
            str,
        )
    }

    if len(named_assets) != len(
        [
            item
            for item in assets
            if isinstance(item, dict)
            and isinstance(
                item.get("name"),
                str,
            )
        ]
    ):
        raise NodeReleaseCatalogError(
            "GitHub release contains duplicate asset names"
        )

    manifest_asset = named_assets.get(
        "3mm-node-manifest.json"
    )

    if manifest_asset is None:
        raise NodeReleaseCatalogError(
            "Published release has no Node manifest"
        )

    manifest_url = _required_string(
        manifest_asset.get(
            "browser_download_url"
        ),
        "Node manifest URL",
    )

    if not _safe_release_asset_url(
        manifest_url,
        repository,
    ):
        raise NodeReleaseCatalogError(
            "Node manifest URL is outside the selected repository"
        )

    manifest_payload = fetch_json(
        manifest_url,
        settings.timeout_seconds,
    )

    try:
        manifest = (
            NodeReleaseManifest.model_validate(
                manifest_payload
            )
        )
    except ValidationError as exc:
        raise NodeReleaseCatalogError(
            "Published Node manifest is invalid"
        ) from exc

    if manifest.release_id != tag:
        raise NodeReleaseCatalogError(
            "Node manifest release identity does not match GitHub"
        )

    if tag != f"v{manifest.version}":
        raise NodeReleaseCatalogError(
            "Node manifest version does not match GitHub"
        )

    if manifest.channel != channel:
        raise NodeReleaseCatalogError(
            "Node manifest channel does not match the request"
        )

    artifact = manifest.artifacts[0]

    release_asset = named_assets.get(
        artifact.filename
    )

    if not isinstance(
        release_asset,
        dict,
    ):
        raise NodeReleaseCatalogError(
            "Node manifest references a missing archive"
        )

    release_url = _required_string(
        release_asset.get(
            "browser_download_url"
        ),
        "Node archive URL",
    )

    if not _safe_release_asset_url(
        release_url,
        repository,
    ):
        raise NodeReleaseCatalogError(
            "Node archive URL is outside the selected repository"
        )

    if (
        str(artifact.download_url)
        != release_url
    ):
        raise NodeReleaseCatalogError(
            "Node archive URL differs from GitHub"
        )

    if (
        release_asset.get("size")
        != artifact.size_bytes
    ):
        raise NodeReleaseCatalogError(
            "Node archive size differs from GitHub"
        )

    digest = release_asset.get(
        "digest"
    )

    if (
        digest is not None
        and digest
        != f"sha256:{artifact.sha256}"
    ):
        raise NodeReleaseCatalogError(
            "Node archive digest differs from GitHub"
        )

    if (
        artifact.size_bytes
        > settings.max_artifact_bytes
    ):
        raise NodeReleaseCatalogError(
            "Node archive exceeds the configured size limit"
        )

    return PublishedNodeRelease(
        tag=tag,
        manifest=manifest,
        artifact=artifact,
    )
    
    
def download_published_node_archive(
    release: PublishedNodeRelease,
    destination: Path,
    settings: UpdateCatalogSettings,
    *,
    opener=urlopen,
) -> Path:
    """Download one validated official Node release artifact."""

    artifact = release.artifact
    url = str(artifact.download_url)

    _validate_node_download_url(
        url,
        settings.repository,
        redirected=False,
    )

    if artifact.size_bytes > settings.max_artifact_bytes:
        raise NodeReleaseCatalogError(
            "Node archive exceeds the configured size limit"
        )

    destination = Path(destination)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = (
        destination.parent
        / (
            "."
            + destination.name
            + "."
            + os.urandom(8).hex()
            + ".download"
        )
    )

    checksum = hashlib.sha256()
    received = 0

    request = Request(
        url,
        headers={
            "User-Agent": "3mm-node-update-staging/1",
        },
    )

    try:
        with opener(
            request,
            timeout=settings.timeout_seconds,
        ) as response:
            _validate_node_download_url(
                response.geturl(),
                settings.repository,
                redirected=True,
            )

            content_length = response.headers.get(
                "Content-Length"
            )

            if content_length is not None:
                try:
                    declared_size = int(content_length)
                except ValueError as exc:
                    raise NodeReleaseCatalogError(
                        "Node archive Content-Length is invalid"
                    ) from exc

                if declared_size != artifact.size_bytes:
                    raise NodeReleaseCatalogError(
                        "Node archive size changed during download"
                    )

            with temporary.open("xb") as output:
                if os.name == "posix":
                    os.chmod(
                        temporary,
                        0o600,
                    )

                while True:
                    chunk = response.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    received += len(chunk)

                    if received > artifact.size_bytes:
                        raise NodeReleaseCatalogError(
                            "Node archive exceeded its declared size"
                        )

                    if received > settings.max_artifact_bytes:
                        raise NodeReleaseCatalogError(
                            "Node archive exceeded the configured size limit"
                        )

                    checksum.update(chunk)
                    output.write(chunk)

                output.flush()
                os.fsync(
                    output.fileno()
                )

    except NodeReleaseCatalogError:
        temporary.unlink(
            missing_ok=True
        )
        raise

    except (
        HTTPError,
        URLError,
        OSError,
        TimeoutError,
    ) as exc:
        temporary.unlink(
            missing_ok=True
        )

        raise NodeReleaseCatalogError(
            "Node archive download failed"
        ) from exc

    if received != artifact.size_bytes:
        temporary.unlink(
            missing_ok=True
        )

        raise NodeReleaseCatalogError(
            "Node archive size does not match the manifest"
        )

    if checksum.hexdigest() != artifact.sha256:
        temporary.unlink(
            missing_ok=True
        )

        raise NodeReleaseCatalogError(
            "Node archive checksum does not match the manifest"
        )

    os.replace(
        temporary,
        destination,
    )

    return destination