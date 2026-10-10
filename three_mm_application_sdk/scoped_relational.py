"""Internal bounded SQLite engine for the pending host relational adapter.

NOT selected by the host or advertised as supported. Admission is an explicit
host dependency, absent by default. Internal Core journal and atomic own-DB
receipts exist; protected host/session transport and lifecycle remain required
before enabling the profile.

Restrictions are cooperative, not a native-code sandbox or hard disk quota.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import stat
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Iterator, Literal

from three_mm_application_sdk import ApplicationOutboxItem, ApplicationStorage
from three_mm_application_sdk.transaction_guard import relational_transaction_active
from three_mm_protocol.application_extension import ApplicationRelationalStorageV1


class ApplicationRelationalStorageError(RuntimeError):
    pass


class ApplicationRelationalExecutionUnconfirmed(ApplicationRelationalStorageError):
    def __init__(self, transaction_id: str):
        self.transaction_id = transaction_id
        super().__init__("Relational commit outcome is unconfirmed; do not replay")


@dataclass(frozen=True, slots=True)
class _TransactionAdmission:
    """Internal adapter handoff, not an extension-created authority document.

    Engine test callbacks exercise ordering only. The private signed verifier
    additionally supplies permit digest and suspend-aware deadline; a production
    protected host session/transport still has to establish trusted expectations.
    """

    transaction_id: str
    mode: Literal["read", "write"]
    profile_sha256: str
    deadline: float
    permit_sha256: str | None = None
    boot_deadline_ms: int | None = None


def _expired(deadline, boot_deadline_ms=None):
    return time.monotonic() >= deadline or (
        boot_deadline_ms is not None
        and (
            not hasattr(time, "CLOCK_BOOTTIME")
            or time.clock_gettime_ns(time.CLOCK_BOOTTIME) // 1_000_000
            >= boot_deadline_ms
        )
    )


_FUNCTIONS = frozenset(
    "abs avg char coalesce count date datetime format glob hex ifnull iif instr "
    "julianday length like likelihood likely lower ltrim max min nullif printf "
    "quote random randomblob replace round rtrim sign strftime substr substring "
    "sum time total trim typeof unicode unixepoch unlikely upper zeroblob "
    "current_timestamp current_date current_time "
    "json json_array json_array_length json_extract json_insert json_object "
    "json_patch json_quote json_remove json_replace json_set json_type json_valid "
    "json_group_array json_group_object row_number rank dense_rank percent_rank "
    "cume_dist ntile lag lead first_value last_value nth_value".split()
)
_READ_PRAGMAS = frozenset(
    {"table_info", "table_xinfo", "index_list", "index_info", "foreign_key_list"}
)


def _value_bytes(value: object) -> int:
    if value is None:
        return 1
    if type(value) is str:
        return len(value.encode("utf-8"))
    if type(value) is bytes:
        return len(value)
    if type(value) is int and -(2**63) <= value < 2**63:
        return 8
    if type(value) is float and math.isfinite(value):
        return 8
    raise ApplicationRelationalStorageError("Unsupported SQLite value")


class _BoundedCursor:
    __slots__ = ("__session", "__cursor", "__batch_rowcount")

    def __init__(self, session, cursor):
        self.__session = session
        self.__cursor = cursor
        self.__batch_rowcount = None

    @property
    def rowcount(self):
        self.__session._check()
        return (
            self.__batch_rowcount
            if self.__batch_rowcount is not None
            else self.__cursor.rowcount
        )

    @property
    def lastrowid(self):
        self.__session._check()
        return None if self.__batch_rowcount is not None else self.__cursor.lastrowid

    @property
    def description(self):
        self.__session._check()
        return self.__cursor.description if self.__cursor is not None else None

    def _batch_result(self, rowcount):
        self.__batch_rowcount = rowcount
        return self

    def fetchone(self):
        session = self.__session
        session._check()
        try:
            row = self.__cursor.fetchone() if self.__cursor is not None else None
            if row is not None:
                session._account(row)
            session._check()
            return row
        except (sqlite3.Error, ApplicationRelationalStorageError) as error:
            session._fail(error)

    def fetchmany(self, size=1):
        self.__session._check()
        if (
            type(size) is not int
            or not 0 <= size <= self.__session.limits.max_result_rows
        ):
            self.__session._fail("Result row limit exceeded")
        rows = []
        for _ in range(size):
            row = self.fetchone()
            if row is None:
                break
            rows.append(row)
        return rows

    def fetchall(self):
        # Never delegate to sqlite3.fetchall: that materializes unbounded rows.
        rows = []
        for row in self:
            rows.append(row)
        return rows

    def __iter__(self):
        self.__session._check()
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row


class _Session:
    """Transaction-bound facade: no public raw connection/cursor or SQL hooks."""

    def __init__(self, storage, connection, mode, deadline, boot_deadline_ms=None):
        self.__storage = storage
        self.__limits = storage.declaration
        self.__mode = mode
        self.__connection = connection
        self.__deadline = deadline
        self.__boot_deadline_ms = boot_deadline_ms
        self.__active = True
        self.__failure = None
        self.__rows = 0
        self.__bytes = 0
        self.__outbox = False
        # SQLite reports database=None for the optimized COUNT(*) read. Only
        # admit that case for a known main table; virtual/shadow reads are never
        # enabled just because migration code created one earlier.
        tables = connection.execute("PRAGMA main.table_list").fetchall()
        self.__main_tables = {
            row[1] for row in tables if row[0] == "main" and row[2] in {"table", "view"}
        } | {"sqlite_master", "sqlite_schema"}
        self.__virtual_tables = {
            row[1]
            for row in tables
            if row[0] == "main" and row[2] in {"virtual", "shadow"}
        }
        connection.set_authorizer(self._authorize)
        connection.set_progress_handler(self._progress, 500)

    @property
    def storage(self):
        return self.__storage

    @property
    def limits(self):
        return self.__limits

    @property
    def mode(self):
        return self.__mode

    def _fail(self, error):
        self.__failure = error
        if isinstance(error, ApplicationRelationalStorageError):
            raise error
        raise ApplicationRelationalStorageError(
            str(error) if isinstance(error, str) else "Scoped SQLite operation refused"
        ) from (error if isinstance(error, Exception) else None)

    def _check(self):
        if not self.__active:
            raise ApplicationRelationalStorageError("Relational session is closed")
        if self.__failure is not None:
            raise ApplicationRelationalStorageError("Relational transaction has failed")
        if _expired(self.__deadline, self.__boot_deadline_ms):
            self._fail("Relational transaction deadline exceeded")
        if self.mode == "write":
            try:
                self.storage._check_auxiliary()
            except ApplicationRelationalStorageError as error:
                self._fail(error)

    def _progress(self):
        try:
            self._check()
            return 0
        except ApplicationRelationalStorageError:
            return 1

    def _authorize(self, action, first, second, database, source):
        if action == sqlite3.SQLITE_PRAGMA:
            allowed = first.lower() in _READ_PRAGMAS and database in {None, "main"}
        elif action == sqlite3.SQLITE_FUNCTION:
            allowed = (second or "").lower() in _FUNCTIONS
        elif action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}:
            allowed = True
        elif action == sqlite3.SQLITE_READ:
            allowed = first not in self.__virtual_tables and (
                (database == "main" and first in self.__main_tables)
                or (database is None and second == "" and first in self.__main_tables)
            )
        elif action in {
            sqlite3.SQLITE_INSERT,
            sqlite3.SQLITE_UPDATE,
            sqlite3.SQLITE_DELETE,
        }:
            name = (first or "").lower()
            protected = name.startswith(("three_mm_", "sqlite_"))
            allowed = (
                self.mode == "write"
                and database == "main"
                and first not in self.__virtual_tables
                and (
                    not protected
                    or (self.__outbox and name == "three_mm_outbox" and source is None)
                )
            )
        else:
            # Includes transaction control, DDL, ATTACH, DETACH, TEMP, virtual
            # tables, VACUUM, ALTER and unsafe pragmas. Never SQLITE_IGNORE.
            allowed = False
        return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY

    def _parameters(self, parameters):
        if type(parameters) is dict:
            if not all(type(key) is str for key in parameters):
                self._fail("SQLite parameter names are invalid")
            values = parameters.values()
        elif type(parameters) in {tuple, list}:
            values = parameters
        else:
            self._fail("SQLite parameters must be a tuple, list or dict")
        if len(parameters) > 999:
            self._fail("Too many SQLite parameters")
        try:
            total = 0
            for value in values:
                size = _value_bytes(value)
                if size > self.limits.max_value_bytes:
                    self._fail("SQLite value limit exceeded")
                total += size
            if total > self.limits.max_result_bytes:
                self._fail("SQLite parameter payload limit exceeded")
        except (UnicodeError, ApplicationRelationalStorageError) as error:
            self._fail(error)
        return parameters

    def _account(self, row):
        try:
            sizes = [_value_bytes(value) for value in row]
        except (UnicodeError, ApplicationRelationalStorageError) as error:
            self._fail(error)
        if any(size > self.limits.max_value_bytes for size in sizes):
            self._fail("SQLite value limit exceeded")
        self.__rows += 1
        # A framing byte per value bounds NULL/empty-column results as well.
        self.__bytes += sum(sizes) + len(sizes)
        if self.__rows > self.limits.max_result_rows:
            self._fail("Result row limit exceeded")
        if self.__bytes > self.limits.max_result_bytes:
            self._fail("Result byte limit exceeded")

    def execute(self, sql, parameters=()):
        self._check()
        try:
            if (
                type(sql) is not str
                or len(sql.encode("utf-8")) > self.limits.max_statement_bytes
            ):
                self._fail("SQLite statement limit exceeded")
            parameters = self._parameters(parameters)
            # Configure busy wait only via trusted code, before caller SQL.
            self.__connection.set_authorizer(None)
            remaining_ms = max(0, int((self.__deadline - time.monotonic()) * 1000))
            self.__connection.execute(
                f"PRAGMA busy_timeout = {min(self.limits.max_busy_ms, remaining_ms)}"
            )
            self.__connection.set_authorizer(self._authorize)
            cursor = self.__connection.execute(sql, parameters)
            self._check()
            return _BoundedCursor(self, cursor)
        except (
            sqlite3.Error,
            UnicodeError,
            ApplicationRelationalStorageError,
        ) as error:
            self._fail(error)

    def executemany(self, sql, parameters):
        self._check()
        result = _BoundedCursor(self, None)
        rowcount = 0
        try:
            if (
                type(sql) is not str
                or len(sql.encode("utf-8")) > self.limits.max_statement_bytes
            ):
                self._fail("SQLite statement limit exceeded")
            # Stream batches: each row and the whole callback share one deadline.
            for item in parameters:
                result = self.execute(sql, item)
                if result.description is not None:
                    self._fail("executemany cannot return rows")
                rowcount += max(0, result.rowcount)
            self._check()
            return result._batch_result(rowcount)
        except Exception as error:
            # Catching an input-generator error in business code must not commit
            # a partially consumed batch.
            self._fail(error)

    def _outbox_execute(self, sql, parameters):
        if self.mode != "write":
            self._fail("Outbox mutation requires a write transaction")
        self.__outbox = True
        try:
            return self.execute(sql, parameters)
        finally:
            self.__outbox = False

    def _close(self):
        self.__active = False
        self.__connection.set_authorizer(None)
        self.__connection.set_progress_handler(None, 0)

    def _prepare_commit(self):
        self._check()
        self.__connection.set_authorizer(None)
        remaining_ms = max(0, int((self.__deadline - time.monotonic()) * 1000))
        self.__connection.execute(
            f"PRAGMA busy_timeout = {min(self.limits.max_busy_ms, remaining_ms)}"
        )
        self.__connection.set_progress_handler(
            lambda: int(_expired(self.__deadline, self.__boot_deadline_ms)), 500
        )


class _OutboxWriter:
    def __init__(self, session):
        self.session = session

    def execute(self, sql, parameters):
        return self.session._outbox_execute(sql, parameters)


class ApplicationScopedStorage(ApplicationStorage):
    """Internal host-selected engine. Missing admission never grants DB access."""

    def __init__(
        self,
        data_dir: Path,
        *,
        declaration: ApplicationRelationalStorageV1,
        schema_revision: str,
        admit: Callable[[str, str, str, float], _TransactionAdmission] | None = None,
        receipts=None,
        complete=None,
    ):
        if not isinstance(data_dir, Path):
            raise ValueError("Scoped storage requires a host-supplied directory")
        self.__data_dir = data_dir
        self.__database_path = data_dir / "state.sqlite3"
        # Revalidate constructed models, not just the nominal Python type.
        self.__declaration = ApplicationRelationalStorageV1.model_validate(
            declaration.model_dump(mode="json")
        )
        from three_mm_application_sdk import REVISION_PATTERN

        if type(schema_revision) is not str or not REVISION_PATTERN.fullmatch(
            schema_revision
        ):
            raise ValueError("Application schema revision is invalid")
        self.__schema_revision = schema_revision
        self.__profile_sha256 = hashlib.sha256(
            json.dumps(
                {
                    "declaration": self.declaration.model_dump(mode="json"),
                    "schema_revision": schema_revision,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.__admit = admit
        # Internal dependencies only. Production host selection remains blocked.
        from three_mm_application_sdk.relational_receipts import _RelationalReceiptStore

        if receipts is not None and type(receipts) is not _RelationalReceiptStore:
            raise ValueError("Invalid protected receipt dependency")
        if complete is not None and (receipts is None or not callable(complete)):
            raise ValueError("Completion requires protected receipt storage")
        self.__receipts, self.__complete = receipts, complete

    @property
    def data_dir(self):
        return self.__data_dir

    @property
    def database_path(self):
        return self.__database_path

    @property
    def declaration(self):
        return self.__declaration

    @property
    def schema_revision(self):
        return self.__schema_revision

    @property
    def profile_sha256(self):
        return self.__profile_sha256

    def _connect(self):
        raise ApplicationRelationalStorageError(
            "Scoped storage cannot use raw writable connections"
        )

    def migrate(self, migrations, target_revision):
        raise ApplicationRelationalStorageError(
            "Migrations require protected host lifecycle authority"
        )

    def _check_auxiliary(self):
        total = 0
        for suffix in ("-wal", "-shm", "-journal"):
            path = self.database_path.with_name(self.database_path.name + suffix)
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ApplicationRelationalStorageError(
                    "SQLite sidecar is not an owned regular file"
                )
            total += info.st_size
        if total > self.declaration.auxiliary_pause_bytes:
            raise ApplicationRelationalStorageError(
                "SQLite auxiliary storage exceeds its pause threshold"
            )

    def _open_existing(self, mode, deadline):
        try:
            for parent in (self.data_dir, *self.data_dir.parents):
                if parent.is_symlink():
                    raise ApplicationRelationalStorageError(
                        "SQLite directory cannot be a symbolic link"
                    )
            info = self.database_path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ApplicationRelationalStorageError(
                    "SQLite database is not an owned regular file"
                )
        except OSError as error:
            raise ApplicationRelationalStorageError(
                "Application database is unavailable"
            ) from error
        connection = sqlite3.connect(
            self.database_path.absolute().as_uri()
            + ("?mode=ro" if mode == "read" else "?mode=rw"),
            uri=True,
            timeout=0,
            isolation_level=None,
            cached_statements=0,
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.enable_load_extension(False)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.setlimit(
                sqlite3.SQLITE_LIMIT_LENGTH,
                max(4096, self.declaration.max_result_bytes),
            )
            connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)
            connection.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
            connection.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 50)
            if mode == "read":
                connection.execute("PRAGMA query_only = ON")
            busy = min(
                self.declaration.max_busy_ms,
                max(0, int((deadline - time.monotonic()) * 1000)),
            )
            connection.execute(f"PRAGMA busy_timeout = {busy}")
            connection.execute("BEGIN" if mode == "read" else "BEGIN IMMEDIATE")
            applied = connection.execute(
                "SELECT revision FROM three_mm_schema_migrations ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            if applied is None or applied[0] != self.schema_revision:
                raise ApplicationRelationalStorageError(
                    "Application schema requires lifecycle recovery"
                )
            if mode == "write":
                self._check_auxiliary()
                page_size = connection.execute("PRAGMA page_size").fetchone()[0]
                page_count = connection.execute("PRAGMA page_count").fetchone()[0]
                maximum = self.declaration.max_database_bytes // page_size
                if page_count > maximum:
                    raise ApplicationRelationalStorageError(
                        "Application database exceeds its page limit"
                    )
                actual = connection.execute(
                    f"PRAGMA max_page_count = {maximum}"
                ).fetchone()[0]
                if actual != maximum:
                    raise ApplicationRelationalStorageError(
                        "SQLite page limit could not be applied"
                    )
            return connection
        except BaseException:
            connection.close()
            raise

    @contextmanager
    def _transaction(self, mode) -> Iterator[_Session]:
        if relational_transaction_active.get():
            raise ApplicationRelationalStorageError(
                "Nested relational transactions are forbidden"
            )
        if mode == "write" and self.declaration.mode != "read_write":
            raise ApplicationRelationalStorageError("Relational storage is read-only")
        if self.__admit is None:
            raise ApplicationRelationalStorageError(
                "Relational Core admission is unavailable"
            )
        transaction_id = uuid.uuid4().hex
        deadline = time.monotonic() + self.declaration.max_transaction_ms / 1000
        admission = self.__admit(transaction_id, mode, self.profile_sha256, deadline)
        if (
            type(admission) is not _TransactionAdmission
            or admission.transaction_id != transaction_id
            or admission.mode != mode
            or admission.profile_sha256 != self.profile_sha256
            or type(admission.deadline) not in {int, float}
            or not math.isfinite(admission.deadline)
            or not time.monotonic() < admission.deadline <= deadline
            or (
                admission.boot_deadline_ms is not None
                and (
                    type(admission.boot_deadline_ms) is not int
                    or admission.boot_deadline_ms < 0
                    or _expired(admission.deadline, admission.boot_deadline_ms)
                )
            )
            or (
                self.__receipts is not None
                and (
                    type(admission.permit_sha256) is not str
                    or not re.fullmatch(r"[0-9a-f]{64}", admission.permit_sha256)
                )
            )
        ):
            raise ApplicationRelationalStorageError(
                "Relational transaction admission is invalid or expired"
            )
        connection = None
        session = None
        token = None
        receipt = None
        try:
            connection = self._open_existing(mode, admission.deadline)
            if self.__receipts is not None:
                self.__receipts._validate(connection)
                if mode == "write":
                    self.__receipts._before_write(connection)
            session = _Session(
                self, connection, mode, admission.deadline, admission.boot_deadline_ms
            )
            session._check()
            token = relational_transaction_active.set(True)
            yield session
            session._prepare_commit()
            if mode == "write" and self.__receipts is not None:
                receipt = self.__receipts._insert(
                    connection, transaction_id, admission.permit_sha256
                )
                # Trusted fixed metadata work also spends the original budget.
                session._prepare_commit()
            try:
                connection.commit()
            except sqlite3.Error as error:
                # Once commit was attempted, do not invent rollback or retry.
                if mode == "write":
                    raise ApplicationRelationalExecutionUnconfirmed(
                        transaction_id
                    ) from error
                raise ApplicationRelationalStorageError(
                    "Read snapshot could not close"
                ) from error
        except BaseException as error:
            if session is not None:
                session._close()
            if connection is not None:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    if mode == "write":
                        raise ApplicationRelationalExecutionUnconfirmed(
                            transaction_id
                        ) from error
            if isinstance(error, sqlite3.Error):
                raise ApplicationRelationalStorageError(
                    "Scoped SQLite transaction could not start"
                ) from error
            if isinstance(error, ValueError):
                raise ApplicationRelationalStorageError(
                    "Receipt metadata requires lifecycle recovery"
                ) from error
            raise
        finally:
            try:
                if session is not None:
                    session._close()
                if connection is not None:
                    connection.close()
            finally:
                if token is not None:
                    relational_transaction_active.reset(token)
        if receipt is not None and self.__complete is not None:
            # Core IPC only after connection close and context/SQL unlock. A lost
            # completion ACK never executes the SQL callback again.
            try:
                self.__complete(receipt)
            except Exception as error:
                raise ApplicationRelationalExecutionUnconfirmed(
                    transaction_id
                ) from error

    def transaction(self):
        return self._transaction("write")

    def read_transaction(self):
        return self._transaction("read")

    def transaction_status(self, transaction_id, permit_sha256):
        """Own outcome metadata after revoke; no new admission or business SQL.

        Missing receipt is unknown, not rolled_back, especially after recovery.
        The supplied protected lineage/key/schema must still match the DB.
        """
        if relational_transaction_active.get() or self.__receipts is None:
            raise ApplicationRelationalStorageError("Receipt lookup is unavailable")
        connection = None
        try:
            connection = self._open_existing(
                "read", time.monotonic() + self.declaration.max_transaction_ms / 1000
            )
            return self.__receipts.lookup(connection, transaction_id, permit_sha256)
        except (sqlite3.Error, ValueError) as error:
            raise ApplicationRelationalStorageError(
                "Receipt metadata requires lifecycle recovery"
            ) from error
        finally:
            if connection is not None:
                connection.close()

    def enqueue_outbox(self, connection, **values):
        if type(connection) is not _Session or connection.storage is not self:
            raise ApplicationRelationalStorageError(
                "Outbox requires this storage's active session"
            )
        connection._check()
        try:
            json.dumps(values.get("payload"), allow_nan=False)
            super().enqueue_outbox(_OutboxWriter(connection), **values)
        except (ValueError, TypeError) as error:
            connection._fail(error)

    def update_outbox(
        self,
        outbox_id,
        *,
        state,
        attempts,
        next_attempt_at=None,
        terminal_result=None,
        last_error=None,
    ):
        if (
            state
            not in {
                "pending",
                "retrying",
                "ambiguous",
                "failed",
                "succeeded",
                "manual_review",
            }
            or type(attempts) is not int
            or attempts < 0
        ):
            raise ValueError("Outbox transition is invalid")
        with self.transaction() as session:
            changed = session._outbox_execute(
                "UPDATE three_mm_outbox SET state = ?, attempts = ?, next_attempt_at = ?, "
                "terminal_result = ?, last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE outbox_id = ?",
                (
                    state,
                    attempts,
                    next_attempt_at.isoformat() if next_attempt_at else None,
                    terminal_result,
                    last_error,
                    outbox_id,
                ),
            ).rowcount
            if changed != 1:
                session._fail("Outbox item was not found")

    def due_outbox(self, *, limit=50, now=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Outbox batch limit is invalid")
        with self.read_transaction() as session:
            rows = session.execute(
                "SELECT outbox_id, event_type, payload_json, payload_hash, remote_idempotency_key, attempts "
                "FROM three_mm_outbox WHERE state IN ('pending', 'retrying') "
                "AND (next_attempt_at IS NULL OR next_attempt_at <= ?) ORDER BY created_at, outbox_id LIMIT ?",
                ((now or datetime.now(UTC)).isoformat(), limit),
            ).fetchall()
            items = []
            for row in rows:
                payload_json, payload_hash = row[2], row[3]
                if (
                    type(payload_json) is not str
                    or hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
                    != payload_hash
                ):
                    session._fail("Outbox payload integrity check failed")
                payload = json.loads(payload_json)
                if type(payload) is not dict or type(row[4]) is not str or not row[4]:
                    session._fail("Outbox payload or idempotency identity is invalid")
                items.append(
                    ApplicationOutboxItem(
                        row[0], row[1], payload, payload_hash, row[4], row[5]
                    )
                )
            return items

    def status(self):
        with self.read_transaction() as session:
            counts = {
                row[0]: row[1]
                for row in session.execute(
                    "SELECT state, COUNT(*) FROM three_mm_outbox GROUP BY state"
                ).fetchall()
            }
            return {"revision": self.schema_revision, "outbox": counts}
