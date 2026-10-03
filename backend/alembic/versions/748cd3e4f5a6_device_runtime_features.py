"""Add runtime feature advertisement without rewriting existing nodes."""

from alembic import op
import sqlalchemy as sa

revision = "748cd3e4f5a6"
down_revision = "637bc2d3e4f5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "device_runtime_features",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("declaration", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_device_runtime_features_device_id",
        "device_runtime_features",
        ["device_id"],
        unique=True,
    )


def downgrade():
    op.drop_table("device_runtime_features")
