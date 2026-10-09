"""Offline SQLite recovery fences, not grants or a runtime authorization API.

Trusted coordinators must hold the release mutation lock and stop Core, Agent
and application services first. Only DB work belongs in this short transaction.
Normal startup/update must not call this operation.
"""

from contextlib import closing
from dataclasses import dataclass
import logging
from pathlib import Path
import re
import secrets
import sqlite3


class AuthorityRecoveryError(RuntimeError):
    def __init__(self):
        super().__init__("Recovery authority metadata is unavailable")


@dataclass(frozen=True)
class RecoveryFence:
    generation: str | None
    applications: int = 0
    connectors: int = 0
    devices: int = 0


REASONS = frozenset({"backup_restore", "restore_rollback", "deployment_rollback", "factory_reset"})
METADATA_COLUMNS = {
    "core_authority_guard": {"singleton_id", "generation", "revision"},
    "application_extension_installations": {"authority_incarnation", "authority_epoch", "authority_mode"},
    "application_connector_bindings": {"authority_revision"},
    "device_platform_states": {"device_id", "control_generation"},
}
GRANT_TABLES = frozenset({'application_native_reviews', 'application_authority_plans',
    'application_authority_grants', 'application_authority_actions'})

# Frozen ancestors of the first authority migration. Unknown/future revisions
# cannot turn missing M20 metadata into a legacy rollback. Stdlib-only recovery;
# never import the mutable Alembic/runtime model graph on the damaged host.
PRE_AUTHORITY_REVISIONS = frozenset({
    "a7bf06b7c8d9", "96aef5a6b7c8", "859de4f5a6b7", "748cd3e4f5a6", "637bc2d3e4f5",
    "526ab1c2d3e4", "4159a0b1c2d3", "3048f9a0b1c2", "2f37e8f9a0b1", "1e26d7e8f9a0",
    "0d15c6d7e8f9", "fc04b5c6d7e8", "ebf3a4b5c6d7", "dae2f3a4b5c6", "c9e1f2a3b4c5",
    "b8d0e1f2a3c4", "a7c9d0e1f2b3", "3af4b5c6d7e8", "29e3f4a5b6c7", "18d2e3f4a5b6",
    "07c9d1e2f3a4", "f6b8c9d0e1f2", "e5a7b8c9d0e1", "d496ac2d3465", "c385fb1c2354",
    "b274fa0b1243", "a164fa0b1242", "9c53e9fa0131", "8b42d8e9f120", "7a31d5d293e1",
    "3c822ea2b9ab", "drop_items_col", "29d0afad2ec4", "add_language_code_to_settings",
    "0f1e2d3c4b5a",
})


def _valid_generation(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise AuthorityRecoveryError()


def _physical_fences(db, tables):
    # Keep the existing physical-command fence, but never classify a dispatched
    # action as certainly failed. Retain its receipt, attempts and timestamps.
    if "application_command_epochs" in tables:
        db.execute("UPDATE application_command_epochs SET generation=lower(hex(randomblob(16)))")
    if "device_commands" in tables:
        columns = {row[1] for row in db.execute("PRAGMA table_info(device_commands)")}
        attempts = [condition for column, condition in (
            ("delivery_attempts", "delivery_attempts > 0"),
            ("delivered_at", "delivered_at IS NOT NULL"),
        ) if column in columns]
        evidence = " OR ".join(attempts) or "0"
        db.execute(f"""UPDATE device_commands SET status='unknown', error='restore_unconfirmed'
                      WHERE command_type IN ('application.capability.invoke', 'capability.invoke')
                        AND (status='delivered' OR (status='queued' AND ({evidence})))""")
        db.execute("""UPDATE device_commands SET status='failed', error='Restore invalidated physical authority'
                      WHERE command_type IN ('application.capability.invoke', 'capability.invoke')
                        AND status='queued'""")
    if "application_job_states" in tables:
        columns = {row[1] for row in db.execute("PRAGMA table_info(application_job_states)")}
        if "lease_token" in columns:
            # Replace, never clear, the occupied token. Scheduler quarantine and
            # previous uncertain outcome remain; this cannot release/replay work.
            db.execute("""UPDATE application_job_states
                          SET lease_token=lower(hex(randomblob(16))), lease_until=NULL,
                              last_outcome='unknown', last_error='restore_unconfirmed'
                          WHERE lease_token IS NOT NULL OR last_outcome='running'""")


def fence_recovered_authority(database: Path, *, reason: str, allow_legacy: bool = False) -> RecoveryFence:
    """Fresh generations + physical quarantine atomically, before service start.

    Legacy is allowed only for rollback into a pre-M20 schema. Partial/current
    metadata is corruption, not permission to initialize or fall back to legacy.
    Logical identities, incarnations, modes, credentials and configuration stay.
    """
    if reason not in REASONS or (allow_legacy and reason not in {"restore_rollback", "deployment_rollback"}):
        raise AuthorityRecoveryError()
    path = Path(database)
    if path.is_symlink() or not path.is_file():
        raise AuthorityRecoveryError()
    try:
        with closing(sqlite3.connect(path.absolute().as_uri() + "?mode=rw", uri=True)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            columns = {
                table: {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                for table in METADATA_COLUMNS
            }
            if "core_authority_guard" not in tables:
                partial = any(columns[table] & names for table, names in METADATA_COLUMNS.items()
                              if table != "device_platform_states")
                partial |= "control_generation" in columns["device_platform_states"]
                partial |= bool(tables & {"application_policy_reviews", "application_policy_review_decisions"})
                partial |= bool(tables & GRANT_TABLES)
                revisions = ({row[0] for row in db.execute("SELECT version_num FROM alembic_version")}
                             if "alembic_version" in tables else set())
                current = bool(revisions - PRE_AUTHORITY_REVISIONS)
                if not allow_legacy or partial or current:
                    raise AuthorityRecoveryError()
                _physical_fences(db, tables)
                report = RecoveryFence(None)
            else:
                if any(not names <= columns[table] for table, names in METADATA_COLUMNS.items()):
                    raise AuthorityRecoveryError()
                # Same serialization point as online writers, first row write.
                if db.execute("UPDATE core_authority_guard SET revision=revision WHERE singleton_id=1").rowcount != 1:
                    raise AuthorityRecoveryError()
                guard = db.execute("SELECT generation, revision FROM core_authority_guard WHERE singleton_id=1").fetchone()
                _valid_generation(guard[0])
                if type(guard[1]) is not int or not 1 <= guard[1] <= 2**53 - 1:
                    raise AuthorityRecoveryError()
                for incarnation, epoch, mode in db.execute(
                    "SELECT authority_incarnation, authority_epoch, authority_mode FROM application_extension_installations"
                ):
                    _valid_generation(incarnation)
                    _valid_generation(epoch)
                    if mode not in {"compatibility", "review_required", "enforced"}:
                        raise AuthorityRecoveryError()
                    if mode == 'enforced' and not GRANT_TABLES <= tables:
                        raise AuthorityRecoveryError()
                for table, column in (("application_connector_bindings", "authority_revision"),
                                      ("device_platform_states", "control_generation")):
                    for (value,) in db.execute(f"SELECT {column} FROM {table}"):
                        _valid_generation(value)
                if db.execute("""SELECT 1 FROM devices d LEFT JOIN device_platform_states p ON p.device_id=d.id
                                 WHERE p.device_id IS NULL LIMIT 1""").fetchone():
                    raise AuthorityRecoveryError()
                generation = secrets.token_hex(16)
                # New identity permits a new counter, but mark it used so the
                # existing unused-metadata downgrade gate cannot erase this fence.
                db.execute("UPDATE core_authority_guard SET generation=?, revision=2 WHERE singleton_id=1", (generation,))
                counts = []
                for table, column in (("application_extension_installations", "authority_epoch"),
                                      ("application_connector_bindings", "authority_revision"),
                                      ("device_platform_states", "control_generation")):
                    counts.append(db.execute(f"UPDATE {table} SET {column}=lower(hex(randomblob(16)))").rowcount)
                _physical_fences(db, tables)
                report = RecoveryFence(generation, *counts)
    except (sqlite3.Error, OSError) as exc:
        raise AuthorityRecoveryError() from exc
    # Root recovery status/journal owns operational attribution, not a user ID
    # looked up in a restored/foreign user table. No private data is logged.
    logging.getLogger(__name__).warning(
        "Recovery authority fenced: reason=%s generation=%s applications=%d connectors=%d devices=%d",
        reason, report.generation, report.applications, report.connectors, report.devices,
    )
    return report


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reason", choices=sorted(REASONS), required=True)
    parser.add_argument("--allow-legacy", action="store_true")
    args = parser.parse_args()
    if getattr(os, "geteuid", lambda: 1)() != 0:
        raise SystemExit("Authority recovery must run as root")
    logging.basicConfig(level=logging.INFO)
    fence_recovered_authority(Path("/var/lib/3mm/core/3mm.db"), reason=args.reason, allow_legacy=args.allow_legacy)
