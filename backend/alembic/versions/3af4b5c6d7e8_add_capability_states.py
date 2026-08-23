"""persist latest Agent capability states

Revision ID: 3af4b5c6d7e8
Revises: 29e3f4a5b6c7
"""

from alembic import op
import sqlalchemy as sa


revision = "3af4b5c6d7e8"
down_revision = "29e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "device_capability_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("capability_id", sa.String(160), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("device_id", "capability_id", name="uq_device_capability_state"),
    )
    op.create_index("ix_device_capability_states_device_id", "device_capability_states", ["device_id"])
    op.create_index("ix_device_capability_states_observed_at", "device_capability_states", ["observed_at"])


def downgrade():
    op.drop_table("device_capability_states")
