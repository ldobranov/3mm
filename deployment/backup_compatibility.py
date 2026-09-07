"""Compatibility policy for restoring archives into a newer release."""

import re
from pathlib import Path

from alembic.script import ScriptDirectory


class BackupCompatibilityError(ValueError):
    """A validated archive needs another release or a supported migration path."""


def version_key(value: str) -> tuple:
    match = re.fullmatch(
        r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
        r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
        r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?", value
    )
    if not match:
        raise BackupCompatibilityError("Backup or installed release version is invalid")
    core = tuple(int(match[i]) for i in (1, 2, 3))
    suffix = match[4]
    if suffix is None:
        return core, (1,)
    identifiers = suffix.split(".")
    if any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in identifiers):
        raise BackupCompatibilityError("Backup or installed release version is invalid")
    return core, (0, tuple((0, int(p)) if p.isdigit() else (1, p) for p in identifiers))


def validate_release_path(source: str, current: str, revision: str, release: Path) -> None:
    source_key, current_key = version_key(source), version_key(current)
    if source_key > current_key:
        raise BackupCompatibilityError(
            f"Backup requires 3mm {source} or newer; this device runs {current}. Update the device first."
        )
    # Cross-minor beta state formats are not implicitly declared compatible.
    if source_key[0][:2] != current_key[0][:2]:
        raise BackupCompatibilityError(
            f"Backup from {source} is outside the supported {current_key[0][0]}.{current_key[0][1]}.x recovery series."
        )
    scripts = ScriptDirectory(str(release / "backend/alembic"))
    heads = scripts.get_heads()
    if len(heads) != 1:
        raise BackupCompatibilityError("Installed release has no unambiguous database migration target")
    ancestors = {item.revision for item in scripts.walk_revisions(base="base", head=heads[0])}
    if revision not in ancestors:
        raise BackupCompatibilityError("Backup database revision has no supported migration path in this release")
