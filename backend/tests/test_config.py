import json

from backend.config import get_settings


def test_safe_portable_defaults(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("APP_CONFIG_FILE", str(config_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.database_url.startswith("sqlite:///")
    assert settings.backend.port == 8887
    assert "password" not in settings.database_url
    assert settings.updates.repository == "ldobranov/3mm"
    assert settings.updates.manifest_asset_name == "3mm-update-manifest.json"


def test_environment_overrides_file_configuration(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "backend": {
                    "database_url": "sqlite:///ignored.db",
                    "port": 8887,
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("APP_CONFIG_FILE", str(config_path))
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BACKEND_PORT", "9001")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
    monkeypatch.setenv("DEVICE_OFFLINE_AFTER_SECONDS", "120")
    monkeypatch.setenv("THREE_MM_UPDATE_REPOSITORY", "example/3mm")
    monkeypatch.setenv("THREE_MM_UPDATE_MANIFEST_ASSET", "catalog.json")
    monkeypatch.setenv("THREE_MM_RELEASE_METADATA_FILE", str(tmp_path / "release.json"))
    monkeypatch.setenv("THREE_MM_UPDATE_STAGING_DIR", str(tmp_path / "staging"))
    monkeypatch.setenv(
        "THREE_MM_UPDATE_DEPENDENCY_ALLOWLIST", str(tmp_path / "allowlist.json")
    )
    monkeypatch.setenv("THREE_MM_UPDATE_HELPER_SOCKET", str(tmp_path / "helper.sock"))
    monkeypatch.setenv(
        "THREE_MM_UPDATE_HELPER_STATUS_FILE", str(tmp_path / "status.json")
    )
    monkeypatch.setenv("THREE_MM_UPDATE_POLICY_FILE", str(tmp_path / "policy.json"))
    monkeypatch.setenv(
        "THREE_MM_UPDATE_CHECK_CACHE_FILE", str(tmp_path / "check-cache.json")
    )
    monkeypatch.setenv("THREE_MM_UPDATE_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("THREE_MM_UPDATE_APPROVAL_TTL_SECONDS", "900")
    monkeypatch.setenv("THREE_MM_UPDATE_MAX_ARTIFACT_BYTES", "104857600")
    monkeypatch.setenv("THREE_MM_UPDATE_MINIMUM_FREE_BYTES", "268435456")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.database_url == "sqlite:///:memory:"
    assert settings.backend.uploads_dir == tmp_path / "uploads"
    assert settings.backend.port == 9001
    assert settings.backend.cors_origins == [
        "http://localhost:3000",
        "http://localhost:5173",
    ]
    assert settings.backend.device_offline_after_seconds == 120
    assert settings.updates.repository == "example/3mm"
    assert settings.updates.manifest_asset_name == "catalog.json"
    assert settings.updates.release_metadata_file == tmp_path / "release.json"
    assert settings.updates.staging_dir == tmp_path / "staging"
    assert settings.updates.dependency_allowlist_file == tmp_path / "allowlist.json"
    assert settings.updates.helper_socket == tmp_path / "helper.sock"
    assert settings.updates.helper_status_file == tmp_path / "status.json"
    assert settings.updates.policy_file == tmp_path / "policy.json"
    assert settings.updates.check_cache_file == tmp_path / "check-cache.json"
    assert settings.updates.timeout_seconds == 12
    assert settings.updates.approval_ttl_seconds == 900
    assert settings.updates.max_artifact_bytes == 104857600
    assert settings.updates.minimum_free_bytes == 268435456
