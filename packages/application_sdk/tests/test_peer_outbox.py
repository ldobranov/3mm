import sqlite3
import pytest
from packages.application_sdk import peer_outbox as outbox


def test_durable_order_capacity_and_no_rebinding(tmp_path):
    path = tmp_path / "owned.db"
    cursor = {"binding_id": "fleet", "approval": "a"*64, "sequence": 4, "checkpoint": "acknowledged"}
    conn = sqlite3.connect(path)
    outbox.create(conn)
    conn.execute("BEGIN IMMEDIATE")
    entries = [outbox.enqueue(conn, cursor) for _ in range(32)]
    with pytest.raises(ValueError, match="full"): outbox.enqueue(conn, cursor)
    conn.commit(); conn.close()
    conn = sqlite3.connect(path)
    conn.execute("BEGIN IMMEDIATE")
    assert outbox.next_intent(conn, "fleet") == entries[0]
    assert [e.sequence for e in entries] == list(range(5, 37))
    with pytest.raises(ValueError): outbox.enqueue(conn, dict(cursor, approval="b"*64))
    with pytest.raises(ValueError): outbox.acknowledge(conn, entries[1], {"status":"accepted","report_id":entries[1].report_id})
    with pytest.raises(ValueError): outbox.acknowledge(conn, entries[0], {"status":"unknown","report_id":entries[0].report_id})
    outbox.acknowledge(conn, entries[0], {"status":"accepted","report_id":entries[0].report_id})
    conn.rollback()
    assert outbox.next_intent(conn, "fleet") == entries[0]
    conn.close()


def test_missing_original_intent_never_invents_replacement(tmp_path):
    conn = sqlite3.connect(tmp_path / "owned.db")
    outbox.create(conn)
    conn.execute("BEGIN IMMEDIATE")
    with pytest.raises(ValueError, match="original"):
        outbox.enqueue(conn, {"binding_id":"fleet","approval":"b"*64,"sequence":3,"checkpoint":"unconfirmed"})
    assert outbox.next_intent(conn, "fleet") is None
    conn.close()
