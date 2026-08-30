"""add supervised application extension installations

Revision ID: a7c9d0e1f2b3
Revises: 3af4b5c6d7e8
"""

from alembic import op
import sqlalchemy as sa


revision = "a7c9d0e1f2b3"
down_revision = "3af4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "application_extension_installations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module_id", sa.String(160), nullable=False),
        sa.Column(
            "module_package_id",
            sa.Integer(),
            sa.ForeignKey("module_packages.id"),
            nullable=False,
        ),
        sa.Column(
            "previous_package_id",
            sa.Integer(),
            sa.ForeignKey("module_packages.id"),
            nullable=True,
        ),
        sa.Column("instance_id", sa.String(24), nullable=False),
        sa.Column("active_version", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("socket_path", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "instance_id", name="uq_application_extension_installation_instance"
        ),
    )
    op.create_index(
        "ix_application_extension_installations_module_id",
        "application_extension_installations",
        ["module_id"],
        unique=True,
    )
    op.create_index(
        "ix_application_extension_installations_status",
        "application_extension_installations",
        ["status"],
    )
    op.create_index(
        "ix_application_extension_installations_enabled",
        "application_extension_installations",
        ["enabled"],
    )


def downgrade():
    op.drop_table("application_extension_installations")
