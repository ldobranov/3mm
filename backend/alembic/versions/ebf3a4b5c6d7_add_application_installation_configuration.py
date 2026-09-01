"""add per-installation application configuration

Revision ID: ebf3a4b5c6d7
Revises: dae2f3a4b5c6, add_language_code_to_settings
"""

from alembic import op
import sqlalchemy as sa


revision = "ebf3a4b5c6d7"
down_revision = ("dae2f3a4b5c6", "add_language_code_to_settings")
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "application_extension_installations",
        sa.Column(
            "configuration",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade():
    op.drop_column("application_extension_installations", "configuration")
