"""Drop items column from menus table

Revision ID: drop_items_col
Revises: 29d0afad2ec4
Create Date: 2025-11-18 06:54:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'drop_items_col'
down_revision: Union[str, Sequence[str], None] = '29d0afad2ec4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the unused items column from menus table."""
    # Drop the items column from menus table
    op.drop_column('menus', 'items')


def downgrade() -> None:
    """Add back the items column to menus table."""
    # Add back the items column
    op.add_column('menus', sa.Column('items', sa.JSON(), nullable=True))