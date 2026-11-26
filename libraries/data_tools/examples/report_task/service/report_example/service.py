"""An application owns its intent, audience, table, artifact and retention policy."""
import re

from .data_tools import Column, Limits
from .data_tools.report import render_table


_COLUMNS = (Column("label", max_length=128), Column("quantity", "integer"))
_LIMITS = Limits(max_rows=64, max_bytes=32_768)


def _reviewed_intent(db, ref):
    row = db.execute("""SELECT r.subject_ref,r.original_run,r.rows,r.size_bytes,r.sha256
        FROM report_requests r JOIN report_subjects s ON s.subject_ref=r.subject_ref
        WHERE r.ref=? AND s.allowed=1 AND r.access_revision=s.access_revision
          AND r.data_revision=s.data_revision""", (ref,)).fetchone()
    if row is None:
        raise ValueError("report_not_available")
    return row


def read_for_subject(db, *, current_subject, ref):
    """Use inside the currently authenticated reader's application transaction."""
    row = _reviewed_intent(db, ref)
    if row[0] != current_subject or row[4] is None:
        raise ValueError("report_not_available")
    return db.execute("SELECT content FROM report_requests WHERE ref=? AND subject_ref=?",
                      (ref, current_subject)).fetchone()[0]


def _receipt(row):
    return {"rows": row[2], "size_bytes": row[3], "sha256": row[4]}


class Service:
    def __init__(self, application):
        self.app = application

    def handle(self, operation_id, payload, context):
        if operation_id == "health" and context.audience == "internal":
            return {"status": "ready"}
        task = context.task_execution
        if (operation_id != "render_table" or context.audience != "internal" or task is None
                or task.task_id != operation_id or set(payload) != {"report_ref"}
                or not isinstance(payload["report_ref"], str) or not re.fullmatch("[0-9a-f]{32}", payload["report_ref"])):
            raise ValueError("report_not_available")
        ref = payload["report_ref"]
        with self.app.storage.transaction() as db:
            row = _reviewed_intent(db, ref)
            if row[1] not in (None, task.task_run_id):
                raise ValueError("report_not_available")
            if row[4] is not None:
                return _receipt(row)
            db.execute("UPDATE report_requests SET original_run=? WHERE ref=? AND original_run IS NULL",
                       (task.task_run_id, ref))
            subject = row[0]
            records = [dict(label=x[0], quantity=x[1]) for x in db.execute(
                "SELECT label,quantity FROM report_items WHERE subject_ref=? ORDER BY item_id LIMIT ?",
                (subject, _LIMITS.max_rows + 1))]
        # No application DB lock while reporting progress or rendering.
        self.app.platform.task_progress(task, 50)
        report = render_table(records, _COLUMNS, title="Selected inventory", limits=_LIMITS)
        meta = report.metadata()
        with self.app.storage.transaction() as db:
            row = _reviewed_intent(db, ref)
            if row[0] != subject or row[1] != task.task_run_id:
                raise ValueError("report_not_available")
            if row[4] is not None:
                return _receipt(row)
            db.execute("""UPDATE report_requests SET content=?,rows=?,size_bytes=?,sha256=?
                          WHERE ref=? AND original_run=? AND sha256 IS NULL""",
                       (report.content, meta["rows"], meta["size_bytes"], meta["sha256"], ref, task.task_run_id))
        return meta


def create_service(application):
    return Service(application)
