"""Private quiescent migration worker, never a runtime/SDK maintenance API.

Only the trusted preparation helper launches it AFTER durable Core begin and
verified DB/files preimages. The child gets no key/token/platform client. Exact
wheel imports and migration callbacks run as the application UID, never root.
Cooperative SQL restrictions are not hostile-native isolation (WP5).
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import math
import os
import signal
import sqlite3
import stat
import subprocess
import sys
import time
import zipimport
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from three_mm_application_sdk import ApplicationMigration, ApplicationStorage
from three_mm_application_sdk.relational_wire import (
    Digest,
    Millis,
    canonical,
    migration_worker_profile_digest,
)
from three_mm_application_sdk.scoped_relational import (
    _FUNCTIONS,
    _READ_PRAGMAS,
    ApplicationScopedStorage,
    _Session,
)
from three_mm_application_sdk.transaction_guard import relational_transaction_active
from three_mm_protocol.application_extension import (
    SERVICE_ENTRYPOINT_PATTERN,
    ApplicationRelationalStorageV1,
)
from three_mm_runtime.application_relational_session import (
    _clock,
    _decode,
    _protected_directory,
    _regular,
)

MAX_WORKER_MS = 30000
MAX_MIGRATIONS = 128


class MigrationWorkerUnconfirmed(RuntimeError):
    """A worker/group may still be alive: NEVER restore or publish live data."""


def _wait_worker(process, plan):
    # Keep the leader unreaped until killpg: its PID must not be reused for a
    # foreign process group between normal completion and descendant cleanup.
    while True:
        remaining = _remaining(plan)
        status = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        if status is not None:
            return (
                status.si_status
                if status.si_code == os.CLD_EXITED
                else -status.si_status
            )
        time.sleep(min(0.05, remaining))


def _stop_worker(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as error:
        raise MigrationWorkerUnconfirmed("Migration worker stop unconfirmed") from error
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired as error:
        raise MigrationWorkerUnconfirmed("Migration worker stop unconfirmed") from error
    deadline = time.monotonic() + 2
    while True:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        except OSError as error:
            raise MigrationWorkerUnconfirmed(
                "Migration worker group stop unconfirmed"
            ) from error
        if time.monotonic() >= deadline:
            raise MigrationWorkerUnconfirmed("Migration worker group stop unconfirmed")
        time.sleep(0.01)


class _WorkerPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    instance_root: Annotated[str, Field(min_length=1, max_length=4096)]
    package_sha256: Digest
    service_sha256: Digest
    migration_entrypoint: Annotated[
        str, Field(pattern=SERVICE_ENTRYPOINT_PATTERN, max_length=240)
    ]
    schema_revision: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")]
    declaration: ApplicationRelationalStorageV1
    database_present: bool
    service_uid: Annotated[int, Field(strict=True, ge=1)]
    service_gid: Annotated[int, Field(strict=True, ge=1)]
    boot_id: Annotated[
        str,
        Field(
            pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        ),
    ]
    issued_at_ms: Millis
    deadline_ms: Millis

    @model_validator(mode="after")
    def valid(self):
        if (
            not Path(self.instance_root).is_absolute()
            or not 0 < self.deadline_ms - self.issued_at_ms <= MAX_WORKER_MS
        ):
            raise ValueError("Invalid migration worker plan")
        return self


def _remaining(plan):
    boot, now = _clock()
    if boot != plan.boot_id or not plan.issued_at_ms <= now < plan.deadline_ms:
        raise TimeoutError("Migration worker expired")
    return (plan.deadline_ms - now) / 1000


def _paths(plan):
    instance = Path(plan.instance_root)
    for directory in (
        instance,
        instance / "releases",
        instance / "releases" / plan.package_sha256,
    ):
        _protected_directory(directory)
    data = instance / "data"
    info = data.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != plan.service_uid
        or info.st_mode & 0o022
    ):
        raise ValueError("Migration own namespace unavailable")
    wheel = instance / "releases" / plan.package_sha256 / "service.whl"
    _regular(wheel, protected=True)
    with wheel.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != plan.service_sha256:
            raise ValueError("Migration wheel changed")
    database = data / "state.sqlite3"
    if os.path.lexists(database) != plan.database_present:
        raise ValueError("Migration database presence changed")
    if plan.database_present:
        info = _regular(database)
        if info.st_uid != plan.service_uid or info.st_mode & 0o022:
            raise ValueError("Migration database ownership unavailable")
    for suffix in ("-wal", "-shm", "-journal"):
        path = database.with_name(database.name + suffix)
        if os.path.lexists(path):
            if not plan.database_present:
                raise ValueError("Migration database has orphan sidecars")
            _regular(path)
    return data, wheel, database


def run_business_migrations(
    instance, ticket, definition, *, database_present, service_uid, service_gid
):
    """Root helper only; no arbitrary caller paths, shell, env or executable.

    This does NOT validate Core authority: the enclosing helper must do so. Its
    locks/preimages remain held; no Core lease is held across this process.
    No retry/repair is possible here. Failure requires enclosing rollback/review.
    """
    if (
        os.name != "posix"
        or os.geteuid() != 0
        or ticket.get("action") != "prepare_migrated_schema"
        or ticket.get("worker_profile_sha256") != migration_worker_profile_digest()
    ):
        raise ValueError("Migration preparation authority unavailable")
    boot, now = _clock()
    if (
        boot != ticket["boot_id"]
        or not ticket["issued_at_ms"] <= now < ticket["deadline_ms"]
    ):
        raise TimeoutError("Migration preparation expired")
    plan = _WorkerPlan.model_validate(
        {
            "instance_root": str(Path(instance).absolute()),
            "package_sha256": ticket["package_sha256"],
            "service_sha256": ticket["service_sha256"],
            "migration_entrypoint": definition.storage.migration_entrypoint,
            "schema_revision": ticket["schema_revision"],
            "declaration": definition.storage.relational.model_dump(mode="json"),
            "database_present": database_present,
            "service_uid": service_uid,
            "service_gid": service_gid,
            "boot_id": boot,
            "issued_at_ms": now,
            "deadline_ms": min(ticket["deadline_ms"], now + MAX_WORKER_MS),
        }
    )
    data, _, _ = _paths(plan)
    payload = canonical(plan.model_dump(mode="json"))
    if len(payload) > 8192:
        raise ValueError("Migration worker plan too large")
    # -I removes inherited PYTHONPATH/user site/current-directory imports. Only
    # the installed Core runtime root and then the pinned wheel are selected.
    bootstrap = "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('three_mm_runtime.application_relational_migrations',run_name='__main__')"
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-c",
            bootstrap,
            str(Path(__file__).resolve().parent.parent),
            payload.decode("ascii"),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=data,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        user=service_uid,
        group=service_gid,
        extra_groups=[],
        start_new_session=True,
        umask=0o077,
        close_fds=True,
    )
    try:
        code = _wait_worker(process, plan)  # CLOCK_BOOTTIME includes suspend.
        _remaining(plan)
        if code != 0:
            raise ValueError("Migration worker failed; do not replay")
    finally:
        # Also stop ordinary background children after nominal completion. A
        # malicious setsid/raw-I/O escape is NOT contained by this WP4 boundary.
        _stop_worker(process)


class _MigrationSession(_Session):
    """Same statement/value/cursor/deadline bounds; only own business DDL added."""

    def __init__(self, *args, **kwargs):
        self._virtual = set()
        connection = args[1]
        self._virtual = {
            row[1]
            for row in connection.execute("PRAGMA main.table_list")
            if row[2] in {"virtual", "shadow"}
        }
        super().__init__(*args, **kwargs)

    def _authorize(self, action, first, second, database, source):
        names = ((first or "").lower(), (second or "").lower())
        protected = any(name.startswith("three_mm_") for name in names)
        if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}:
            allowed = True
        elif action == sqlite3.SQLITE_READ:
            allowed = database in {None, "main"} and first not in self._virtual
        elif action == sqlite3.SQLITE_FUNCTION:
            allowed = names[1] in _FUNCTIONS | {
                "sqlite_rename_table",
                "sqlite_rename_column",
                "sqlite_rename_test",
                "sqlite_drop_column",
                "sqlite_rename_quotefix",
            }
        elif action == sqlite3.SQLITE_PRAGMA:
            allowed = names[0] in _READ_PRAGMAS and database in {None, "main"}
        elif action in {
            sqlite3.SQLITE_INSERT,
            sqlite3.SQLITE_UPDATE,
            sqlite3.SQLITE_DELETE,
        }:
            allowed = (
                not names[0].startswith("three_mm_")
                and database == "main"
                and first not in self._virtual
            )
        elif action == sqlite3.SQLITE_ALTER_TABLE:
            allowed = (
                first == "main"
                and not names[1].startswith(("three_mm_", "sqlite_"))
                and source is None
            )
        elif action in {
            sqlite3.SQLITE_CREATE_TABLE,
            sqlite3.SQLITE_DROP_TABLE,
            sqlite3.SQLITE_CREATE_INDEX,
            sqlite3.SQLITE_DROP_INDEX,
            sqlite3.SQLITE_CREATE_VIEW,
            sqlite3.SQLITE_DROP_VIEW,
            sqlite3.SQLITE_CREATE_TRIGGER,
            sqlite3.SQLITE_DROP_TRIGGER,
        }:
            allowed = not protected and database == "main" and source is None
        else:
            allowed = False  # transaction/ATTACH/TEMP/virtual/UDF/unsafe PRAGMA
        return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY


class _MigrationStorage(ApplicationStorage):
    def __init__(self, data, plan):
        super().__init__(data)
        self.plan = plan
        self.scoped = ApplicationScopedStorage(
            data, declaration=plan.declaration, schema_revision=plan.schema_revision
        )

    def _connect(self):
        remaining = _remaining(self.plan)
        _regular(self.database_path)
        self.scoped._check_auxiliary()
        connection = sqlite3.connect(
            self.database_path.as_uri() + "?mode=rw",
            uri=True,
            timeout=0,
            isolation_level=None,
            cached_statements=0,
            factory=_MigrationConnection,
        )
        try:
            connection.plan = self.plan
            connection.scoped = self.scoped
            connection.deadline = time.monotonic() + min(
                remaining, self.plan.declaration.max_transaction_ms / 1000
            )
            connection.row_factory = sqlite3.Row
            connection.enable_load_extension(False)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                f"PRAGMA busy_timeout={min(self.plan.declaration.max_busy_ms, int(remaining * 1000))}"
            )
            connection.set_progress_handler(
                lambda: int(_clock()[1] >= self.plan.deadline_ms), 500
            )
            connection.setlimit(
                sqlite3.SQLITE_LIMIT_LENGTH,
                max(4096, self.plan.declaration.max_result_bytes),
            )
            connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)
            connection.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
            connection.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 50)
            page_size = connection.execute("PRAGMA page_size").fetchone()[0]
            maximum = self.plan.declaration.max_database_bytes // page_size
            if (
                connection.execute("PRAGMA page_count").fetchone()[0] > maximum
                or connection.execute(f"PRAGMA max_page_count={maximum}").fetchone()[0]
                != maximum
            ):
                raise ValueError("Migration database exceeds profile")
            if connection.execute(
                "SELECT name FROM sqlite_schema WHERE name IN ('three_mm_relational_lineage','three_mm_relational_commits')"
            ).fetchone():
                raise ValueError("Prepared database requires recovery review")
            if (
                connection.execute(
                    "SELECT name FROM sqlite_schema WHERE name='three_mm_schema_migrations'"
                ).fetchone()
                and connection.execute(
                    "SELECT COUNT(*) FROM three_mm_schema_migrations"
                ).fetchone()[0]
                > MAX_MIGRATIONS
            ):
                raise ValueError("Migration history exceeds worker profile")
            return connection
        except BaseException:
            connection.close()
            raise

    def apply(self, migration, connection):
        remaining = min(_remaining(self.plan), connection.deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("Migration transaction expired")
        session = _MigrationSession(
            self.scoped,
            connection,
            "write",
            time.monotonic() + remaining,
            min(self.plan.deadline_ms, _clock()[1] + int(remaining * 1000)),
        )
        try:
            migration.apply(session)
            session._prepare_commit()  # Includes sticky failure + final deadline.
        finally:
            session._close()
            connection.set_progress_handler(
                lambda: int(
                    time.monotonic() >= connection.deadline
                    or _clock()[1] >= self.plan.deadline_ms
                ),
                500,
            )
        # SQLite ALTER authorization reports the OLD name only. Check reserved
        # names after DDL as well, before the SDK inserts history/commits.
        unexpected = connection.execute(
            "SELECT name FROM sqlite_schema WHERE lower(name) GLOB 'three_mm_*' AND name NOT IN ('three_mm_schema_migrations','three_mm_outbox')"
        ).fetchone()
        if unexpected:
            raise ValueError("Migration changed reserved SDK metadata")


class _MigrationConnection(sqlite3.Connection):
    def commit(self):
        _remaining(self.plan)
        if time.monotonic() >= self.deadline:
            raise TimeoutError("Migration transaction expired")
        self.scoped._check_auxiliary()
        self.execute(
            f"PRAGMA busy_timeout={min(self.plan.declaration.max_busy_ms, max(0, int((self.deadline - time.monotonic()) * 1000)))}"
        )
        return super().commit()


def _migration_factory(wheel, entrypoint):
    # Prepending sys.path alone does not pin imports: an already-loaded Core
    # module or a parent package outside the wheel can win resolution. Validate
    # each package before importing it, then resolve the reviewed factory.
    module_name, factory_name = entrypoint.split(":", 1)
    parts = module_name.split(".")
    for length in range(1, len(parts) + 1):
        name = ".".join(parts[:length])
        spec = importlib.util.find_spec(name)
        if spec is None:
            raise ValueError("Migration entrypoint must come from the pinned wheel")
        pinned = (
            isinstance(spec.loader, zipimport.zipimporter)
            and Path(spec.loader.archive).resolve() == wheel.resolve()
        )
        # Preserve valid namespace packages, but not a mixed namespace spanning
        # other wheels/Core directories. They have locations rather than code.
        locations = list(spec.submodule_search_locations or ())
        if spec.origin is None and locations:
            pinned = all(
                Path(location).resolve().is_relative_to(wheel.resolve())
                for location in locations
            )
        if not pinned:
            raise ValueError("Migration entrypoint must come from the pinned wheel")
        module = importlib.import_module(name)
    factory = getattr(module, factory_name)
    if not callable(factory):
        raise ValueError("Migration factory is invalid")
    return factory


def _worker(plan):
    # Validate real privileges BEFORE imports, database creation or package code.
    if (
        os.name != "posix"
        or os.getuid() != plan.service_uid
        or os.geteuid() != plan.service_uid
        or os.getgid() != plan.service_gid
        or os.getegid() != plan.service_gid
        or set(os.getgroups()) - {plan.service_gid}
    ):
        raise ValueError("Migration worker must run as the exact non-root service")
    remaining = _remaining(plan)
    import resource

    for kind, ceiling in (
        (resource.RLIMIT_AS, 512 * 1024 * 1024),
        (resource.RLIMIT_CPU, max(1, math.ceil(remaining))),
        (
            resource.RLIMIT_FSIZE,
            plan.declaration.max_database_bytes
            + plan.declaration.auxiliary_pause_bytes,
        ),
    ):
        _, hard = resource.getrlimit(kind)
        bound = min(ceiling, hard) if hard != resource.RLIM_INFINITY else ceiling
        resource.setrlimit(kind, (bound, bound))
    data, wheel, database = _paths(plan)
    sys.path.insert(0, str(wheel))
    token = relational_transaction_active.set(True)  # No platform/file dispatch.
    try:
        migrations = _migration_factory(wheel, plan.migration_entrypoint)()
        if (
            type(migrations) not in {list, tuple}
            or not 1 <= len(migrations) <= MAX_MIGRATIONS
            or not all(
                isinstance(item, ApplicationMigration) and callable(item.apply)
                for item in migrations
            )
        ):
            raise ValueError("Migration plan is invalid")
        _remaining(plan)
        # Import/factory is application code; verify the selected namespace again.
        _paths(plan)
        if not plan.database_present:
            descriptor = os.open(
                database, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            os.close(descriptor)
        storage = _MigrationStorage(data, plan)
        guarded = [
            ApplicationMigration(
                item.revision, lambda db, item=item: storage.apply(item, db)
            )
            for item in migrations
        ]
        # Reuse SDK forward-history/outbox compatibility. Each migration has its
        # own atomic transaction; enclosing helper restores the coherent preimage
        # if a later step fails. No service factory, replay or runtime grant.
        storage.migrate(guarded, plan.schema_revision)
        _remaining(plan)
        storage.scoped._check_auxiliary()
    finally:
        relational_transaction_active.reset(token)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Private migration worker plan required")
    _worker(
        _WorkerPlan.model_validate(_decode(sys.argv[1].encode("ascii"), limit=8192))
    )
