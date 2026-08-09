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


class AppSettings(BaseModel):
    frontend: FrontendSettings = Field(default_factory=FrontendSettings)
    backend: BackendSettings = Field(default_factory=BackendSettings)

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

    backend["database_url"] = _normalize_database_url(
        backend.get("database_url", BackendSettings().database_url)
    )

    return AppSettings(
        frontend=FrontendSettings.model_validate(frontend),
        backend=BackendSettings.model_validate(backend),
    )
