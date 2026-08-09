"""Add the Core device registry tables.

Revision ID: 7a31d5d293e1
Revises: 3c822ea2b9ab
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a31d5d293e1"
down_revision: str | Sequence[str] | None = "3c822ea2b9ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("protocol_version", sa.String(32), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("device_id"),
    )
    op.create_index("ix_devices_device_id", "devices", ["device_id"], unique=True)

    op.create_table(
        "device_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("credential_id", sa.String(64), nullable=False),
        sa.Column("secret_hash", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("credential_id"),
    )
    op.create_index(
        "ix_device_credentials_device_id", "device_credentials", ["device_id"]
    )
    op.create_index(
        "ix_device_credentials_credential_id",
        "device_credentials",
        ["credential_id"],
        unique=True,
    )

    op.create_table(
        "device_pairing_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("requested_device_id", sa.String(64), nullable=True),
        sa.Column("public_key", sa.Text(), nullable=True),
        sa.Column("requested_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "device_id", sa.Integer(), sa.ForeignKey("devices.id"), nullable=True
        ),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "approved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index(
        "ix_device_pairing_requests_code_hash",
        "device_pairing_requests",
        ["code_hash"],
        unique=True,
    )
    op.create_index(
        "ix_device_pairing_requests_requested_device_id",
        "device_pairing_requests",
        ["requested_device_id"],
    )
    op.create_index(
        "ix_device_pairing_requests_device_id", "device_pairing_requests", ["device_id"]
    )
    op.create_index(
        "ix_device_pairing_requests_expires_at",
        "device_pairing_requests",
        ["expires_at"],
    )

    op.create_table(
        "device_inventory_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("inventory", sa.JSON(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_device_inventory_snapshots_device_id",
        "device_inventory_snapshots",
        ["device_id"],
    )
    op.create_index(
        "ix_device_inventory_snapshots_received_at",
        "device_inventory_snapshots",
        ["received_at"],
    )
    op.create_index(
        "ix_inventory_device_received",
        "device_inventory_snapshots",
        ["device_id", "received_at"],
    )

    op.create_table(
        "device_heartbeats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("protocol_version", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_device_heartbeats_device_id", "device_heartbeats", ["device_id"]
    )
    op.create_index(
        "ix_device_heartbeats_received_at", "device_heartbeats", ["received_at"]
    )
    op.create_index(
        "ix_heartbeat_device_received",
        "device_heartbeats",
        ["device_id", "received_at"],
    )


def downgrade() -> None:
    op.drop_table("device_heartbeats")
    op.drop_table("device_inventory_snapshots")
    op.drop_table("device_pairing_requests")
    op.drop_table("device_credentials")
    op.drop_table("devices")
