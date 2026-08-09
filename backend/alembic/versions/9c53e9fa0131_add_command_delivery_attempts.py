"""add command delivery attempts

Revision ID: 9c53e9fa0131
Revises: 8b42d8e9f120
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9c53e9fa0131"
down_revision: Union[str, Sequence[str], None] = "8b42d8e9f120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "device_commands",
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("device_commands", "delivery_attempts")
