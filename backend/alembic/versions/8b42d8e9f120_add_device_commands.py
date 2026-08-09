"""add device commands

Revision ID: 8b42d8e9f120
Revises: 7a31d5d293e1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8b42d8e9f120"
down_revision: Union[str, Sequence[str], None] = "7a31d5d293e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_commands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("command_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_device_commands_command_id", "device_commands", ["command_id"], unique=True)
    op.create_index("ix_device_commands_device_id", "device_commands", ["device_id"])
    op.create_index("ix_device_commands_status", "device_commands", ["status"])
    op.create_index("ix_device_commands_expires_at", "device_commands", ["expires_at"])
    op.create_index("ix_command_device_status_created", "device_commands", ["device_id", "status", "created_at"])
    op.create_index("ux_command_device_idempotency", "device_commands", ["device_id", "idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_table("device_commands")
