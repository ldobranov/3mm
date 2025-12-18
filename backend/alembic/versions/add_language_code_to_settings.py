"""Add language_code column to settings table

Revision ID: add_language_code_to_settings
Revises: 
Create Date: 2025-11-12 06:22:36.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_language_code_to_settings'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add language_code column to settings table (nullable for backward compatibility)
    op.add_column('settings', sa.Column('language_code', sa.String(10), nullable=True))
    
    # Create index for efficient lookups of language-specific settings
    op.create_index('idx_settings_key_lang', 'settings', ['key', 'language_code'], unique=False)
    
    # Add comment for documentation
    op.execute("COMMENT ON COLUMN settings.language_code IS 'Optional language code for language-specific settings. NULL means global setting.'")


def downgrade() -> None:
    # Remove the index first
    op.drop_index('idx_settings_key_lang', table_name='settings')
    
    # Remove the column
    op.drop_column('settings', 'language_code')