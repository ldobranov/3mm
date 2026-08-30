"""add durable application event deliveries and cursors

Revision ID: c9e1f2a3b4c5
Revises: b8d0e1f2a3c4
"""

from alembic import op
import sqlalchemy as sa


revision = "c9e1f2a3b4c5"
down_revision = "b8d0e1f2a3c4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "application_event_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "application_installation_id",
            sa.Integer(),
            sa.ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subscription_id", sa.String(96), nullable=False),
        sa.Column(
            "device_event_id",
            sa.Integer(),
            sa.ForeignKey("device_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "application_installation_id",
            "subscription_id",
            "device_event_id",
            name="uq_application_event_delivery",
        ),
    )
    op.create_index(
        "ix_application_event_deliveries_application_installation_id",
        "application_event_deliveries",
        ["application_installation_id"],
    )
    op.create_index(
        "ix_application_event_deliveries_device_event_id",
        "application_event_deliveries",
        ["device_event_id"],
    )
    op.create_index(
        "ix_application_event_deliveries_status",
        "application_event_deliveries",
        ["status"],
    )
    op.create_index(
        "ix_application_event_delivery_queue",
        "application_event_deliveries",
        ["application_installation_id", "subscription_id", "status", "device_event_id"],
    )
    op.create_table(
        "application_event_cursors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "application_installation_id",
            sa.Integer(),
            sa.ForeignKey("application_extension_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subscription_id", sa.String(96), nullable=False),
        sa.Column("last_device_event_id", sa.Integer(), nullable=True),
        sa.Column("last_event_id", sa.String(64), nullable=True),
        sa.Column("acknowledged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dead_letter_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dropped_dead_letter_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "application_installation_id",
            "subscription_id",
            name="uq_application_event_cursor",
        ),
    )
    op.create_index(
        "ix_application_event_cursors_application_installation_id",
        "application_event_cursors",
        ["application_installation_id"],
    )


def downgrade():
    op.drop_table("application_event_cursors")
    op.drop_table("application_event_deliveries")
