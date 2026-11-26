"""Optional workstation-only check of portable archive UI build evidence, not trust."""
from contextlib import closing
from pathlib import Path
import re
import sqlite3
from itertools import count

from backend.artifacts.packages import MAX_PACKAGE_BYTES, validate_module_package
from backend.artifacts.provenance import read_build, UiBuildEvidenceError


MAX_ACTIVE = 8
MAX_INPUT = 64 * 1024 * 1024


def observe(staging, entries):
    """Called only after all entries and active package identities passed staging.

    No compiler, app, configured artifact store or review key. Passing means
    the archived build inventory agrees with the packaged UI declaration.
    """
    core = staging / "payload/core"
    sizes = {item.path: item.size_bytes for item in entries if item.area == "core"}
    try:
        with closing(sqlite3.connect((core / "3mm.db").as_uri() + "?mode=ro", uri=True, timeout=0.2)) as db:
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("PRAGMA query_only=ON")
            db.set_progress_handler(lambda steps=count(): next(steps) >= 256, 1000)
            rows = db.execute("""SELECT p.sha256 FROM application_extension_installations AS i
                LEFT JOIN module_packages AS p ON p.id=i.module_package_id
                WHERE i.enabled=1 AND i.status='active' LIMIT ?""", (MAX_ACTIVE+1,)).fetchall()
        if len(rows) > MAX_ACTIVE:
            return "not_checked"
        total, saw_ui = 0, False
        for sha, in rows:
            if type(sha) is not str or not re.fullmatch("[0-9a-f]{64}", sha):
                return "not_checked"
            package = f"uploads/modules/{sha}.zip"
            size = sizes.get(package, 0)
            total += size
            if not 0 < size <= MAX_PACKAGE_BYTES or total > MAX_INPUT:
                return "not_checked"
            with (core/package).open("rb") as source:
                app = validate_module_package(source.read(size+1))
            if app.sha256 != sha:
                return "not_checked"
            if app.compiled_ui is None:
                continue
            saw_ui = True
            relative = Path("extensions/compiled") / app.manifest.module_id / app.manifest.version / sha
            base = core / relative
            if not base.resolve().is_relative_to(core/"extensions/compiled"):
                return "not_checked"
            prefix = relative.as_posix() + "/"
            total += sum(n for path,n in sizes.items() if path.startswith(prefix))
            if total > MAX_INPUT:
                return "not_checked"
            try:
                if not read_build(base,app):
                    return "build_attention"
            except UiBuildEvidenceError:
                return "build_attention"
        return "builds_matched" if saw_ui else "no_active_ui_observed"
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return "not_checked"
