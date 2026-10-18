"""Bounded local build evidence, never publisher trust or browser isolation."""

import hashlib
import json
import os
from pathlib import Path
import re
import stat


MANIFEST = "build-provenance.json"
MAX_BYTES = 40 * 1024 * 1024
MAX_FILES = 256
DOMAIN = b"3mm:compiled-ui-build:v1\x00"


class UiBuildEvidenceError(ValueError):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise UiBuildEvidenceError("Duplicate build metadata")
        result[key] = value
    return result


def _protected(path, *, directory=False):
    value = path.lstat()
    if not (stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode)):
        raise UiBuildEvidenceError("Build path is not a regular owned path")
    if os.name == "posix" and (value.st_uid != os.geteuid() or value.st_mode & 0o022):
        raise UiBuildEvidenceError("Build path is not Core-owned and protected")
    return value


def _read(path, limit=MAX_BYTES):
    if type(limit) is not int or not 0 <= limit <= MAX_BYTES:
        raise UiBuildEvidenceError("Invalid build file bound")
    original = _protected(path)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as source:
        before = os.fstat(source.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_size > limit
                or (original.st_dev, original.st_ino) != (before.st_dev, before.st_ino)
                or (os.name == "posix" and (before.st_uid != os.geteuid() or before.st_mode & 0o022))):
            raise UiBuildEvidenceError("Build file exceeds its bounds")
        data = source.read(limit + 1)
        after = os.fstat(source.fileno())
    if len(data) > limit or (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise UiBuildEvidenceError("Build changed while reading")
    return data


def _inventory(root):
    if root.absolute() != root.resolve():
        raise UiBuildEvidenceError("Build root contains a link")
    files, total, count = {}, 0, 0
    for directory, directories, names in os.walk(root, followlinks=False):
        count += 1
        if count > MAX_FILES:
            raise UiBuildEvidenceError("Build directories exceed their bounds")
        _protected(Path(directory), directory=True)
        for name in directories:
            _protected(Path(directory) / name, directory=True)
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if relative == MANIFEST:
                continue
            if len(files) >= MAX_FILES or len(relative) > 240:
                raise UiBuildEvidenceError("Build inventory exceeds its bounds")
            data = _read(path, MAX_BYTES - total)
            total += len(data)
            files[relative] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    return files


def _toolchain(value):
    expected = {"node", "vite", "vue_plugin"}
    if not isinstance(value, dict) or set(value) != expected or any(
        not isinstance(item, str) or re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][\w.-]+)?", item) is None
        for item in value.values()
    ):
        raise UiBuildEvidenceError("Build toolchain metadata is invalid")
    return value


def record_build(root, validated, compiler_sha256):
    # Old/custom compilers remain compatibility-only, never silently upgraded.
    toolchain_path = root / "build-toolchain.json"
    if not toolchain_path.exists() and not toolchain_path.is_symlink():
        return
    toolchain = _toolchain(json.loads(_read(toolchain_path, 4096), object_pairs_hook=_unique))
    value = {
        "build_version": 1, "source_sha256": validated.sha256,
        "compiler_sha256": compiler_sha256,
        "toolchain": toolchain, "files": _inventory(root),
    }
    (root / MANIFEST).write_bytes(_canonical(value))


def read_build(root, validated):
    path = root / MANIFEST
    if not path.exists() and not path.is_symlink():
        return None
    try:
        value = json.loads(_read(path, 128 * 1024), object_pairs_hook=_unique)
        if (not isinstance(value, dict)
                or set(value) != {"build_version", "source_sha256", "compiler_sha256", "toolchain", "files"}
                or type(value["build_version"]) is not int or value["build_version"] != 1
                or value["source_sha256"] != validated.sha256
                or not isinstance(value["compiler_sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", value["compiler_sha256"]) is None
                or value["files"] != _inventory(root)
                or _toolchain(value["toolchain"]) != json.loads(_read(root / "build-toolchain.json", 4096), object_pairs_hook=_unique)
                or json.loads(_read(root / "compiled-ui.json", 65536), object_pairs_hook=_unique)
                != validated.compiled_ui.model_dump(mode="json")):
            raise UiBuildEvidenceError("Build evidence changed")
        return hashlib.sha256(DOMAIN + _canonical(value)).hexdigest()
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        raise UiBuildEvidenceError("Compiled UI build evidence is unavailable") from error


def read_asset(artifact, relative):
    """Return verified bytes, not a later lazy-open FileResponse."""
    try:
        if (type(relative) is not str or "\\" in relative or relative.startswith("/")
                or any(part in {"", ".", ".."} for part in relative.split("/"))):
            raise UiBuildEvidenceError("Invalid asset path")
        value = json.loads(_read(artifact.path / MANIFEST, 128 * 1024), object_pairs_hook=_unique)
        if hashlib.sha256(DOMAIN + _canonical(value)).hexdigest() != artifact.built_ui_sha256:
            raise UiBuildEvidenceError("Build identity changed")
        expected = value["files"][relative]
        data = _read(artifact.path / relative, expected["size"])
        if hashlib.sha256(data).hexdigest() != expected["sha256"] or len(data) != expected["size"]:
            raise UiBuildEvidenceError("Build asset changed")
        return data
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise UiBuildEvidenceError("Compiled UI asset is unavailable") from error
