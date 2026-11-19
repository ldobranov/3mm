"""Check the exact packages a Standalone restore would ask to start."""

from contextlib import ExitStack, closing
from dataclasses import dataclass
import hashlib
import io
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
import time
import zipfile
import zlib

from packages.protocol import BackupEntryV1


@dataclass(frozen=True)
class CapturePackage:
    module_id: str
    version: str
    sha256: str
    size: int


# Advisory on-demand UI work only; never limits what the writer can archive
# or what staging must validate before attempting a restore.
MAX_PROFILE_CHECKS = 32
MAX_PROFILE_READ_BYTES = 24 * 1024 * 1024
MAX_PROFILE_DEFINITION_BYTES = 256 * 1024


def review_capture_profiles(packages: tuple[CapturePackage, ...], uploads: Path):
    """Inspect only exact, active, content-addressed declarations after closing the catalog.

    Return just warning counts. Capture is allowed even if automatic reactivation
    is unavailable. Do not read an app database, unpack code or start a host.
    """
    from backend.artifacts.packages import MAX_FILES, MAX_PACKAGE_BYTES
    from packages.protocol.application_extension import parse_application_extension

    remaining = MAX_PROFILE_READ_BYTES
    separate, unknown = 0, 0
    directory = uploads / "modules"
    for index, item in enumerate(packages):
        if (index >= MAX_PROFILE_CHECKS or not 0 < item.size <= min(remaining, MAX_PACKAGE_BYTES)
                or not re.fullmatch("[0-9a-f]{64}", item.sha256)):
            unknown += 1
            continue
        remaining -= item.size
        try:
            if uploads.is_symlink() or directory.is_symlink():
                raise ValueError
            path = directory / (item.sha256 + ".zip")
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                         | getattr(os, "O_BINARY", 0))
            with os.fdopen(fd, "rb") as source:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_size != item.size:
                    raise ValueError
                data = source.read(item.size + 1)
            if len(data) != item.size or hashlib.sha256(data).hexdigest() != item.sha256:
                raise ValueError
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                members = archive.infolist()
                definitions = [m for m in members if m.filename == "application-extension.json"]
                if (len(members) > MAX_FILES or len(definitions) != 1
                        or definitions[0].compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                        or not 0 < definitions[0].file_size <= MAX_PROFILE_DEFINITION_BYTES):
                    raise ValueError
                with archive.open(definitions[0]) as stream:
                    raw = stream.read(MAX_PROFILE_DEFINITION_BYTES + 1)
                if len(raw) != definitions[0].file_size:
                    raise ValueError
                app = parse_application_extension(raw)
                if (app.module_id, app.version) != (item.module_id, item.version):
                    raise ValueError
                separate += int(app.storage.relational is not None)
        except (OSError, ValueError, KeyError, RuntimeError, EOFError, zipfile.BadZipFile, zlib.error):
            unknown += 1
    return separate, unknown


class ApplicationRecoveryError(ValueError):
    """Fixed operation-safe reasons; never include paths, configuration or ZIP content."""
    preview_code = "state.application_package_invalid"
    restore_code = "restore_application_package_invalid"


class ApplicationSchemaRecoveryError(ApplicationRecoveryError):
    """The declared active data must not silently become an empty database."""
    preview_code = "state.application_schema_invalid"
    restore_code = "restore_application_schema_invalid"


class ApplicationRecoveryProfileError(ApplicationRecoveryError):
    """The ordinary Standalone activation path cannot recreate this reviewed profile."""
    restore_code = "restore_application_profile_unavailable"


def _check_staged_schema(database: Path, target_revision: str, work_root: Path) -> None:
    # Never open the uploaded original writable. A nonempty WAL may contain the only
    # copy of a committed migration: never use immutable=1 on a database with live journals.
    # SQLite can rebuild its ephemeral shared-memory index in a private disposable copy.
    try:
        with ExitStack() as stack:
            journals = [p for suffix in ("-wal", "-journal")
                        if (p := database.with_name(database.name + suffix)).is_file() and p.stat().st_size]
            if journals:
                scratch = Path(stack.enter_context(tempfile.TemporaryDirectory(dir=work_root)))
                for original in (database, *journals):
                    shutil.copyfile(original, scratch / original.name)
                uri = (scratch / database.name).as_uri() + "?mode=rw"
            else:
                uri = database.as_uri() + "?mode=ro&immutable=1"
            db = stack.enter_context(closing(sqlite3.connect(uri, uri=True, timeout=1)))
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("PRAGMA query_only=ON")
            deadline = time.monotonic() + 30
            db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
            if db.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
                raise ApplicationSchemaRecoveryError("Staged application database integrity check failed")
            ledger = db.execute("""SELECT type FROM pragma_table_list
                                   WHERE schema='main' AND name='three_mm_schema_migrations'""").fetchone()
            if ledger != ("table",) or db.execute("""SELECT substr(revision,1,65) FROM three_mm_schema_migrations
                                                    ORDER BY rowid DESC LIMIT 1""").fetchone() != (target_revision,):
                raise ApplicationSchemaRecoveryError("Staged application database does not match the active package schema")
    except (OSError, sqlite3.Error):
        raise ApplicationSchemaRecoveryError("Staged application database or schema could not be verified") from None


def _predates_applications(revision: str) -> bool:
    from alembic.script import ScriptDirectory

    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[2] / "alembic"))
    return revision in {item.revision for item in scripts.walk_revisions(
        base="base", head="3af4b5c6d7e8",  # parent of the application-installations migration
    )}


def validate_recovery_packages(database: Path, revision: str, entries: tuple[BackupEntryV1, ...],
                               *, staged_payload: Path | None = None) -> tuple[CapturePackage, ...]:
    """Preview compares journal/manifest; private restore staging also validates ZIP identities.

    Never import package code, start an app, or interpret retained data as an installed app.
    """
    candidates = []
    try:
        uri = database.resolve(strict=True).as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=1)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("BEGIN")  # one consistent catalog even for the live read-only preview
            table = db.execute("SELECT type FROM sqlite_master WHERE name='application_extension_installations'").fetchone()
            if not table and _predates_applications(revision):
                return ()
            if table != ("table",):
                raise ApplicationRecoveryError("Application installation catalog is unavailable")
            if not db.execute("SELECT 1 FROM application_extension_installations WHERE enabled=1 AND status='active' LIMIT 1").fetchone():
                return ()
            if db.execute("SELECT type FROM sqlite_master WHERE name='module_packages'").fetchone() != ("table",):
                raise ApplicationRecoveryError("Active application package catalog is unavailable")
            from backend.artifacts.packages import MAX_PACKAGE_BYTES, validate_module_package
            from components.system_runtime.application_activation import application_instance_id

            files = {e.path: e for e in entries if e.area == "core" and e.path.startswith("uploads/modules/")}
            databases = {e.path for e in entries if e.area == "applications" and e.size_bytes > 0
                         and e.path.endswith("/data/state.sqlite3")}
            rows = db.execute("""
                SELECT i.module_id, i.instance_id, i.active_version, p.module_id, p.version, p.sha256
                FROM application_extension_installations AS i
                LEFT JOIN module_packages AS p ON p.id=i.module_package_id
                WHERE i.enabled=1 AND i.status='active'
                ORDER BY i.module_id, i.instance_id
            """)
            for name, instance, active, owner, version, sha in rows:
                if (not isinstance(name, str) or len(name) > 160 or owner != name
                    or not isinstance(active, str) or not active or active != version
                    or instance != application_instance_id(name)
                    or not isinstance(sha, str) or not re.fullmatch("[0-9a-f]{64}", sha)):
                    raise ApplicationRecoveryError("Active application catalog identity does not match its package")
                entry = files.get(f"uploads/modules/{sha}.zip")
                if not entry or entry.sha256 != sha or not 0 < entry.size_bytes <= MAX_PACKAGE_BYTES:
                    raise ApplicationRecoveryError("An active application package is missing or has the wrong checksum")
                relative_db = f"{instance}/data/state.sqlite3"
                if relative_db not in databases:
                    raise ApplicationSchemaRecoveryError("The database for an active application is missing or empty")
                if staged_payload is not None:
                    # Already checksum-verified, regular files inside private restore staging only.
                    # Do not follow a database-supplied path or unpack/start the application here.
                    with (staged_payload / "core/uploads/modules" / f"{sha}.zip").open("rb") as package:
                        validated = validate_module_package(package.read(MAX_PACKAGE_BYTES + 1))
                    app = validated.application_extension
                    if app is None or (app.module_id, app.version, validated.sha256) != (name, active, sha):
                        raise ApplicationRecoveryError("Staged application package identity does not match its installation")
                    if app.storage.relational is not None:
                        # Its protected preparation/consent is not part of this archive.
                        # Neither downgrade the app to native writable SQLite nor manufacture approval.
                        raise ApplicationRecoveryProfileError(
                            "Automatic Standalone restore cannot re-create a separately prepared relational application"
                        )
                    _check_staged_schema((staged_payload / "applications" / relative_db).absolute(),
                                         app.storage.schema_revision, staged_payload.parent)
                else:
                    candidates.append(CapturePackage(name, active, sha, entry.size_bytes))
        return tuple(candidates)
    except ApplicationRecoveryError:
        raise
    except (sqlite3.Error, OSError, ValueError, KeyError, zipfile.BadZipFile, zlib.error):
        raise ApplicationRecoveryError("Active application recovery packages could not be verified") from None
