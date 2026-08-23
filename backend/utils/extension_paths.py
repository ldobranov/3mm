import os
from pathlib import Path


def backend_extensions_dir() -> Path:
    return Path(os.getenv("BACKEND_EXTENSIONS_DIR", "backend/extensions"))


def frontend_extensions_dir() -> Path:
    return Path(os.getenv("FRONTEND_EXTENSIONS_DIR", "frontend/src/extensions"))


def extension_quarantine_dir() -> Path:
    return backend_extensions_dir() / "quarantine"
