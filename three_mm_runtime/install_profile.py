"""Immutable release-local installation profile, independent of device role."""

from enum import Enum
from pathlib import Path


class InstallProfile(str, Enum):
    FULL = "full"
    NODE = "node"


def read_install_profile(release_root: Path) -> InstallProfile:
    marker = release_root / ".3mm-install-profile"
    try:
        value = marker.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        # Released versions before Fleet contain the full runtime.
        return InstallProfile.FULL
    try:
        return InstallProfile(value)
    except ValueError as exc:
        raise RuntimeError("Invalid installation profile; refusing runtime activation") from exc


def validate_profile_role(profile: InstallProfile, role: str | None) -> None:
    if profile is InstallProfile.NODE and role not in {None, "node"}:
        raise RuntimeError("Install the full runtime before promoting a minimal Node to Hub")
