"""Durable at-most-one attempt for queue-delivered capability actions.

A pending record after a crash means unknown, never permission to retry.
This cannot guarantee exactly-once effects on arbitrary physical hardware.
"""
from contextlib import closing
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Callable

from three_mm_protocol import AgentCommand, AgentCommandResult


class PhysicalCommandJournal:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = data_dir / 'physical-commands.sqlite3'
        with closing(self._connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS attempts (identity TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT)')
        os.chmod(self.path, 0o600)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute('PRAGMA synchronous=FULL')
        return db

    @staticmethod
    def _identity(command):
        return command.device_id + ':' + command.idempotency_key

    @staticmethod
    def _digest(command):
        content = {'type': command.command_type, 'payload': command.payload,
                   'created_at': command.created_at.isoformat(), 'expires_at': command.expires_at.isoformat()}
        return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

    @staticmethod
    def failed(command, state, message):
        return AgentCommandResult(command_id=command.command_id, device_id=command.device_id,
            status='failed', completed_at=datetime.now(UTC), output={'execution_state': state}, error=message)

    def execute(self, command: AgentCommand, invoke: Callable[[], dict], *,
                authorize: Callable[[], None] | None = None,
                now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> AgentCommandResult:
        identity, digest = self._identity(command), self._digest(command)
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT digest, result FROM attempts WHERE identity=?', (identity,)).fetchone()
            if previous:
                if previous[0] != digest:
                    return self.failed(command, 'conflict', 'Physical command identity has different content')
                if previous[1] is None:
                    return self.failed(command, 'unknown', 'Previous physical attempt is unresolved; automatic retry refused')
                return AgentCommandResult.model_validate_json(previous[1]).model_copy(update={'command_id': command.command_id})
            db.execute('INSERT INTO attempts VALUES (?, ?, NULL)', (identity, digest))
        # The transaction above is committed before authorization or hardware.
        if command.expires_at <= now():
            result = self.failed(command, 'not_executed', 'Physical command expired')
        else:
            try:
                if authorize is not None:
                    authorize()
            except Exception:
                result = self.failed(command, 'not_executed', 'Live execution authorization was unavailable or denied')
            else:
                if command.expires_at <= now():
                    result = self.failed(command, 'not_executed', 'Physical command expired before driver invocation')
                else:
                    try:
                        output = invoke()
                        result = AgentCommandResult(command_id=command.command_id, device_id=command.device_id,
                            status='succeeded', completed_at=now(), output={**output, 'execution_state': 'executed'})
                    except Exception:
                        result = self.failed(command, 'unknown', 'Driver outcome is unknown; automatic retry refused')
        with closing(self._connect()) as db, db:
            db.execute('UPDATE attempts SET result=? WHERE identity=? AND digest=?',
                (result.model_dump_json(), identity, digest))
        return result
