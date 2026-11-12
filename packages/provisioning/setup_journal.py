"""Bounded, secret-free setup transaction journal; survives process interruption."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


class SetupJournal:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "setup-attempt.json"

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.path.with_suffix(".lock").open("a") as lock:
            if os.name == "posix":
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                if os.name == "posix":
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        if self.path.stat().st_size > 16384:
            raise ValueError("Invalid setup journal")
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or set(value) != {"id", "previous", "wifi", "committed"}:
            raise ValueError("Invalid setup journal")
        import re
        if (not isinstance(value["id"], str) or not re.fullmatch(r"[0-9a-f]{32}", value["id"])
                or type(value["wifi"]) is not bool or type(value["committed"]) is not bool):
            raise ValueError("Invalid setup journal")
        return value

    def begin(self, identifier: str, previous, *, wifi: bool) -> None:
        atomic_json(self.path, {"id": identifier, "previous": previous.to_dict() if previous else None,
                               "wifi": wifi, "committed": False})

    def commit(self) -> None:
        value = self.load()
        if value is None:
            raise RuntimeError("Missing setup attempt")
        value["committed"] = True
        atomic_json(self.path, value)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


class SetupActivationJournal(SetupJournal):
    """Committed role handoff, separate from network/role transaction visibility."""

    def __init__(self, data_dir: Path):
        self.path = data_dir / 'setup-activation.json'

    def load(self) -> dict | None:
        value = super().load()
        if value is not None and not value['committed']:
            raise ValueError('Uncommitted setup activation')
        return value

    def handoff(self, journal: SetupJournal) -> None:
        attempt = journal.load()
        if attempt is None:
            return  # Retry after acknowledgement cannot create another intent.
        if not attempt['committed']:
            raise ValueError('Setup must commit before runtime activation')
        pending = self.load()
        if pending is not None and pending != attempt:
            raise RuntimeError('Another setup activation is pending')
        journal.path.replace(self.path)
        if os.name == 'posix':
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
