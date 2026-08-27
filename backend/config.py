"""Portable, typed application configuration.

Tracked configuration contains only safe development defaults. Deployments can
override every machine-specific value through environment variables.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "backend" / "data" / "3mm.db"
DEFAULT_UPLOADS_PATH = PROJECT_ROOT / "uploads"


class FrontendSettings(BaseModel):
    backend_url: str = "http://localhost:8887"
    frontend_url: str = "http://localhost:5173"


class BackendSettings(BaseModel):
    database_url: str = f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
    uploads_dir: Path = DEFAULT_UPLOADS_PATH
    host: str = "0.0.0.0"
    port: int = Field(default=8887, ge=1, le=65535)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    device_offline_after_seconds: int = Field(default=90, ge=5, le=3600)


class UpdateCatalogSettings(BaseModel):
    repository: str = Field(
        default="ldobranov/3mm",
        pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
    )
    manifest_asset_name: str = Field(
        default="3mm-update-manifest.json",
        pattern=r"^[A-Za-z0-9._-]+\.json$",
    )
    release_metadata_file: Path = PROJECT_ROOT / ".3mm-release.json"
    staging_dir: Path = PROJECT_ROOT / ".runtime" / "update-staging"
    dependency_allowlist_file: Path = (
        PROJECT_ROOT / "deployment" / "update-dependency-allowlist.json"
    )
    helper_socket: Path = Path("/run/3mm/update-helper.sock")
    helper_status_file: Path = PROJECT_ROOT / ".runtime" / "update-status.json"
    policy_file: Path = PROJECT_ROOT / ".runtime" / "update-policy.json"
    check_cache_file: Path = PROJECT_ROOT / ".runtime" / "update-check-cache.json"
    timeout_seconds: int = Field(default=8, ge=1, le=30)
    approval_ttl_seconds: int = Field(default=1800, ge=300, le=86400)
    max_artifact_bytes: int = Field(
        default=512 * 1024 * 1024,
        ge=1024 * 1024,
        le=2 * 1024 * 1024 * 1024,
    )
    minimum_free_bytes: int = Field(
        default=512 * 1024 * 1024,
        ge=64 * 1024 * 1024,
    )


class NetworkRecoverySettings(BaseModel):
    policy_file: Path = PROJECT_ROOT / ".runtime" / "network-recovery-policy.json"
    marker_file: Path = PROJECT_ROOT / ".runtime" / "network-recovery.json"
    helper_socket: Path = Path("/run/3mm/update-helper.sock")
    machine_id_file: Path = Path("/etc/machine-id")
    offline_after_seconds: int = Field(default=300, ge=60, le=3600)
    setup_url: str = "http://10.42.0.1:8895/setup"


class AppSettings(BaseModel):
    frontend: FrontendSettings = Field(default_factory=FrontendSettings)
    backend: BackendSettings = Field(default_factory=BackendSettings)
    updates: UpdateCatalogSettings = Field(default_factory=UpdateCatalogSettings)
    network_recovery: NetworkRecoverySettings = Field(
        default_factory=NetworkRecoverySettings
    )

    @property
    def database_url(self) -> str:
        return self.backend.database_url


def _load_json_config(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as config_file:
        loaded = json.load(config_file)
    if not isinstance(loaded, dict):
        raise ValueError(f"Configuration root must be an object: {path}")
    return loaded


def _normalize_database_url(database_url: str) -> str:
    """Resolve tracked relative SQLite paths against the project root."""

    relative_prefix = "sqlite:///"
    if not database_url.startswith(relative_prefix):
        return database_url

    database_path = database_url[len(relative_prefix) :]
    if database_path == ":memory:" or Path(database_path).is_absolute():
        return database_url

    resolved = (PROJECT_ROOT / database_path).resolve()
    return f"sqlite:///{resolved.as_posix()}"


def _parse_cors_origins(value: str) -> list[str]:
    stripped = value.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        parsed = json.loads(stripped)
        if not isinstance(parsed, list) or not all(
            isinstance(origin, str) for origin in parsed
        ):
            raise ValueError("CORS_ORIGINS must be a JSON string array")
        return parsed
    return [origin.strip() for origin in stripped.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    config_path = Path(os.getenv("APP_CONFIG_FILE", DEFAULT_CONFIG_PATH))
    data = _load_json_config(config_path)

    frontend = dict(data.get("frontend") or {})
    backend = dict(data.get("backend") or {})
    updates = dict(data.get("updates") or {})
    network_recovery = dict(data.get("network_recovery") or {})

    if database_url := os.getenv("DATABASE_URL"):
        backend["database_url"] = database_url
    if uploads_dir := os.getenv("UPLOADS_DIR"):
        backend["uploads_dir"] = uploads_dir
    if backend_host := os.getenv("BACKEND_HOST"):
        backend["host"] = backend_host
    if backend_port := os.getenv("BACKEND_PORT"):
        backend["port"] = int(backend_port)
    if cors_origins := os.getenv("CORS_ORIGINS"):
        backend["cors_origins"] = _parse_cors_origins(cors_origins)
    if offline_after := os.getenv("DEVICE_OFFLINE_AFTER_SECONDS"):
        backend["device_offline_after_seconds"] = int(offline_after)
    if frontend_backend_url := os.getenv("FRONTEND_BACKEND_URL"):
        frontend["backend_url"] = frontend_backend_url
    if frontend_url := os.getenv("FRONTEND_URL"):
        frontend["frontend_url"] = frontend_url
    if update_repository := os.getenv("THREE_MM_UPDATE_REPOSITORY"):
        updates["repository"] = update_repository
    if update_manifest := os.getenv("THREE_MM_UPDATE_MANIFEST_ASSET"):
        updates["manifest_asset_name"] = update_manifest
    if release_metadata := os.getenv("THREE_MM_RELEASE_METADATA_FILE"):
        updates["release_metadata_file"] = release_metadata
    if staging_dir := os.getenv("THREE_MM_UPDATE_STAGING_DIR"):
        updates["staging_dir"] = staging_dir
    if dependency_allowlist := os.getenv("THREE_MM_UPDATE_DEPENDENCY_ALLOWLIST"):
        updates["dependency_allowlist_file"] = dependency_allowlist
    if helper_socket := os.getenv("THREE_MM_UPDATE_HELPER_SOCKET"):
        updates["helper_socket"] = helper_socket
    if helper_status := os.getenv("THREE_MM_UPDATE_HELPER_STATUS_FILE"):
        updates["helper_status_file"] = helper_status
    if update_policy := os.getenv("THREE_MM_UPDATE_POLICY_FILE"):
        updates["policy_file"] = update_policy
    if update_check_cache := os.getenv("THREE_MM_UPDATE_CHECK_CACHE_FILE"):
        updates["check_cache_file"] = update_check_cache
    if update_timeout := os.getenv("THREE_MM_UPDATE_TIMEOUT_SECONDS"):
        updates["timeout_seconds"] = int(update_timeout)
    if approval_ttl := os.getenv("THREE_MM_UPDATE_APPROVAL_TTL_SECONDS"):
        updates["approval_ttl_seconds"] = int(approval_ttl)
    if max_artifact := os.getenv("THREE_MM_UPDATE_MAX_ARTIFACT_BYTES"):
        updates["max_artifact_bytes"] = int(max_artifact)
    if minimum_free := os.getenv("THREE_MM_UPDATE_MINIMUM_FREE_BYTES"):
        updates["minimum_free_bytes"] = int(minimum_free)
    if recovery_policy := os.getenv("THREE_MM_NETWORK_RECOVERY_POLICY_FILE"):
        network_recovery["policy_file"] = recovery_policy
    if recovery_marker := os.getenv("THREE_MM_NETWORK_RECOVERY_MARKER_FILE"):
        network_recovery["marker_file"] = recovery_marker
    if recovery_helper := os.getenv("THREE_MM_NETWORK_RECOVERY_HELPER_SOCKET"):
        network_recovery["helper_socket"] = recovery_helper
    if recovery_delay := os.getenv("THREE_MM_NETWORK_RECOVERY_OFFLINE_SECONDS"):
        network_recovery["offline_after_seconds"] = int(recovery_delay)

    backend["database_url"] = _normalize_database_url(
        backend.get("database_url", BackendSettings().database_url)
    )

    return AppSettings(
        frontend=FrontendSettings.model_validate(frontend),
        backend=BackendSettings.model_validate(backend),
        updates=UpdateCatalogSettings.model_validate(updates),
        network_recovery=NetworkRecoverySettings.model_validate(network_recovery),
    )
