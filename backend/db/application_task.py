"""Core admission/result journal; task code and waiting run outside Core."""
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, Float, DateTime, JSON, ForeignKey, UniqueConstraint, Index, CheckConstraint
from backend.db.base import Base


class ApplicationTaskRun(Base):
    __tablename__ = "application_task_runs"
    task_run_id = Column(String(37), primary_key=True)
    installation_id = Column(Integer, ForeignKey("application_extension_installations.id", ondelete="CASCADE"), nullable=False)
    package_id = Column(Integer, ForeignKey("module_packages.id"), nullable=False)
    incarnation = Column(String(32), nullable=False)
    authority_epoch = Column(String(32), nullable=False)
    grant_revision = Column(BigInteger, nullable=False)
    task_id = Column(String(96), nullable=False)
    request_id = Column(String(36), nullable=False)
    schedule_id = Column(String(41), nullable=True, index=True)
    request_hash = Column(String(64), nullable=False)
    state = Column(String(16), nullable=False)
    payload = Column(JSON, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=False)
    not_after = Column(DateTime(timezone=True), nullable=False)
    lease_until = Column(DateTime(timezone=True), nullable=True)
    lease_monotonic = Column(Float, nullable=True)
    boot_id = Column(String(36), nullable=True)
    lease_token = Column(String(64), nullable=True)
    worker_generation = Column(String(32), nullable=True)
    invocation_id = Column(String(32), nullable=True)
    dispatched = Column(Boolean, nullable=False, default=False)
    started = Column(Boolean, nullable=False, default=False)
    output_schema = Column(JSON, nullable=True)
    progress = Column(Integer, nullable=False, default=0)
    result = Column(JSON, nullable=True)
    error_code = Column(String(32), nullable=True)
    __table_args__ = (
        UniqueConstraint("installation_id", "incarnation", "task_id", "request_id", name="uq_application_task_request"),
        Index("ix_application_tasks_due", "state", "due_at"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_application_task_progress"),
        CheckConstraint("state IN ('queued','running','succeeded','failed','expired','cancelled','unknown','resolved')", name="ck_application_task_state"),
    )


class ApplicationTaskSchedule(Base):
    """Owned admission ledger, with a durable cursor against repeated occurrences."""
    __tablename__ = "application_task_schedules"
    schedule_id = Column(String(41), primary_key=True)
    installation_id = Column(Integer, ForeignKey("application_extension_installations.id", ondelete="CASCADE"), nullable=False)
    package_id = Column(Integer, ForeignKey("module_packages.id"), nullable=False)
    incarnation = Column(String(32), nullable=False)
    authority_epoch = Column(String(32), nullable=False)
    grant_revision = Column(BigInteger, nullable=False)
    task_id = Column(String(96), nullable=False)
    request_id = Column(String(32), nullable=False)
    request_hash = Column(String(64), nullable=False)
    state = Column(String(16), nullable=False)
    payload = Column(JSON, nullable=False)
    rule = Column(JSON, nullable=False)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    start_window_seconds = Column(Integer, nullable=False)
    max_occurrences = Column(Integer, nullable=False)
    history_limit = Column(Integer, nullable=False)
    cursor_at = Column(DateTime(timezone=True), nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=False)
    admitted = Column(Integer, nullable=False, default=0)
    skipped = Column(Integer, nullable=False, default=0)
    last_request_id = Column(String(36), nullable=True)
    error_code = Column(String(32), nullable=True)
    __table_args__ = (
        UniqueConstraint("installation_id", "incarnation", "task_id", "request_id", name="uq_application_task_schedule_request"),
        Index("ix_application_task_schedules_poll", "state", "checked_at"),
        CheckConstraint("state IN ('active','cancelled','exhausted','blocked')", name="ck_application_task_schedule_state"),
    )
