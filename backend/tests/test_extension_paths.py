from pathlib import Path

from backend.utils.extension_paths import (
    backend_extensions_dir,
    extension_quarantine_dir,
    frontend_extensions_dir,
)
from backend.utils.extension_security import ExtensionSecurityManager


def test_extension_paths_keep_development_defaults(monkeypatch):
    monkeypatch.delenv("BACKEND_EXTENSIONS_DIR", raising=False)
    monkeypatch.delenv("FRONTEND_EXTENSIONS_DIR", raising=False)

    assert backend_extensions_dir() == Path("backend/extensions")
    assert frontend_extensions_dir() == Path("frontend/src/extensions")
    assert extension_quarantine_dir() == Path("backend/extensions/quarantine")


def test_extension_paths_can_use_writable_production_storage(monkeypatch, tmp_path):
    backend_dir = tmp_path / "extensions" / "backend"
    frontend_dir = tmp_path / "extensions" / "frontend"
    monkeypatch.setenv("BACKEND_EXTENSIONS_DIR", str(backend_dir))
    monkeypatch.setenv("FRONTEND_EXTENSIONS_DIR", str(frontend_dir))

    assert backend_extensions_dir() == backend_dir
    assert frontend_extensions_dir() == frontend_dir
    assert extension_quarantine_dir() == backend_dir / "quarantine"

    installed = backend_dir / "Clock_1.0.0"
    installed.mkdir(parents=True)
    (installed / "manifest.json").write_text("{}", encoding="utf-8")

    ExtensionSecurityManager().quarantine_extension(installed, "test")

    assert not installed.exists()
    assert (backend_dir / "quarantine" / "Clock_1.0.0" / "manifest.json").is_file()
