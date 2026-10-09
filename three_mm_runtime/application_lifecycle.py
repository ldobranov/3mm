"""Private helper fencing for immutable-host application lifecycle operations.

This is not an application grant. The helper checks the committed Core ticket,
serializes runtime mutations and durably consumes each ticket before effects.
The production helper's existing SQLite database is opened read-only.
"""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat


class ApplicationLifecycleError(RuntimeError):
    def __init__(self):
        super().__init__("Application lifecycle ticket is unavailable, stale or consumed")


STATUSES = {
    "activate_application_extension": "activating",
    "disable_application_extension": "disabling",
    "uninstall_application_extension": "uninstalling",
    "recover_application_extension": "recovering",
}
RELEASE_MUTATION_LOCK = Path("/run/lock/3mm-release-mutation.lock")


@contextmanager
def _release_lock(*, enforce_permissions=True):
    """Exclude install/restore/reset, whose lock survives state directory swaps."""
    import fcntl

    fd = os.open(RELEASE_MUTATION_LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or (enforce_permissions and (info.st_uid != 0 or info.st_mode & 0o022))):
            raise ApplicationLifecycleError()
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def _ticket(payload):
    ticket = payload.get("lifecycle")
    if (
        not isinstance(ticket, dict)
        or set(ticket) != {"installation_id", "module_id", "instance_id", "incarnation", "epoch", "guard_generation"}
        or type(ticket["installation_id"]) is not int or ticket["installation_id"] < 1
        or not isinstance(ticket["module_id"], str) or not 1 <= len(ticket["module_id"]) <= 255
        or any(not isinstance(ticket[key], str) or re.fullmatch(pattern, ticket[key]) is None
               for key, pattern in (("instance_id", r"[0-9a-f]{24}"),
                                    ("incarnation", r"[0-9a-f]{32}"), ("epoch", r"[0-9a-f]{32}"),
                                    ("guard_generation", r"[0-9a-f]{32}")))
        or not isinstance(payload.get("action"), str) or payload["action"] not in STATUSES
    ):
        raise ApplicationLifecycleError()
    return ticket


def _check_current(payload, ticket, database):
    # mode=ro must not create a database, initialize metadata or hold a transaction
    # across systemd/filesystem work. This helper only supports its installed DB.
    try:
        with sqlite3.connect(Path(database).absolute().as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")  # One read snapshot for guard + installation; closed below.
            guard = db.execute("SELECT generation, revision FROM core_authority_guard WHERE singleton_id = 1").fetchone()
            if (guard is None or guard["generation"] != ticket["guard_generation"]
                    or type(guard["revision"]) is not int or not 1 <= guard["revision"] <= 2**53 - 1):
                raise ApplicationLifecycleError()
            row = db.execute(
                """SELECT i.id, i.module_id, i.instance_id, i.authority_incarnation,
                          i.authority_epoch, i.status, i.enabled, i.configuration, p.sha256
                   FROM application_extension_installations i
                   JOIN module_packages p ON p.id = i.module_package_id
                   WHERE i.id = ?""", (ticket["installation_id"],),
            ).fetchone()
            if row is None or (
                row["module_id"], row["instance_id"], row["authority_incarnation"],
                row["authority_epoch"], row["status"], row["enabled"]
            ) != (
                ticket["module_id"], ticket["instance_id"], ticket["incarnation"],
                ticket["epoch"], STATUSES[payload["action"]], 0
            ):
                raise ApplicationLifecycleError()
            if payload["action"] == "activate_application_extension":
                if (row["sha256"] != payload.get("sha256")
                        or json.loads(row["configuration"]) != payload.get("configuration", {})):
                    raise ApplicationLifecycleError()
            elif payload.get("instance_id") != ticket["instance_id"]:
                raise ApplicationLifecycleError()
    except (sqlite3.Error, ValueError, TypeError) as exc:
        raise ApplicationLifecycleError() from exc
    finally:
        if "db" in locals():
            db.close()


@contextmanager
def _runtime_lock(state_root, *, enforce_permissions=True):
    # Root-owned StateDirectory, not application-writable runtime/data paths.
    # flock also serializes separate helper processes/restarts. Fail closed on
    # unsupported hosts; Windows tests explicitly replace this Linux boundary.
    import fcntl

    directory = Path(state_root)
    info = directory.lstat()
    if (not stat.S_ISDIR(info.st_mode)
            or (enforce_permissions and (info.st_uid != 0 or info.st_mode & 0o022))):
        raise ApplicationLifecycleError()
    fd = os.open(directory / "application-lifecycle.lock",
                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or (enforce_permissions and (info.st_uid != 0 or info.st_mode & 0o077))):
            raise ApplicationLifecycleError()
        # Busy is unconfirmed, never permission to overlap or replay effects.
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def _consume(ticket, payload, state_root, *, enforce_permissions=True):
    path = Path(state_root) / f"lifecycle-{ticket['instance_id']}.json"
    token = {key: ticket[key] for key in ("incarnation", "epoch")}
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 4096
                or (enforce_permissions and os.name == "posix"
                    and (info.st_uid != 0 or info.st_mode & 0o077))):
            raise ApplicationLifecycleError()
        with path.open("rb") as source:
            previous = json.loads(source.read(4097))
        if (not isinstance(previous, dict)
                or set(previous) != {"incarnation", "epoch", "request_digest"}
                or any(not isinstance(previous[key], str)
                       or re.fullmatch(pattern, previous[key]) is None
                       for key, pattern in (("incarnation", r"[0-9a-f]{32}"),
                                            ("epoch", r"[0-9a-f]{32}"),
                                            ("request_digest", r"[0-9a-f]{64}")))):
            raise ApplicationLifecycleError()
        if all(previous[key] == value for key, value in token.items()):
            raise ApplicationLifecycleError()
    # Store no configuration values/credentials, only a digest and private IDs.
    token["request_digest"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()
    temporary = path.with_suffix(f".{ticket['epoch']}.tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as output:
            json.dump(token, output, separators=(",", ":"))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        if os.name == "posix":
            directory_fd = os.open(state_root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def application_lifecycle_operation(payload, *, database, state_root, enforce_permissions=True):
    """No helper effect without a fresh ticket and a durable one-use receipt."""
    ticket = _ticket(payload)
    try:
        with _release_lock(enforce_permissions=enforce_permissions), _runtime_lock(
            state_root, enforce_permissions=enforce_permissions
        ):
            _check_current(payload, ticket, database)
            _consume(ticket, payload, state_root, enforce_permissions=enforce_permissions)
            yield
    except (OSError, ValueError, TypeError) as exc:
        raise ApplicationLifecycleError() from exc
