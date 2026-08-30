"""add application permission grants and kiosk identities

Revision ID: b8d0e1f2a3c4
Revises: a7c9d0e1f2b3
"""

from alembic import op
import sqlalchemy as sa


revision = "b8d0e1f2a3c4"
down_revision = "a7c9d0e1f2b3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "application_permission_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "application_installation_id",
            sa.Integer(),
            sa.ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("permission_id", sa.String(96), nullable=False),
        sa.Column("granted_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "application_installation_id",
            "user_id",
            "permission_id",
            name="uq_application_permission_grant",
        ),
    )
    op.create_index("ix_application_permission_grants_application_installation_id", "application_permission_grants", ["application_installation_id"])
    op.create_index("ix_application_permission_grants_user_id", "application_permission_grants", ["user_id"])

    op.create_table(
        "application_kiosk_enrollments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "application_installation_id",
            sa.Integer(),
            sa.ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_application_kiosk_enrollments_application_installation_id", "application_kiosk_enrollments", ["application_installation_id"])
    op.create_index("ix_application_kiosk_enrollments_expires_at", "application_kiosk_enrollments", ["expires_at"])

    op.create_table(
        "application_kiosk_terminals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("terminal_id", sa.String(64), nullable=False),
        sa.Column(
            "enrollment_id",
            sa.Integer(),
            sa.ForeignKey("application_kiosk_enrollments.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column(
            "application_installation_id",
            sa.Integer(),
            sa.ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_application_kiosk_terminals_terminal_id", "application_kiosk_terminals", ["terminal_id"], unique=True)
    op.create_index("ix_application_kiosk_terminals_application_installation_id", "application_kiosk_terminals", ["application_installation_id"])
    op.create_index("ix_application_kiosk_terminals_enabled", "application_kiosk_terminals", ["enabled"])


def downgrade():
    op.drop_table("application_kiosk_terminals")
    op.drop_table("application_kiosk_enrollments")
    op.drop_table("application_permission_grants")
