"""Bounded one-shot task admission and result journal; preserve existing state."""
from alembic import op
import sqlalchemy as sa

revision = "4f29a071b819"
down_revision = "3e189f465708"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("application_task_runs",
        sa.Column("task_run_id", sa.String(37), primary_key=True),
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
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_monotonic", sa.Float()),
        sa.Column("boot_id", sa.String(36)),
        sa.Column("lease_token", sa.String(64)),
        sa.Column("worker_generation", sa.String(32)),
        sa.Column("invocation_id", sa.String(32)),
        sa.Column("dispatched", sa.Boolean(), nullable=False),
        sa.Column("started", sa.Boolean(), nullable=False),
        sa.Column("output_schema", sa.JSON()),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("error_code", sa.String(32)),
        sa.UniqueConstraint("installation_id", "incarnation", "task_id", "request_id", name="uq_application_task_request"),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_application_task_progress"),
        sa.CheckConstraint("state IN ('queued','running','succeeded','failed','expired','cancelled','unknown','resolved')", name="ck_application_task_state"))
    op.create_index("ix_application_tasks_due", "application_task_runs", ["state", "due_at"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM application_task_runs LIMIT 1")).first():
        raise RuntimeError("Task history exists; restore a verified pre-upgrade backup")
    # Empty-journal downgrade only; never discard outcomes or request identities.
    op.drop_index("ix_application_tasks_due", table_name="application_task_runs")
    op.drop_table("application_task_runs")
