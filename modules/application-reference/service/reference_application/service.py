"""Deterministic neutral workflow used to accept the application platform."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import timedelta
import uuid

from three_mm_application_sdk import ApplicationContext, OperationContext


def _canonical(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class ReferenceService:
    def __init__(self, application: ApplicationContext) -> None:
        self.application = application

    def _idempotent(self, operation_id, payload, context, callback):
        key = context.idempotency_key
        if not key:
            raise ValueError("An idempotency key is required")
        payload_hash = hashlib.sha256(_canonical(payload).encode()).hexdigest()
        with self.application.storage.transaction() as connection:
            previous = connection.execute(
                "SELECT operation_id, payload_hash, result_json "
                "FROM command_results WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            if previous is not None:
                if previous[0] != operation_id or previous[1] != payload_hash:
                    raise ValueError("Idempotency key was reused with another request")
                return json.loads(previous[2])
            result = callback(connection)
            connection.execute(
                "INSERT INTO command_results VALUES (?, ?, ?, ?, ?)",
                (
                    key,
                    operation_id,
                    payload_hash,
                    _canonical(result),
                    self.application.clock.now().isoformat(),
                ),
            )
            return result

    @staticmethod
    def _record(connection, record_id):
        row = connection.execute(
            "SELECT * FROM records WHERE record_id = ?", (record_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Reference record was not found")
        return row

    def handle(self, operation_id, payload, context: OperationContext):
        handlers = {
            "health": self._health,
            "register": self._register,
            "approve": self._approve,
            "assign_identifier": self._assign_identifier,
            "add_item": self._add_item,
            "get_record": self._get_record,
            "process_scan": self._process_scan,
            "deliver_outbox": self._deliver_outbox,
            "sync_catalog": self._sync_catalog,
        }
        handler = handlers.get(operation_id)
        if handler is None:
            raise ValueError("Operation is unsupported")
        return handler(payload, context)

    def _health(self, _payload, _context):
        return {"status": "ready"}

    def _register(self, payload, context):
        def mutation(connection):
            label = str(payload["label"]).strip()
            if not label or len(label) > 120:
                raise ValueError("Reference label is invalid")
            record_id = f"record_{uuid.uuid4().hex}"
            now = self.application.clock.now().isoformat()
            connection.execute(
                "INSERT INTO records(record_id, label, status, created_at, updated_at) "
                "VALUES (?, ?, 'submitted', ?, ?)",
                (record_id, label, now, now),
            )
            return {"record_id": record_id, "status": "submitted"}

        return self._idempotent("register", payload, context, mutation)

    def _approve(self, payload, context):
        def mutation(connection):
            row = self._record(connection, payload["record_id"])
            if row[2] not in {"submitted", "approved"}:
                raise ValueError("Reference record cannot be approved")
            connection.execute(
                "UPDATE records SET status = 'approved', updated_at = ? WHERE record_id = ?",
                (self.application.clock.now().isoformat(), payload["record_id"]),
            )
            return {"status": "approved"}

        return self._idempotent("approve", payload, context, mutation)

    def _assign_identifier(self, payload, context):
        def mutation(connection):
            self._record(connection, payload["record_id"])
            identifier = str(payload["opaque_identifier"]).strip()
            if not identifier or len(identifier) > 512:
                raise ValueError("Opaque identifier is invalid")
            connection.execute(
                "UPDATE records SET opaque_identifier = ?, updated_at = ? "
                "WHERE record_id = ?",
                (
                    identifier,
                    self.application.clock.now().isoformat(),
                    payload["record_id"],
                ),
            )
            return {"status": "assigned"}

        return self._idempotent("assign_identifier", payload, context, mutation)

    def _add_item(self, payload, context):
        def mutation(connection):
            row = self._record(connection, payload["record_id"])
            quantity = payload["quantity"]
            if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 100:
                raise ValueError("Item quantity is invalid")
            item_count = int(row[4]) + quantity
            connection.execute(
                "UPDATE records SET item_count = ?, updated_at = ? WHERE record_id = ?",
                (item_count, self.application.clock.now().isoformat(), payload["record_id"]),
            )
            return {"item_count": item_count}

        return self._idempotent("add_item", payload, context, mutation)

    def _get_record(self, payload, _context):
        with self.application.storage.transaction() as connection:
            row = self._record(connection, payload["record_id"])
            return {
                "record_id": row[0],
                "status": row[2],
                "item_count": int(row[4]),
                "session_started_at": row[5],
                "session_ended_at": row[6],
            }

    def _process_scan(self, payload, context):
        def mutation(connection):
            scan = payload.get("payload")
            identifier = scan.get("opaque_identifier") if isinstance(scan, dict) else None
            if not isinstance(identifier, str):
                return {"status": "ignored"}
            row = connection.execute(
                "SELECT * FROM records WHERE opaque_identifier = ?", (identifier,)
            ).fetchone()
            if row is None:
                return {"status": "ignored"}
            occurred_at = str(payload["occurred_at"])
            if row[2] == "approved":
                connection.execute(
                    "UPDATE records SET status = 'active', session_started_at = ?, "
                    "updated_at = ? WHERE record_id = ?",
                    (occurred_at, occurred_at, row[0]),
                )
                return {"status": "started"}
            if row[2] == "active":
                connection.execute(
                    "UPDATE records SET status = 'closed', session_ended_at = ?, "
                    "updated_at = ? WHERE record_id = ?",
                    (occurred_at, occurred_at, row[0]),
                )
                self.application.storage.enqueue_outbox(
                    connection,
                    outbox_id=f"out_{uuid.uuid4().hex}",
                    event_type="record.finalized",
                    payload={"record_id": row[0], "item_count": int(row[4])},
                    idempotency_key=f"reference-finalize:{row[0]}",
                )
                return {"status": "closed"}
            return {"status": "already_closed"}

        return self._idempotent("process_scan", payload, context, mutation)

    def _deliver_outbox(self, _payload, _context):
        if self.application.platform is None:
            raise RuntimeError("Application platform is unavailable")
        delivered = retrying = manual_review = 0
        for item in self.application.storage.due_outbox(
            limit=25,
            now=self.application.clock.now(),
        ):
            result = self.application.platform.connector_request(
                "business_api",
                method="POST",
                path="/api/finalize",
                body=_canonical(item.payload).encode(),
                headers={"Content-Type": "application/json"},
                idempotency_key=item.remote_idempotency_key,
                request_id=(
                    "connector_"
                    f"{hashlib.sha256(f'{item.outbox_id}:{item.attempts}'.encode()).hexdigest()[:32]}"
                ),
            )
            attempts = item.attempts + 1
            outcome = result.get("outcome")
            if outcome == "succeeded":
                self.application.storage.update_outbox(
                    item.outbox_id, state="succeeded", attempts=attempts, terminal_result="delivered"
                )
                delivered += 1
            elif outcome == "retryable":
                delay = min(300, 2 ** min(attempts, 8))
                self.application.storage.update_outbox(
                    item.outbox_id,
                    state="retrying",
                    attempts=attempts,
                    next_attempt_at=self.application.clock.now() + timedelta(seconds=delay),
                    last_error=str(result.get("error_category") or "remote_unavailable"),
                )
                retrying += 1
            else:
                state = "ambiguous" if outcome == "ambiguous" else "manual_review"
                self.application.storage.update_outbox(
                    item.outbox_id,
                    state=state,
                    attempts=attempts,
                    terminal_result="manual_review_required",
                    last_error=str(result.get("error_category") or outcome),
                )
                manual_review += 1
        return {"delivered": delivered, "retrying": retrying, "manual_review": manual_review}

    def _sync_catalog(self, _payload, _context):
        if self.application.platform is None:
            raise RuntimeError("Application platform is unavailable")
        checkpoint = self.application.platform.get_checkpoint("catalog")
        revision = int(checkpoint["revision"])
        value = checkpoint.get("value") if isinstance(checkpoint.get("value"), dict) else {}
        page = int(value.get("next_page", 1))
        result = self.application.platform.connector_request(
            "business_api",
            method="GET",
            path=f"/api/catalog/page/{page}",
        )
        if result.get("outcome") != "succeeded":
            return {"status": "retrying", "items": 0}
        try:
            response = json.loads(base64.b64decode(str(result["body_base64"])))
            items = response["items"]
            next_page = response.get("next_page")
            if not isinstance(items, list) or len(items) > 100:
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise ValueError("Catalog response is invalid")
        with self.application.storage.transaction() as connection:
            if page == 1:
                connection.execute("DELETE FROM catalog_staging")
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("label"), str):
                    raise ValueError("Catalog item is invalid")
                connection.execute(
                    "INSERT OR REPLACE INTO catalog_staging(item_id, label) VALUES (?, ?)",
                    (item["id"], item["label"]),
                )
            if next_page is None:
                published = revision + 1
                connection.execute("DELETE FROM catalog_items")
                connection.execute(
                    "INSERT INTO catalog_items(item_id, label, published_revision) "
                    "SELECT item_id, label, ? FROM catalog_staging",
                    (published,),
                )
                connection.execute("DELETE FROM catalog_staging")
        if next_page is None:
            saved = self.application.platform.put_checkpoint(
                "catalog", {"next_page": 1}, expected_revision=revision
            )
            return {"status": "completed", "items": len(items)}
        self.application.platform.put_checkpoint(
            "catalog", {"next_page": int(next_page)}, expected_revision=revision
        )
        return {"status": "retrying", "items": len(items)}


def create_service(application: ApplicationContext):
    return ReferenceService(application)
