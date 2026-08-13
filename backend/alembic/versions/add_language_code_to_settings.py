"""Add language_code column to settings table

Revision ID: add_language_code_to_settings
Revises: 
Create Date: 2025-11-12 06:22:36.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_language_code_to_settings'
down_revision = '0f1e2d3c4b5a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('settings')}
    if 'language_code' not in columns:
        op.add_column('settings', sa.Column('language_code', sa.String(10), nullable=True))

    indexes = {index['name'] for index in inspector.get_indexes('settings')}
    if 'idx_settings_key_lang' not in indexes:
        op.create_index('idx_settings_key_lang', 'settings', ['key', 'language_code'], unique=False)

    if op.get_bind().dialect.name == 'postgresql':
        op.execute(
            "COMMENT ON COLUMN settings.language_code IS "
            "'Optional language code for language-specific settings. NULL means global setting.'"
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {index['name'] for index in inspector.get_indexes('settings')}
    if 'idx_settings_key_lang' in indexes:
        op.drop_index('idx_settings_key_lang', table_name='settings')

    columns = {column['name'] for column in inspector.get_columns('settings')}
    if 'language_code' in columns:
        op.drop_column('settings', 'language_code')
