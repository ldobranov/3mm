"""Opt-in, application-owned SQLite queue for reviewed status-report intents.

Use create() in an application migration, and enqueue()/acknowledge() in its
own write transactions. Never hold a transaction during transport. No worker,
ambient credentials, destination URLs, arbitrary payloads or automatic replay.
"""
import re
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ReportIntent:
    binding_id: str
    approval: str
    sequence: int
    report_id: str

    def send(self, client):
        return client.send_reviewed_status(self.binding_id, approval=self.approval,
                                           sequence=self.sequence, report_id=self.report_id)


def create(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS sdk_peer_report_outbox_v1 (
        binding_id TEXT NOT NULL, approval TEXT NOT NULL, sequence INTEGER NOT NULL,
        report_id TEXT NOT NULL UNIQUE, PRIMARY KEY(binding_id, sequence))""")
    connection.execute("""CREATE TABLE IF NOT EXISTS sdk_peer_report_cursor_v1
        (binding_id TEXT PRIMARY KEY, approval TEXT NOT NULL, sequence INTEGER NOT NULL)""")


def next_intent(connection, binding_id):
    row = connection.execute("""SELECT binding_id, approval, sequence, report_id
        FROM sdk_peer_report_outbox_v1 WHERE binding_id=? ORDER BY sequence LIMIT 1""", (binding_id,)).fetchone()
    return ReportIntent(*row) if row is not None else None


def enqueue(connection, checkpoint):
    """A previously observed approval is safe offline: Core rechecks it on every send."""
    binding, approval, cursor = (checkpoint[k] for k in ("binding_id", "approval", "sequence"))
    if (not connection.in_transaction or not isinstance(binding, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,95}", binding)
            or not isinstance(approval, str) or not re.fullmatch(r"[0-9a-f]{64}", approval)
            or type(cursor) is not int or not 0 <= cursor < 2**53-1):
        raise ValueError("A write transaction and an exact Core checkpoint are required")
    head = next_intent(connection, binding)
    if head and head.approval != approval:
        raise ValueError("Queued work belongs to a different approval; never silently rebind it")
    if not head and checkpoint.get("checkpoint") not in {"acknowledged", "no_sample"}:
        raise ValueError("Resolve the outstanding original report first")
    count, highest = connection.execute("SELECT COUNT(*),MAX(sequence) FROM sdk_peer_report_outbox_v1 WHERE binding_id=?",
                                        (binding,)).fetchone()
    total, = connection.execute("SELECT COUNT(*) FROM sdk_peer_report_outbox_v1").fetchone()
    if count >= 32 or total >= 128:
        raise ValueError("Peer report queue is full; no pending intent was dropped")
    local = connection.execute("SELECT approval, sequence FROM sdk_peer_report_cursor_v1 WHERE binding_id=?", (binding,)).fetchone()
    if not local:
        if connection.execute("SELECT COUNT(*) FROM sdk_peer_report_cursor_v1").fetchone()[0] >= 128:
            raise ValueError("Peer report cursor budget reached")
        connection.execute("INSERT INTO sdk_peer_report_cursor_v1 VALUES (?,?,?)", (binding, approval, cursor))
    sequence = max(highest or 0, cursor, local[1] if local and local[0] == approval else 0) + 1
    if sequence >= 2**53:
        raise ValueError("Peer report sequence exhausted")
    intent = ReportIntent(binding, approval, sequence, "report_" + uuid.uuid4().hex)
    connection.execute("INSERT INTO sdk_peer_report_outbox_v1 VALUES (?,?,?,?)",
                       (binding, approval, sequence, intent.report_id))
    return intent


def acknowledge(connection, intent, result):
    if (not connection.in_transaction or not isinstance(intent, ReportIntent) or not isinstance(result, dict)
            or result.get("status") != "accepted" or result.get("report_id") != intent.report_id
            or next_intent(connection, intent.binding_id) != intent):
        raise ValueError("Only the acknowledged head of this queue can advance")
    connection.execute("DELETE FROM sdk_peer_report_outbox_v1 WHERE binding_id=? AND approval=? AND sequence=? AND report_id=?",
                       (intent.binding_id, intent.approval, intent.sequence, intent.report_id))
    connection.execute("UPDATE sdk_peer_report_cursor_v1 SET approval=?, sequence=? WHERE binding_id=?",
                       (intent.approval, intent.sequence, intent.binding_id))


def discard_reviewed(connection, intent):
    """Explicit app-owner cleanup after withdrawal. Cannot cancel an in-flight report."""
    if not connection.in_transaction or not isinstance(intent, ReportIntent) or next_intent(connection, intent.binding_id) != intent:
        raise ValueError("Review the original queued head first")
    connection.execute("DELETE FROM sdk_peer_report_outbox_v1 WHERE binding_id=? AND approval=?",
                       (intent.binding_id, intent.approval))
