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
    monkeypatch.setenv("BACKEND_PORT", "9001")
    monkeypatch.setenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    )
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.database_url == "sqlite:///:memory:"
    assert settings.backend.port == 9001
    assert settings.backend.cors_origins == [
        "http://localhost:3000",
        "http://localhost:5173",
    ]
