"""Optional app-side integration: notify the original recipient of a completed report.

Use in the SAME application's existing transaction. This source example is
not installed by Core and does not modify the worker-only report ZIP.
"""
import re
import time
from datetime import datetime, timezone
from uuid import uuid4

if __package__:  # bundled beside the service, within the application's own wheel
    from .data_tools.inbox import Audience, Inbox, InboxError, initialize
else:  # standalone source example
    from application_data_tools.inbox import Audience, Inbox, InboxError, initialize


TOPIC = "report.ready"
INBOX = Inbox([TOPIC])
MAX_OPEN = 128
MAX_FOR_RECIPIENT = 16
MAX_ATTEMPTS = 3
RETENTION = 24 * 3600
DELIVERY_STATES = ("not_scheduled", "waiting", "deferred", "expired", "not_eligible",
                   "not_subscribed", "recorded", "limited")


def migrate(db):
    initialize(db)
    db.execute("ALTER TABLE report_requests ADD COLUMN notice_review TEXT NOT NULL DEFAULT 'unreviewed'")
    db.execute("UPDATE report_requests SET notice_review='not_requested'")  # never enroll existing work retroactively
    db.execute("""CREATE TABLE report_notices(
        ref TEXT PRIMARY KEY, subject TEXT NOT NULL, access_revision INTEGER NOT NULL, data_revision INTEGER NOT NULL,
        consent TEXT NOT NULL, created INTEGER NOT NULL, expires INTEGER NOT NULL, next_try INTEGER NOT NULL,
        attempts INTEGER NOT NULL, status TEXT NOT NULL)""")
    db.execute("CREATE INDEX report_notices_for_subject ON report_notices(subject)")
    db.execute("CREATE INDEX report_notices_expiry ON report_notices(expires)")
    # Erasing the business object also erases its notice. Do not let a
    # subsequently reused opaque reference adopt the old delivery or consent.
    db.execute("""CREATE TRIGGER report_notice_erased AFTER DELETE ON report_requests
        BEGIN
          DELETE FROM inbox_entries WHERE topic='report.ready' AND recipient=OLD.subject_ref AND event_ref=OLD.ref;
          DELETE FROM report_notices WHERE ref=OLD.ref;
        END""")


def migrate_retry_windows(db):
    """Optional subsequent app migration; historical intents never get a schedule automatically."""
    db.execute("ALTER TABLE report_notices ADD COLUMN retry_request_id TEXT")


def _transaction(db):
    if getattr(db, "in_transaction", True) is False:
        raise InboxError("application_transaction_required")


def _review(db, ref):
    if type(ref) is not str or not re.fullmatch(r"[0-9a-f]{32}",ref):
        raise InboxError("invalid_reference")
    return db.execute("""SELECT r.subject_ref,r.access_revision,r.data_revision,r.sha256,r.original_run,r.notice_review
            FROM report_requests r JOIN report_subjects s ON s.subject_ref=r.subject_ref
            WHERE r.ref=? AND s.allowed=1 AND r.access_revision=s.access_revision
              AND r.data_revision=s.data_revision""",(ref,)).fetchone()


def remember(db, *, current_audience, ref, now):
    """In the transaction reviewing a NEW report request, never when replaying a worker."""
    _transaction(db)
    scope = current_audience(db)
    if type(now) is not int or not 0 <= now <= 2**53-1-RETENTION:
        raise InboxError("invalid_time")
    row = _review(db,ref)
    if not isinstance(scope,Audience) or not row or (row[0],row[1]) != (scope.recipient,scope.access_revision):
        raise InboxError("report_not_available")
    if row[3] is not None or row[4] is not None:
        raise InboxError("not_a_new_review")
    existing = db.execute("SELECT status FROM report_notices WHERE ref=?", (ref,)).fetchone()
    if existing:
        return existing[0]  # Do not acquire new consent or move the original deadline.
    if row[5] != "unreviewed":
        return row[5]
    token = INBOX.capture_consent(db,lambda _:scope,TOPIC)
    if not token:
        db.execute("UPDATE report_requests SET notice_review='not_subscribed' WHERE ref=?", (ref,))
        return "not_subscribed"
    # This table counts terminal receipts too until explicit retention/erasure.
    # It can never become an unbounded deferred queue.
    if (db.execute("SELECT count(*) FROM report_notices WHERE subject=?", (scope.recipient,)).fetchone()[0] >= MAX_FOR_RECIPIENT
            or db.execute("SELECT count(*) FROM report_notices").fetchone()[0] >= MAX_OPEN):
        db.execute("UPDATE report_requests SET notice_review='capacity_limited' WHERE ref=?", (ref,))
        return "capacity_limited"
    db.execute("""INSERT INTO report_notices(ref,subject,access_revision,data_revision,consent,created,expires,next_try,attempts,status)
                  VALUES(?,?,?,?,?,?,?,?,0,'waiting')""",(ref,*tuple(row[:3]),token,now,now+RETENTION,now))
    db.execute("UPDATE report_requests SET notice_review='reviewed' WHERE ref=?", (ref,))
    return "waiting"


def deliver_original(db, ref, *, now):
    """Call after the ordinary render commits or from an approved bounded app task.

    A lost response repeats only this local idempotent observation/delivery.
    No new task, recipient, event ID, permission, network or email is created.
    """
    _transaction(db)
    if type(now) is not int or not 0 <= now <= 2**53-1 or type(ref) is not str or not re.fullmatch(r"[0-9a-f]{32}",ref):
        raise InboxError("invalid_delivery")
    job = db.execute("""SELECT subject,access_revision,data_revision,consent,created,expires,next_try,attempts,status
                        FROM report_notices WHERE ref=?""", (ref,)).fetchone()
    if not job:
        return "not_scheduled"
    subject, access, revision, token, created, expires, due, attempts, status = job
    if status not in ("waiting","deferred"):
        return status
    row = _review(db,ref)
    if now >= expires:
        status = "expired"
    elif not row or tuple(row[:3]) != (subject,access,revision):
        status = "not_eligible"
    elif token != INBOX.capture_consent(db,lambda _:Audience(subject,access),TOPIC):
        status = "not_subscribed"
    elif row[3] is None or row[4] is None or now < max(created,due):
        return status
    else:
        # _review and the consent test run in this SAME write transaction.
        attempts += 1
        result = INBOX.publish(db,lambda _:Audience(subject,access),topic=TOPIC,consent=token,
                               event_ref=ref,resource_ref=ref,now=now,available=now,expires=expires)
        if result in ("available","already_recorded"):
            status = "recorded"
        elif result in ("rate_limited","capacity_limited"):
            status = "deferred" if attempts < MAX_ATTEMPTS else "limited"
            due = min(now + 60 * attempts, expires)
        else:
            status = result
    db.execute("UPDATE report_notices SET attempts=?,status=?,next_try=? WHERE ref=?",(attempts,status,due,ref))
    return status


def run_delivery_task(application, payload, context):
    """One approved internal delivery turn. No scheduler, external channel or implicit retry."""
    task = context.task_execution
    if (context.audience != "internal" or task is None or task.task_id != "deliver_notice"
            or type(payload) is not dict or set(payload) != {"report_ref"}):
        raise InboxError("invalid_delivery")
    with application.storage.transaction() as db:
        state = deliver_original(db, payload["report_ref"], now=int(time.time()))
        if state not in DELIVERY_STATES:
            raise InboxError("invalid_delivery")
        return {"state": state}


def read_status(db, *, current_audience, ref, now):
    """Read only the current viewer's intent. No subscribe, retry or change of state."""
    _transaction(db)
    scope = current_audience(db)
    row = _review(db,ref)
    if not isinstance(scope,Audience) or not row or tuple(row[:2]) != (scope.recipient,scope.access_revision):
        raise InboxError("report_not_available")
    if type(now) is not int or not 0 <= now <= 2**53-1:
        raise InboxError("invalid_time")
    receipt = db.execute("""SELECT status,attempts,next_try,expires,consent FROM report_notices WHERE ref=? AND subject=?
             AND access_revision=? AND data_revision=?""",(ref,*tuple(row[:3]))).fetchone()
    if not receipt:
        return {"state":row[5] if row[5] in ("not_subscribed","capacity_limited") else "not_scheduled"}
    status = receipt[0]
    if status in ("waiting","deferred"):
        if now >= receipt[3]:
            status = "expired"
        elif INBOX.capture_consent(db,lambda _:scope,TOPIC) != receipt[4]:
            status = "not_subscribed"
    return {"state":status,"attempts":receipt[1],"retry_not_before":receipt[2] if status=="deferred" else None}


def claim_retry_window(db, *, current_audience, ref, now):
    """In one app write transaction: return ONE first-admission plan, never a replay.

    Only after a real rate/capacity deferral, with the original subscription
    and current report rights. Commit the transaction BEFORE submitting this
    plan to the SDK. Do not send the plan or request ID to a browser.
    """
    status = read_status(db, current_audience=current_audience, ref=ref, now=now)
    if status["state"] != "deferred":
        return None
    remaining = MAX_ATTEMPTS - status["attempts"]
    if not 1 <= remaining < MAX_ATTEMPTS:
        return None
    expires, existing = db.execute("SELECT expires,retry_request_id FROM report_notices WHERE ref=?", (ref,)).fetchone()
    start = max(now + 1, status["retry_not_before"])
    # The example task declares a 180s admission horizon. A backwards clock
    # jump must not consume the single original ID for an inadmissible plan.
    if existing is not None or start >= expires or start > now + 180:
        return None
    # Attempt two may defer for 120s. Allow the full first start window
    # before that delay to avoid spending the last occurrence too early.
    window, run_budget = 10, 5
    interval = 120 + window + run_budget
    remaining = min(remaining, 1 + (expires - start - 1) // interval)
    end = min(expires, start + (remaining - 1) * interval + window + run_budget)
    key = uuid4().hex
    db.execute("UPDATE report_notices SET retry_request_id=? WHERE ref=? AND retry_request_id IS NULL", (key,ref))
    return {"task_id":"deliver_notice","request_id":key,"payload":{"report_ref":ref},
            "rule":{"kind":"interval","every_seconds":interval},
            "start_at":datetime.fromtimestamp(start,timezone.utc), "end_at":datetime.fromtimestamp(end,timezone.utc),
            "max_occurrences":remaining, "history_limit":remaining, "start_window_seconds":window}


def retry_lookup_key(db, *, current_audience, ref, now):
    """Read-only handle for lookup_task_schedule, never for another creation."""
    status = read_status(db,current_audience=current_audience,ref=ref,now=now)
    if status["state"] not in ("deferred","recorded","limited"):
        return None
    # Even a terminal local receipt is not permission to inspect the shared
    # scheduler after opt-out (or opt-out followed by a new subscription).
    row = db.execute("SELECT consent,retry_request_id FROM report_notices WHERE ref=?", (ref,)).fetchone()
    if row and row[0] == INBOX.capture_consent(db,current_audience,TOPIC):
        return row[1]
    return None


def prune(db, *, now):
    INBOX.prune_expired(db,now=now)
    db.execute("DELETE FROM report_notices WHERE ref IN (SELECT ref FROM report_notices WHERE expires<=? ORDER BY expires,ref LIMIT 64)",(now,))


def erase(db, *, current_audience):
    _transaction(db)
    scope = current_audience(db)
    if not isinstance(scope,Audience):
        raise InboxError("inbox_unavailable")
    INBOX.erase_recipient(db,lambda _:scope)
    db.execute("DELETE FROM report_notices WHERE subject=?", (scope.recipient,))
