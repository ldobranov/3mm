"""Owned interval/calendar schedule admission and bounded occurrence history."""
from alembic import op
import sqlalchemy as sa

revision = "5a30b182c920"
down_revision = "4f29a071b819"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("application_command_requests", sa.Column("task_run_id", sa.String(37)))
    op.create_table("application_task_schedules",
        sa.Column("schedule_id", sa.String(41), primary_key=True),
        sa.Column("installation_id", sa.Integer(), sa.ForeignKey("application_extension_installations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("package_id", sa.Integer(), sa.ForeignKey("module_packages.id"), nullable=False),
        sa.Column("incarnation", sa.String(32), nullable=False),
        sa.Column("authority_epoch", sa.String(32), nullable=False),
        sa.Column("grant_revision", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.String(96), nullable=False),
        sa.Column("request_id", sa.String(32), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("rule", sa.JSON(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("start_window_seconds", sa.Integer(), nullable=False),
        sa.Column("max_occurrences", sa.Integer(), nullable=False),
        sa.Column("history_limit", sa.Integer(), nullable=False),
        sa.Column("cursor_at", sa.DateTime(timezone=True)),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("admitted", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("last_request_id", sa.String(36)),
        sa.Column("error_code", sa.String(32)),
        sa.UniqueConstraint("installation_id", "incarnation", "task_id", "request_id", name="uq_application_task_schedule_request"),
        sa.CheckConstraint("state IN ('active','cancelled','exhausted','blocked')", name="ck_application_task_schedule_state"))
    op.create_index("ix_application_task_schedules_poll", "application_task_schedules", ["state", "checked_at"])
    with op.batch_alter_table("application_task_runs") as batch:
        batch.alter_column("request_id", existing_type=sa.String(32), type_=sa.String(36), existing_nullable=False)
        batch.add_column(sa.Column("schedule_id", sa.String(41)))
        batch.create_index("ix_application_task_runs_schedule_id", ["schedule_id"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM application_command_requests WHERE task_run_id IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Task command history exists; restore a verified pre-upgrade backup")
    if op.get_bind().execute(sa.text("SELECT 1 FROM application_task_schedules LIMIT 1")).first():
        raise RuntimeError("Schedule history exists; restore a verified pre-upgrade backup")
    if op.get_bind().execute(sa.text("SELECT 1 FROM application_task_runs WHERE schedule_id IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Occurrence history exists; restore a verified pre-upgrade backup")
    with op.batch_alter_table("application_task_runs") as batch:
        batch.drop_index("ix_application_task_runs_schedule_id")
        batch.drop_column("schedule_id")
        batch.alter_column("request_id", existing_type=sa.String(36), type_=sa.String(32), existing_nullable=False)
    op.drop_index("ix_application_task_schedules_poll", table_name="application_task_schedules")
    op.drop_table("application_task_schedules")
    op.drop_column("application_command_requests", "task_run_id")
