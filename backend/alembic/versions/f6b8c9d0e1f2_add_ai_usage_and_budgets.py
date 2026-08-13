"""add AI jobs budgets and usage ledger

Revision ID: f6b8c9d0e1f2
Revises: e5a7b8c9d0e1
"""
from alembic import op
import sqlalchemy as sa

revision = "f6b8c9d0e1f2"
down_revision = "e5a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_credit_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("available_microcredits", sa.Integer(), nullable=False),
        sa.Column("reserved_microcredits", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_credit_accounts_user_id", "ai_credit_accounts", ["user_id"], unique=True)
    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(64), nullable=False), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False), sa.Column("model", sa.String(160), nullable=False),
        sa.Column("payment_mode", sa.String(32), nullable=False), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=False), sa.Column("estimated_output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_max_microcredits", sa.Integer(), nullable=False), sa.Column("approved_max_microcredits", sa.Integer(), nullable=True),
        sa.Column("reserved_microcredits", sa.Integer(), nullable=False), sa.Column("actual_input_tokens", sa.Integer(), nullable=True),
        sa.Column("actual_output_tokens", sa.Integer(), nullable=True), sa.Column("actual_microcredits", sa.Integer(), nullable=True),
        sa.Column("artifact_hash", sa.String(64), nullable=True), sa.Column("proposal_id", sa.String(64), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("job_id", "user_id", "request_hash", "status", "artifact_hash", "proposal_id"):
        op.create_index(f"ix_ai_jobs_{column}", "ai_jobs", [column], unique=column == "job_id")
    op.create_table(
        "ai_usage_ledger",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("entry_id", sa.String(64), nullable=False),
        sa.Column("job_id", sa.String(64), nullable=False), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("entry_type", sa.String(32), nullable=False), sa.Column("microcredits", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_usage_ledger_entry_id", "ai_usage_ledger", ["entry_id"], unique=True)
    op.create_index("ix_ai_usage_ledger_job_id", "ai_usage_ledger", ["job_id"])
    op.create_index("ix_ai_usage_ledger_user_id", "ai_usage_ledger", ["user_id"])


def downgrade():
    op.drop_table("ai_usage_ledger")
    op.drop_table("ai_jobs")
    op.drop_table("ai_credit_accounts")
