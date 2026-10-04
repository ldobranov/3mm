"""Core configuration selection and bounded provider health, preserving legacy."""

from alembic import op
import sqlalchemy as sa

revision = "96aef5a6b7c8"
down_revision = "859de4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "device_capability_providers",
        sa.Column("configured_capability_ids", sa.JSON(), nullable=True),
    )
    op.create_table(
        "device_capability_health",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_type", sa.String(64), nullable=False),
        sa.Column("provider_id", sa.String(160), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "device_id",
            "provider_type",
            "provider_id",
            name="uq_device_capability_health",
        ),
    )


def downgrade():
    providers = sa.table(
        "device_capability_providers", sa.column("configured_capability_ids", sa.JSON())
    )
    if any(
        value is not None
        for value in op.get_bind()
        .execute(sa.select(providers.c.configured_capability_ids))
        .scalars()
    ):
        raise RuntimeError(
            "Explicit capability configuration cannot safely downgrade; use the pre-upgrade database backup"
        )
    op.drop_table("device_capability_health")
    with op.batch_alter_table("device_capability_providers") as batch:
        batch.drop_column("configured_capability_ids")
