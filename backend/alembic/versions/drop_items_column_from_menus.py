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
    """Preserve Menu.items, which remains part of the active model and API."""
    pass


def downgrade() -> None:
    """The corrected upgrade is intentionally schema-neutral."""
    pass
