"""Persistent public assets, separate from immutable code and private app data."""

import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote

from backend.config import AppSettings, get_settings


class AssetPathError(ValueError):
    """An asset path is outside its permitted namespace or is unsafe."""


class AssetStorage:
    """Use the same configured root for writes, static serving and backups.

    Files here are public through /uploads. Secrets, application databases and
    private generated files belong in the application's existing private data
    directory, not this store. Callers remain responsible for authorization,
    content validation and size limits.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()

    @staticmethod
    def _parts(relative: str) -> list[str]:
        if not isinstance(relative, str) or any(
            char in relative for char in ("\\", ":", "\x00")
        ):
            raise AssetPathError("Invalid asset path")
        parts = relative.split("/") if relative else []
        if any(part in {"", ".", ".."} for part in parts):
            raise AssetPathError("Invalid asset path")
        return parts

    def directory(self, relative: str = "", *, create: bool = False) -> Path:
        target = self.root
        for part in self._parts(relative):
            target = target / part
            if target.is_symlink():
                raise AssetPathError("Asset directories must not be symbolic links")
        if not target.resolve().is_relative_to(self.root):
            raise AssetPathError("Asset path is outside writable storage")
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return target

    def settings_dir(self, *, create: bool = False) -> Path:
        return self.directory("settings", create=create)

    def extension_dir(self, extension_id: str, *, create: bool = False) -> Path:
        if not isinstance(extension_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", extension_id
        ):
            raise AssetPathError("Invalid extension identifier")
        return self.directory(f"extensions/{extension_id}", create=create)

    def file(self, directory: str, name: str) -> Path:
        parts = self._parts(name)
        if len(parts) != 1:
            raise AssetPathError("Asset filename must be a single name")
        parent = self.directory(directory)
        target = parent / name
        if target.is_symlink() or not target.resolve().is_relative_to(parent.resolve()):
            raise AssetPathError("Asset file is outside its namespace")
        return target

    def public_url(self, directory: str, name: str) -> str:
        self.file(directory, name)
        relative = "/".join([*self._parts(directory), name])
        return f"/uploads/{quote(relative, safe='/')}"

    def write_bytes(self, directory: str, name: str, content: bytes) -> Path:
        """Replace atomically; a failed upload must not erase the previous logo."""
        target = self.file(directory, name)
        self.directory(directory, create=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target.parent, prefix=".upload-", suffix=".tmp", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            os.replace(temporary, target)
            return target
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def get_asset_storage(settings: AppSettings | None = None) -> AssetStorage:
    return AssetStorage((settings or get_settings()).backend.uploads_dir)
