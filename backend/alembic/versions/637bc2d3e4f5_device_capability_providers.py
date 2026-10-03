"""Add non-module capability providers without rewriting existing device data."""

from alembic import op
import sqlalchemy as sa

revision = "637bc2d3e4f5"
down_revision = "526ab1c2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "device_capability_providers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_type", sa.String(64), nullable=False),
        sa.Column("provider_id", sa.String(160), nullable=False),
        sa.Column("provider_version", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "device_id",
            "provider_type",
            "provider_id",
            name="uq_device_capability_provider",
        ),
    )
    op.create_index(
        "ix_device_capability_providers_device_id",
        "device_capability_providers",
        ["device_id"],
    )


def downgrade():
    op.drop_table("device_capability_providers")
