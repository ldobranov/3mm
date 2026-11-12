"""Bounded audit-log retention for production hardening (M15).

The audit journal grows without bound today. This service computes and applies a
deterministic retention plan that never deletes young or evidential records.

Evidential protection is deliberately conservative: any action/entity text that
carries an uncertain/terminal/in-progress marker is retained regardless of age,
so a historical purge can never erase quarantined, unconfirmed, recovery or
failed-operation evidence that later reconciliation may still need.

Both the plan and the apply path are memory-bounded: counting happens in SQL and
deletion selects at most ``max_batch`` identifiers, so a large journal is never
materialized in Python just to remove a few rows.

This operates only on the ordinary human/admin audit journal. It does not touch
device events, application authority actions, outbox/job journals or backup
metadata, which have their own ownership and retention contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, not_, or_, select
from sqlalchemy.orm import Session

from backend.db.audit_log import AuditLog

# Conservative markers that identify records which must survive any age-based
# purge. Matching is case-insensitive and bounded to the three text columns.
_EVIDENTIAL_MARKERS = (
    "UNCONFIRMED",
    "UNCERTAIN",
    "PENDING",
    "QUARANTINE",
    "RECOVERY",
    "ROLLBACK",
    "FAILED",
    "EXECUTION",
    "REVIEW",
)

DEFAULT_RETENTION_DAYS = 90
MIN_RETENTION_DAYS = 30
MAX_RETENTION_DAYS = 3650
MAX_DELETE_BATCH = 10000


class AuditRetentionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AuditRetentionPlan:
    cutoff: datetime
    candidate_total: int
    protected_evidential: int


def retention_cutoff(now: datetime, retention_days: int) -> datetime:
    if (
        isinstance(retention_days, bool)
        or not MIN_RETENTION_DAYS <= retention_days <= MAX_RETENTION_DAYS
    ):
        raise AuditRetentionError(
            "Audit retention days are outside the supported range"
        )
    if now.tzinfo is not None:
        now = now.astimezone(UTC).replace(tzinfo=None)
    return now - timedelta(days=retention_days)


def _evidential_predicate():
    """SQL predicate matching any evidential marker in the text columns."""
    columns = (AuditLog.action, AuditLog.entity_type, AuditLog.entity_name)
    clauses = []
    for marker in _EVIDENTIAL_MARKERS:
        pattern = f"%{marker}%"
        clauses.extend(
            func.upper(func.coalesce(column, "")).like(pattern) for column in columns
        )
    return or_(*clauses)


def plan_audit_retention(
    db: Session,
    *,
    now: datetime,
    retention_days: int,
) -> AuditRetentionPlan:
    """Compute a deterministic plan with SQL counts only (no row loading)."""
    cutoff = retention_cutoff(now, retention_days)
    old = AuditLog.timestamp < cutoff
    total = db.scalar(select(func.count()).select_from(AuditLog).where(old)) or 0
    evidential = (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(old, _evidential_predicate())
        )
        or 0
    )
    return AuditRetentionPlan(
        cutoff=cutoff,
        candidate_total=max(0, total - evidential),
        protected_evidential=evidential,
    )


def apply_audit_retention(
    db: Session,
    *,
    now: datetime,
    retention_days: int,
    max_batch: int,
) -> int:
    """Delete at most ``max_batch`` old non-evidential audit records.

    The candidate identifiers are selected with a SQL ``LIMIT`` so the journal is
    never fully materialized. Evidential rows and everything at/after the cutoff
    are preserved. The caller owns the transaction boundary and commits.
    """
    if isinstance(max_batch, bool) or not 1 <= max_batch <= MAX_DELETE_BATCH:
        raise AuditRetentionError(
            "Audit retention batch is outside the supported range"
        )
    cutoff = retention_cutoff(now, retention_days)
    identifiers = db.scalars(
        select(AuditLog.id)
        .where(AuditLog.timestamp < cutoff, not_(_evidential_predicate()))
        .order_by(AuditLog.id)
        .limit(max_batch)
    ).all()
    if not identifiers:
        return 0
    deleted = (
        db.query(AuditLog)
        .filter(AuditLog.id.in_(identifiers))
        .delete(synchronize_session=False)
    )
    return int(deleted)
