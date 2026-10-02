"""Fail-closed actual Core runtime version for package/SDK compatibility."""

from pathlib import Path
import re

from three_mm_protocol.module_manifest import SEMVER_PATTERN

VERSION_FILE = Path(__file__).resolve().parents[1] / "VERSION"


def core_version() -> str:
    try:
        value = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError("Core runtime version is unavailable") from exc
    if not re.fullmatch(SEMVER_PATTERN, value):
        raise ValueError("Core runtime version is invalid")
    return value
