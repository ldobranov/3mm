"""add_is_translatable_and_content_type_to_settings

Revision ID: 29d0afad2ec4
Revises: add_language_code_to_settings
Create Date: 2025-11-17 08:19:12.972812

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '29d0afad2ec4'
down_revision: Union[str, Sequence[str], None] = 'add_language_code_to_settings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
