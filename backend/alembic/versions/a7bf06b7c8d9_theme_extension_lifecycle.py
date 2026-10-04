"""Add installation-local theme lifecycle without changing existing packages.

Revision ID: a7bf06b7c8d9
Revises: 96aef5a6b7c8
"""

from alembic import op
import sqlalchemy as sa


revision = "a7bf06b7c8d9"
down_revision = "96aef5a6b7c8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "theme_extension_installations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "module_package_id",
            sa.Integer(),
            sa.ForeignKey("module_packages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "is_selected", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "installed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("module_package_id", name="uq_theme_extension_package"),
        sa.CheckConstraint(
            "NOT is_selected OR enabled", name="ck_selected_theme_enabled"
        ),
    )
    op.create_index(
        "uq_theme_extension_selected",
        "theme_extension_installations",
        ["is_selected"],
        unique=True,
        sqlite_where=sa.text("is_selected = 1"),
        postgresql_where=sa.text("is_selected"),
    )


def downgrade():
    op.drop_index(
        "uq_theme_extension_selected", table_name="theme_extension_installations"
    )
    op.drop_table("theme_extension_installations")
