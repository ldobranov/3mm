"""Explicit CAP12 loopback-only acceptance lab. No Core or application access."""

import argparse
from contextlib import closing, nullcontext
from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid

from three_mm_platform_wire import remaining
from three_mm_protocol.public_webhooks import (
    MAX_WEBHOOK_BYTES, WebhookRejected, valid_webhook_event_id, validate_webhook_endpoint, verify_webhook,
)

LOOPBACK = "127.0.0.1"
ROUTE = "/webhook"
DATABASE = "webhook-inbox.sqlite3"
MAX_RECEIPTS = 4096
MAX_RETAINED_BODIES = 128
BODY_RETENTION_SECONDS = 3600
REQUEST_SECONDS = 3
_APPLICATION_ID = 0x334D5731  # 3MW1; this is not the Core database.
_SCHEMA_VERSION = 4
_SIGNED_HEADERS = ("X-3mm-Webhook-Id", "X-3mm-Webhook-Timestamp", "X-3mm-Webhook-Signature")
_RECEIPT_ID = re.compile(r"[0-9a-f]{32}")
_TERMINAL_STATES = frozenset({"delivered", "rejected", "not_dispatched"})


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    receipt_id: str
    attempt_id: str
    status: str


def _retention_now():
    return int(time.time())


class WebhookInbox:
    def __init__(self, state_dir: Path, audience: str, binding_sha256: str | None):
        self.path = state_dir / DATABASE
        self._endpoint = (audience, binding_sha256)
        if not state_dir.is_dir() or self.path.is_symlink():
            raise ValueError("Use a private lab state directory")
        try:
            self.path.touch(mode=0o600, exist_ok=False)
        except FileExistsError:
            if not self.path.is_file():
                raise ValueError("Invalid lab database") from None

        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            identity = db.execute("PRAGMA application_id").fetchone()[0]
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if (identity, version) == (0, 0) and not db.execute(
                "SELECT 1 FROM sqlite_schema LIMIT 1"
            ).fetchone():
                db.execute("CREATE TABLE endpoint (audience TEXT NOT NULL, binding_sha256 TEXT)")
                db.execute("INSERT INTO endpoint VALUES (?, ?)", (audience, binding_sha256))
                db.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
            elif identity != _APPLICATION_ID or version not in (2, 3, _SCHEMA_VERSION) or not self._matches_endpoint(db):
                raise ValueError("Lab database does not match this endpoint or schema")
            if version in (0, 2):
                db.execute("""CREATE TABLE delivery_attempts (
                    receipt_id TEXT PRIMARY KEY NOT NULL,
                    attempt_id TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('unconfirmed','delivered','rejected','not_dispatched'))
                )""")
            if version != _SCHEMA_VERSION:
                self._upgrade_receipts(db, version)
                db.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

    @staticmethod
    def _upgrade_receipts(db, version):
        if version:
            db.execute("ALTER TABLE receipts RENAME TO receipts_before_retention")
        db.execute("""CREATE TABLE receipts (
            event_id TEXT PRIMARY KEY NOT NULL,
            receipt_id TEXT UNIQUE NOT NULL,
            body_sha256 TEXT NOT NULL,
            body BLOB,
            body_expires_at INTEGER NOT NULL
        )""")
        if version:
            # Old receipts have no timestamps. Give pending bodies one bounded
            # window from upgrade; completed attempts no longer need raw bytes.
            db.execute("""INSERT INTO receipts
                SELECT old.event_id, old.receipt_id, old.body_sha256,
                       CASE WHEN attempt.status <> 'unconfirmed' THEN NULL ELSE old.body END, ?
                FROM receipts_before_retention AS old
                LEFT JOIN delivery_attempts AS attempt ON attempt.receipt_id = old.receipt_id""",
                (_retention_now() + BODY_RETENTION_SECONDS,))
            db.execute("DROP TABLE receipts_before_retention")
        db.execute("CREATE INDEX retained_webhook_bodies ON receipts(body_expires_at) WHERE body IS NOT NULL")

    def _matches_endpoint(self, db):
        return db.execute("SELECT audience, binding_sha256 FROM endpoint LIMIT 2").fetchall() == [self._endpoint]

    def _connect(self):
        db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, isolation_level=None, timeout=0.25)
        try:
            db.execute("PRAGMA synchronous = FULL")
            db.execute("PRAGMA secure_delete = ON")
        except sqlite3.Error:
            db.close()
            raise
        return db

    @staticmethod
    def _prune_expired(db, now):
        return db.execute("UPDATE receipts SET body = NULL WHERE body IS NOT NULL AND body_expires_at <= ?",
                          (now,)).rowcount

    def prune_expired(self):
        """Local maintenance for an idle lab; retains every receipt and attempt."""
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if not self._matches_endpoint(db):
                raise WebhookRejected("Webhook inbox is unavailable")
            return self._prune_expired(db, _retention_now())

    def accept(self, proof, body):
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if proof.audience != self._endpoint[0] or not self._matches_endpoint(db):
                raise WebhookRejected("Webhook inbox is unavailable")
            now = _retention_now()
            self._prune_expired(db, now)
            existing = db.execute(
                "SELECT receipt_id, body_sha256 FROM receipts WHERE event_id = ?", (proof.event_id,),
            ).fetchone()
            if existing:
                return (202, existing[0]) if existing[1] == proof.body_sha256 else (409, None)
            if (db.execute("SELECT count(*) FROM receipts").fetchone()[0] >= MAX_RECEIPTS
                    or db.execute("SELECT count(*) FROM receipts WHERE body IS NOT NULL").fetchone()[0]
                    >= MAX_RETAINED_BODIES):
                return 503, None
            receipt = uuid.uuid4().hex
            db.execute("INSERT INTO receipts VALUES (?, ?, ?, ?, ?)",
                       (proof.event_id, receipt, proof.body_sha256, body, now + BODY_RETENTION_SECONDS))
            # The connection context commits before accept() returns to the HTTP handler.
            return 202, receipt

    def claim_delivery(self, receipt_id, binding_sha256):
        if not isinstance(receipt_id, str) or _RECEIPT_ID.fullmatch(receipt_id) is None:
            raise WebhookRejected("Webhook receipt is unavailable")
        return self._claim_delivery(receipt_id, binding_sha256)

    def claim_next_delivery(self, binding_sha256):
        """Select and durably reserve the oldest unattempted body in one transaction."""
        return self._claim_delivery(None, binding_sha256)

    def _claim_delivery(self, receipt_id, binding_sha256):
        if binding_sha256 is None or self._endpoint[1] != binding_sha256:
            raise WebhookRejected("Webhook receipt is unavailable")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if not self._matches_endpoint(db):
                raise WebhookRejected("Webhook receipt is unavailable")
            self._prune_expired(db, _retention_now())
            if receipt_id is None:
                candidate = db.execute("""SELECT r.receipt_id FROM receipts AS r
                    WHERE r.body IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM delivery_attempts AS a WHERE a.receipt_id = r.receipt_id
                    ) ORDER BY r.body_expires_at, r.rowid LIMIT 1""").fetchone()
                if candidate is None:
                    return None
                receipt_id = candidate[0]
                if not isinstance(receipt_id, str) or _RECEIPT_ID.fullmatch(receipt_id) is None:
                    raise WebhookRejected("Webhook receipt is unavailable")
            else:
                row = db.execute("SELECT attempt_id, status FROM delivery_attempts WHERE receipt_id = ?",
                                 (receipt_id,)).fetchone()
                if row is not None:
                    return DeliveryAttempt(receipt_id, *row), None
            stored = db.execute("""SELECT event_id, body_sha256, body FROM receipts
                WHERE receipt_id = ? AND length(event_id) <= 128 AND length(body_sha256) = 64
                AND typeof(body) = 'blob' AND length(body) BETWEEN 1 AND ?""",
                (receipt_id, MAX_WEBHOOK_BYTES)).fetchone()
            if (stored is not None and valid_webhook_event_id(stored[0])
                    and hashlib.sha256(stored[2]).hexdigest() == stored[1]):
                attempt = DeliveryAttempt(receipt_id, uuid.uuid4().hex, "unconfirmed")
                db.execute("INSERT INTO delivery_attempts VALUES (?, ?, ?)",
                           (attempt.receipt_id, attempt.attempt_id, attempt.status))
                return attempt, (stored[0], stored[2])
        # Commit expiry even when the requested payload could not be claimed.
        raise WebhookRejected("Webhook receipt is unavailable")

    def finish_delivery(self, attempt, status):
        if status not in _TERMINAL_STATES:
            raise ValueError("Invalid webhook outcome")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if not self._matches_endpoint(db) or db.execute("""UPDATE delivery_attempts SET status = ?
                WHERE receipt_id = ? AND attempt_id = ? AND status = 'unconfirmed'""",
                (status, attempt.receipt_id, attempt.attempt_id)).rowcount != 1:
                raise WebhookRejected("Webhook attempt is unavailable")
            db.execute("UPDATE receipts SET body = NULL WHERE receipt_id = ?", (attempt.receipt_id,))
        return DeliveryAttempt(attempt.receipt_id, attempt.attempt_id, status)


class _DeadlineReader(io.RawIOBase):
    def __init__(self, connection):
        self.connection = connection
        self.deadline = time.monotonic() + REQUEST_SECONDS

    def readable(self):
        return True

    def readinto(self, buffer):
        self.connection.settimeout(remaining(self.deadline))
        return self.connection.recv_into(buffer)


class WebhookLabHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "3mm-Webhook-Lab"
    sys_version = ""

    def setup(self):
        super().setup()
        self.rfile.close()
        self.rfile = io.BufferedReader(_DeadlineReader(self.connection))

    def log_message(self, format, *args):
        pass

    def _reply(self, status, receipt=None):
        self.close_connection = True
        payload = {"status": "accepted", "receipt_id": receipt} if receipt else {"status": "refused"}
        body = json.dumps(payload, separators=(",", ":")).encode("ascii")
        try:
            self.connection.settimeout(1)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except OSError:
            # A dropped acknowledgement does not undo a committed receipt.
            pass

    def send_error(self, code, message=None, explain=None):
        self._reply(code)

    def handle_expect_100(self):
        self._reply(417)
        return False

    def do_POST(self):
        server = self.server
        if self.path != server.route or self.requestline.split()[1] != server.route:
            return self._reply(404)
        if (self.headers.defects or self.headers.get_all("Host", []) != [server.authority]
                or any(name in self.headers for name in ("Origin", "Cookie", "Authorization",
                                                         "Transfer-Encoding", "Content-Encoding"))):
            return self._reply(400)
        if "Expect" in self.headers:
            return self._reply(417)
        if self.headers.get_all("Content-Type", []) != ["application/octet-stream"]:
            return self._reply(415)
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not re.fullmatch(r"[1-9][0-9]{0,9}", lengths[0]):
            return self._reply(400)
        length = int(lengths[0])
        if length > MAX_WEBHOOK_BYTES:
            return self._reply(413)
        fields = [self.headers.get_all(name, []) for name in _SIGNED_HEADERS]
        if any(len(values) != 1 for values in fields):
            return self._reply(400)
        event_id, timestamp, signature = (values[0] for values in fields)
        try:
            body = self.rfile.read(length)
        except TimeoutError:
            return self._reply(408)
        except OSError:
            return self._reply(400)
        if len(body) != length:
            return self._reply(400)
        try:
            proof = verify_webhook(body, audience=server.audience, event_id=event_id,
                                   timestamp=timestamp, signature=signature, secret=server.secret,
                                   now=int(time.time()))
        except WebhookRejected:
            return self._reply(403)
        try:
            with server.admission.hold() if server.admission is not None else nullcontext():
                status, receipt = server.inbox.accept(proof, body)
        except WebhookRejected:
            return self._reply(403)
        except sqlite3.Error:
            return self._reply(503)
        self._reply(status, receipt)


class WebhookLabServer(HTTPServer):
    def __init__(self, state_dir: Path, audience: str, secret: bytes, port: int = 0, *, admission=None):
        validate_webhook_endpoint(audience, secret)
        binding = None
        if admission is not None:
            binding = admission.binding_sha256
            if admission.audience != audience or re.fullmatch(r"[0-9a-f]{64}", binding) is None:
                raise ValueError("Lab authority does not match this endpoint")
        self.inbox = WebhookInbox(state_dir.resolve(), audience, binding)
        self.admission = admission
        self.route = admission.path if admission is not None else ROUTE
        self.audience = audience
        self.secret = secret
        # A single worker and fixed IPv4 loopback: no wildcard, TLS or reverse proxy.
        super().__init__((LOOPBACK, port), WebhookLabHandler)
        self.authority = f"{LOOPBACK}:{self.server_port}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--audience", required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        with args.key_file.open("rb") as stream:
            secret = stream.read(33)
        server = WebhookLabServer(args.state_dir, args.audience, secret, args.port)
    except (OSError, ValueError, sqlite3.Error, OverflowError):
        parser.exit(1, "Cannot start webhook lab. Check private state, endpoint and key configuration.\n")
    with server:
        print(f"CAP12 lab: http://{server.authority}{ROUTE}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
