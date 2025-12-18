"""add_user_id_to_settings

Revision ID: 3c822ea2b9ab
Revises: drop_items_col
Create Date: 2025-11-25 05:54:43.004962

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c822ea2b9ab'
down_revision: Union[str, Sequence[str], None] = 'drop_items_col'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
