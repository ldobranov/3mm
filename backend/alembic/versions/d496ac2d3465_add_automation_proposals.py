"""add automation proposals

Revision ID: d496ac2d3465
Revises: c385fb1c2354
"""

from alembic import op
import sqlalchemy as sa


revision = "d496ac2d3465"
down_revision = "c385fb1c2354"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "automation_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("proposal_id", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("candidate", sa.JSON(), nullable=False),
        sa.Column("candidate_hash", sa.String(64), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("validation_issues", sa.JSON(), nullable=False),
        sa.Column("diff", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_automation_proposals_proposal_id", "automation_proposals", ["proposal_id"], unique=True)
    op.create_index("ix_automation_proposals_status", "automation_proposals", ["status"])


def downgrade():
    op.drop_index("ix_automation_proposals_status", table_name="automation_proposals")
    op.drop_index("ix_automation_proposals_proposal_id", table_name="automation_proposals")
    op.drop_table("automation_proposals")
