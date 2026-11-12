"""Synthetic CAP12 receiver, packaged only by the native host integration test."""

from base64 import b64decode

from packages.application_sdk import ApplicationMigration


def _migration(db):
    db.execute("CREATE TABLE received (receipt_id TEXT NOT NULL, event_id TEXT NOT NULL, body BLOB NOT NULL)")


def get_migrations():
    return [ApplicationMigration("0001", _migration)]


class Receiver:
    def __init__(self, application):
        self.storage = application.storage

    def handle(self, operation_id, payload, context):
        if operation_id == "health" and context.audience == "internal":
            return {"status": "ready"}
        if (operation_id != "receive_event" or context.audience != "internal" or context.actor.kind != "service"
                or set(payload) != {"receipt_id", "event_id", "body_base64"}
                or context.idempotency_key != payload["receipt_id"]):
            raise ValueError("Unexpected receiver invocation")
        body = b64decode(payload["body_base64"], validate=True)
        if body == b"reject":
            return {"status": "rejected"}
        # No deduplication in the probe: an erroneous replay must be observable.
        with self.storage.transaction() as db:
            db.execute("INSERT INTO received VALUES (?, ?, ?)", (payload["receipt_id"], payload["event_id"], body))
        return {"status": "accepted"}


def create_service(application):
    return Receiver(application)
