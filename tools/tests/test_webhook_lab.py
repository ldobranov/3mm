from contextlib import closing, contextmanager
import hashlib
import hmac
import http.client
import json
import queue
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

import pytest

from tools import webhook_lab as lab
from packages.protocol.public_webhooks import WebhookRejected


AUDIENCE = "89abcdef0123456789abcdef01234567"
KEY = bytes(range(32))
BODY = b"original bytes\x00\xff\r\n"
EVENT = "delivery-1"


@contextmanager
def server(directory, *, key=KEY, admission=None):
    with lab.WebhookLabServer(directory, AUDIENCE, key, admission=admission) as listener:
        worker = threading.Thread(target=listener.serve_forever, kwargs={"poll_interval": 0.01})
        worker.start()
        try:
            yield listener
        finally:
            listener.shutdown()
            worker.join(timeout=5)
            assert not worker.is_alive()


def headers(body, event_id=EVENT, *, timestamp=None, key=KEY):
    timestamp = int(time.time()) if timestamp is None else timestamp
    prefix = f"3mm.webhook.v1\nPOST\n{AUDIENCE}\n{timestamp}\n{event_id}\n".encode("ascii")
    return {
        "Content-Type": "application/octet-stream",
        "X-3mm-Webhook-Id": event_id,
        "X-3mm-Webhook-Timestamp": str(timestamp),
        "X-3mm-Webhook-Signature": "v1=" + hmac.digest(key, prefix + body, "sha256").hex(),
    }


def post(listener, body=BODY, **kwargs):
    return post_at(listener.server_address, body, path=listener.route, **kwargs)


def post_at(address, body=BODY, *, event_id=EVENT, timestamp=None, key=KEY, path=lab.ROUTE):
    with closing(http.client.HTTPConnection(*address, timeout=5)) as client:
        client.request("POST", path, body, headers(body, event_id, timestamp=timestamp, key=key))
        with client.getresponse() as response:
            return response.status, json.loads(response.read())


def raw_post(listener, lines, *, body=b"", path=lab.ROUTE, send_eof=True):
    with socket.create_connection(listener.server_address, timeout=5) as connection:
        start = [f"POST {path} HTTP/1.1", f"Host: {listener.authority}"]
        connection.sendall(("\r\n".join(start + lines) + "\r\n\r\n").encode("ascii") + body)
        if send_eof:
            connection.shutdown(socket.SHUT_WR)
        with http.client.HTTPResponse(connection) as response:
            response.begin()
            return response.status, json.loads(response.read())


def rows(directory):
    with closing(sqlite3.connect(directory / lab.DATABASE)) as db:
        return db.execute(
            "SELECT event_id, receipt_id, body_sha256, body FROM receipts ORDER BY event_id",
        ).fetchall()


def test_commit_before_ack_and_same_receipt_after_restart(tmp_path):
    with server(tmp_path) as listener:
        assert listener.server_address[0] == "127.0.0.1"
        status, response = post(listener, timestamp=int(time.time()) - 10)
        assert status == 202
        expected = [(EVENT, response["receipt_id"], hashlib.sha256(BODY).hexdigest(), BODY)]
        assert rows(tmp_path) == expected
    with server(tmp_path) as listener:
        assert post(listener) == (202, response)
        assert post(listener, BODY + b"!") == (409, {"status": "refused"})
        assert rows(tmp_path) == expected


def test_upgrade_v2_reviewed_inbox_preserves_receipts_and_fences_attempts(tmp_path):
    binding = "a" * 64
    receipt_id = "1" * 32
    stored = (EVENT, receipt_id, hashlib.sha256(BODY).hexdigest(), BODY)
    with closing(sqlite3.connect(tmp_path / lab.DATABASE)) as db, db:
        db.execute(f"PRAGMA application_id = {lab._APPLICATION_ID}")
        db.execute("PRAGMA user_version = 2")
        db.execute("CREATE TABLE endpoint (audience TEXT NOT NULL, binding_sha256 TEXT)")
        db.execute("INSERT INTO endpoint VALUES (?, ?)", (AUDIENCE, binding))
        db.execute("""CREATE TABLE receipts (event_id TEXT PRIMARY KEY NOT NULL, receipt_id TEXT NOT NULL,
                    body_sha256 TEXT NOT NULL, body BLOB NOT NULL)""")
        db.execute("INSERT INTO receipts VALUES (?, ?, ?, ?)", stored)
    with pytest.raises(ValueError, match="does not match"):
        lab.WebhookInbox(tmp_path, AUDIENCE, "b" * 64)
    inbox = lab.WebhookInbox(tmp_path, AUDIENCE, binding)
    assert rows(tmp_path) == [stored]
    attempt, payload = inbox.claim_delivery(receipt_id, binding)
    assert (attempt.status, payload) == ("unconfirmed", (EVENT, BODY))
    with pytest.raises(WebhookRejected):
        inbox.claim_delivery(receipt_id, "b" * 64)
    confirmed = inbox.finish_delivery(attempt, "delivered")
    with pytest.raises(WebhookRejected):
        inbox.finish_delivery(attempt, "rejected")
    reopened = lab.WebhookInbox(tmp_path, AUDIENCE, binding)
    assert reopened.claim_delivery(receipt_id, binding) == (confirmed, None)
    assert rows(tmp_path) == [(*stored[:3], None)]


def test_upgrade_v3_keeps_completed_and_unconfirmed_attempts(tmp_path, monkeypatch):
    binding = "a" * 64
    digest = hashlib.sha256(BODY).hexdigest()
    now = int(time.time())
    monkeypatch.setattr(lab, "_retention_now", lambda: now)
    finished = lab.DeliveryAttempt("1" * 32, "a" * 32, "delivered")
    uncertain = lab.DeliveryAttempt("2" * 32, "b" * 32, "unconfirmed")
    with closing(sqlite3.connect(tmp_path / lab.DATABASE)) as db, db:
        db.execute(f"PRAGMA application_id = {lab._APPLICATION_ID}")
        db.execute("PRAGMA user_version = 3")
        db.execute("CREATE TABLE endpoint (audience TEXT NOT NULL, binding_sha256 TEXT)")
        db.execute("INSERT INTO endpoint VALUES (?, ?)", (AUDIENCE, binding))
        db.execute("""CREATE TABLE receipts (event_id TEXT PRIMARY KEY NOT NULL, receipt_id TEXT NOT NULL,
                    body_sha256 TEXT NOT NULL, body BLOB NOT NULL)""")
        db.execute("CREATE UNIQUE INDEX receipts_by_id ON receipts(receipt_id)")
        db.execute("""CREATE TABLE delivery_attempts (receipt_id TEXT PRIMARY KEY NOT NULL,
                    attempt_id TEXT UNIQUE NOT NULL, status TEXT NOT NULL)""")
        for event, attempt in (("done", finished), ("waiting", uncertain)):
            db.execute("INSERT INTO receipts VALUES (?, ?, ?, ?)", (event, attempt.receipt_id, digest, BODY))
            db.execute("INSERT INTO delivery_attempts VALUES (?, ?, ?)",
                       (attempt.receipt_id, attempt.attempt_id, attempt.status))
    with pytest.raises(ValueError, match="does not match"):
        lab.WebhookInbox(tmp_path, AUDIENCE, "b" * 64)
    assert [row[3] for row in rows(tmp_path)] == [BODY, BODY]
    inbox = lab.WebhookInbox(tmp_path, AUDIENCE, binding)
    assert [row[3] for row in rows(tmp_path)] == [None, BODY]
    assert inbox.claim_delivery(finished.receipt_id, binding) == (finished, None)
    now += lab.BODY_RETENTION_SECONDS
    assert inbox.prune_expired() == 1
    assert inbox.prune_expired() == 0
    assert inbox.claim_delivery(uncertain.receipt_id, binding) == (uncertain, None)
    assert [row[3] for row in rows(tmp_path)] == [None, None]


def test_expiry_frees_payload_space_without_evicting_deduplication(tmp_path, monkeypatch):
    now = int(time.time())
    monkeypatch.setattr(lab, "_retention_now", lambda: now)
    monkeypatch.setattr(lab, "MAX_RETAINED_BODIES", 1)
    monkeypatch.setattr(lab, "MAX_RECEIPTS", 2)
    with server(tmp_path) as listener:
        original = post(listener)
        assert original[0] == 202
        now += lab.BODY_RETENTION_SECONDS - 1
        assert post(listener) == original
        assert post(listener, event_id="next-event")[0] == 503
        now += 1
        assert post(listener, key=bytes(reversed(KEY)))[0] == 403
        assert rows(tmp_path)[0][3] == BODY  # Unverified input cannot change state.
        assert post(listener, event_id="next-event")[0] == 202
        assert rows(tmp_path)[0][3] is None
        assert post(listener) == original
        assert post(listener, BODY + b"!")[0] == 409
    with server(tmp_path) as listener:
        now += lab.BODY_RETENTION_SECONDS
        assert post(listener, event_id="capacity-exhausted")[0] == 503
        assert [row[3] for row in rows(tmp_path)] == [None, None]
        assert post(listener) == original


@contextmanager
def cli_listener(directory, key_file):
    with subprocess.Popen(
        [sys.executable, "-m", "tools.webhook_lab", "--state-dir", str(directory),
         "--audience", AUDIENCE, "--key-file", str(key_file)],
        stdout=subprocess.PIPE, text=True,
    ) as child:
        startup = queue.Queue()
        reader = threading.Thread(target=lambda: startup.put(child.stdout.readline()))
        reader.start()
        try:
            line = startup.get(timeout=15)
            assert line.startswith("CAP12 lab: ")
            endpoint = urlsplit(line.removeprefix("CAP12 lab: ").strip())
            assert (endpoint.scheme, endpoint.hostname, endpoint.path) == ("http", "127.0.0.1", lab.ROUTE)
            yield endpoint.hostname, endpoint.port
        finally:
            # End only the test-owned process; the next process has no shared memory.
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)
            reader.join(timeout=5)


def test_command_line_receipt_survives_process_termination(tmp_path):
    key_file = tmp_path / "synthetic.key"
    key_file.write_bytes(KEY)
    with cli_listener(tmp_path, key_file) as address:
        first = post_at(address, timestamp=int(time.time()) - 10)
        assert first[0] == 202
    with cli_listener(tmp_path, key_file) as address:
        assert post_at(address) == first
    assert len(rows(tmp_path)) == 1


def test_no_receipt_for_invalid_expired_or_rotated_signature(tmp_path):
    other_key = bytes(reversed(KEY))
    with server(tmp_path) as listener:
        assert post(listener, key=other_key)[0] == 403
        assert post(listener, timestamp=int(time.time()) - 301)[0] == 403
        assert rows(tmp_path) == []
        original = post(listener)
        assert original[0] == 202
    with server(tmp_path, key=other_key) as listener:
        assert post(listener)[0] == 403
        assert post(listener, key=other_key) == original
        assert len(rows(tmp_path)) == 1


def test_lost_ack_can_be_recovered_without_second_insert(tmp_path, monkeypatch):
    reply = lab.WebhookLabHandler._reply

    def lose_ack(handler, status, receipt=None):
        if status == 202:
            handler.close_connection = True
        else:
            reply(handler, status, receipt)

    with monkeypatch.context() as change:
        change.setattr(lab.WebhookLabHandler, "_reply", lose_ack)
        with server(tmp_path) as listener:
            with pytest.raises(http.client.RemoteDisconnected):
                post(listener)
    expected = rows(tmp_path)
    assert len(expected) == 1
    with server(tmp_path) as listener:
        assert post(listener) == (202, {"status": "accepted", "receipt_id": expected[0][1]})
    assert rows(tmp_path) == expected


def test_sqlite_commit_failure_does_not_acknowledge_or_leave_partial_row(tmp_path):
    with server(tmp_path) as listener:
        with closing(sqlite3.connect(tmp_path / lab.DATABASE, isolation_level=None)) as reader:
            reader.execute("BEGIN")
            reader.execute("SELECT count(*) FROM receipts").fetchone()  # Hold the shared lock.
            assert post(listener) == (503, {"status": "refused"})
            reader.execute("ROLLBACK")
        assert rows(tmp_path) == []
        assert post(listener)[0] == 202


def test_full_inbox_still_resolves_original_receipt_without_evicting(tmp_path, monkeypatch):
    monkeypatch.setattr(lab, "MAX_RECEIPTS", 1)
    with server(tmp_path) as listener:
        original = post(listener)
        assert original[0] == 202
        assert post(listener, event_id="another-event")[0] == 503
        assert post(listener) == original
        assert post(listener, b"different bytes")[0] == 409
    assert len(rows(tmp_path)) == 1


@pytest.mark.parametrize("extra,expected", [
    (["Host: external.example"], 400),
    (["X-3mm-Webhook-Signature: ambiguous"], 400),
    (["X-3mm-Webhook-Timestamp: 123"], 400),
    (["X-3mm-Webhook-Id: duplicate"], 400),
    (["Content-Length: 1", "Content-Length: 1"], 400),
    (["Content-Length: 1", "Transfer-Encoding: chunked"], 400),
    (["Content-Length: 1", "Content-Encoding: gzip"], 400),
    (["Content-Length: 1", "Cookie: no"], 400),
    (["Content-Length: 1", "Origin: http://localhost"], 400),
    (["Content-Length: 1", "Authorization: no"], 400),
    (["Content-Length: 1", "Expect: 100-continue"], 417),
    (["Content-Length: 65537"], 413),
    (["Content-Length: 1"], 400),  # EOF without the declared byte.
])
def test_invalid_framing_is_rejected_without_record(tmp_path, extra, expected):
    framing = [f"{name}: {value}" for name, value in headers(BODY).items()]
    with server(tmp_path) as listener:
        assert raw_post(listener, framing + extra)[0] == expected
    assert rows(tmp_path) == []


def test_body_wait_is_bounded_and_other_paths_are_not_served(tmp_path, monkeypatch):
    monkeypatch.setattr(lab, "REQUEST_SECONDS", 0.3)
    framing = [f"{name}: {value}" for name, value in headers(BODY).items()]
    framing += [f"Content-Length: {len(BODY)}"]
    with server(tmp_path) as listener:
        for path in ("/api", "//webhook", "/webhook?x=1", "/%77ebhook"):
            assert raw_post(listener, framing, body=BODY, path=path)[0] == 404
        assert raw_post(listener, framing, body=BODY[:1], send_eof=False)[0] == 408
        assert rows(tmp_path) == []
        assert post(listener)[0] == 202


def test_inbox_will_not_be_reused_for_another_audience_or_database(tmp_path):
    path = tmp_path / lab.DATABASE
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE unrelated (data TEXT)")
        db.execute("INSERT INTO unrelated VALUES ('keep')")
    with pytest.raises(ValueError, match="does not match"):
        lab.WebhookLabServer(tmp_path, AUDIENCE, KEY)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT data FROM unrelated").fetchall() == [("keep",)]
    clean = tmp_path / "clean"
    clean.mkdir()
    with server(clean) as listener:
        assert post(listener)[0] == 202
    with pytest.raises(ValueError, match="does not match"):
        lab.WebhookLabServer(clean, "0" * 32, KEY)
    assert len(rows(clean)) == 1


def test_old_disposable_lab_schema_is_not_migrated_or_reset(tmp_path):
    path = tmp_path / lab.DATABASE
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(f"PRAGMA application_id = {lab._APPLICATION_ID}")
        db.execute("PRAGMA user_version = 1")
        db.execute("CREATE TABLE endpoint (audience TEXT NOT NULL)")
        db.execute("INSERT INTO endpoint VALUES (?)", (AUDIENCE,))
    with pytest.raises(ValueError, match="does not match"):
        lab.WebhookLabServer(tmp_path, AUDIENCE, KEY)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (1,)
        assert db.execute("SELECT * FROM endpoint").fetchall() == [(AUDIENCE,)]
