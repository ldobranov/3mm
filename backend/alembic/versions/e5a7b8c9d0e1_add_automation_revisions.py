"""add automation revisions and audit events

Revision ID: e5a7b8c9d0e1
Revises: d496ac2d3465
"""

from alembic import op
import sqlalchemy as sa


revision = "e5a7b8c9d0e1"
down_revision = "d496ac2d3465"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "automation_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision_id", sa.String(64), nullable=False),
        sa.Column("automation_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.String(64), nullable=True),
        sa.Column("definition", sa.JSON(), nullable=True),
        sa.Column("definition_hash", sa.String(64), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("command_ids", sa.JSON(), nullable=False),
        sa.Column("applied_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("automation_id", "revision", name="uq_automation_revision_number"),
    )
    op.create_index("ix_automation_revisions_revision_id", "automation_revisions", ["revision_id"], unique=True)
    op.create_index("ix_automation_revisions_automation_id", "automation_revisions", ["automation_id"])
    op.create_index("ix_automation_revisions_proposal_id", "automation_revisions", ["proposal_id"])
    op.create_table(
        "automation_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("automation_id", sa.String(64), nullable=False),
        sa.Column("proposal_id", sa.String(64), nullable=True),
        sa.Column("revision_id", sa.String(64), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("event_id", "automation_id", "proposal_id", "revision_id", "event_type"):
        op.create_index(f"ix_automation_audit_events_{column}", "automation_audit_events", [column], unique=column == "event_id")


def downgrade():
    op.drop_table("automation_audit_events")
    op.drop_table("automation_revisions")
