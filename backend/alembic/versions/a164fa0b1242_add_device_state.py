"""add device desired and reported state

Revision ID: a164fa0b1242
Revises: 9c53e9fa0131
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a164fa0b1242"
down_revision: Union[str, Sequence[str], None] = "9c53e9fa0131"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "device_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("desired_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("desired_state", sa.JSON(), nullable=False),
        sa.Column("desired_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reported_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reported_state", sa.JSON(), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_device_states_device_id", "device_states", ["device_id"], unique=True)

def downgrade() -> None:
    op.drop_table("device_states")
