"""Add authority/lifecycle state without changing identities or credentials."""

from alembic import op
import sqlalchemy as sa

revision = "859de4f5a6b7"
down_revision = "748cd3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    state = op.create_table(
        "device_platform_states",
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("authority_status", sa.String(16), nullable=False),
        sa.Column("lifecycle", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(120), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    devices = sa.table(
        "devices", sa.column("id", sa.Integer()), sa.column("revoked_at", sa.DateTime())
    )
    credentials = sa.table(
        "device_credentials",
        sa.column("device_id", sa.Integer()),
        sa.column("revoked_at", sa.DateTime()),
    )
    revoked = sa.or_(
        devices.c.revoked_at.is_not(None),
        sa.and_(
            sa.exists().where(credentials.c.device_id == devices.c.id),
            ~sa.exists().where(
                sa.and_(
                    credentials.c.device_id == devices.c.id,
                    credentials.c.revoked_at.is_(None),
                )
            ),
        ),
    )
    op.get_bind().execute(
        state.insert().from_select(
            ["device_id", "authority_status", "lifecycle", "revision", "updated_at"],
            sa.select(
                devices.c.id,
                sa.literal("bound"),
                sa.case((revoked, "revoked"), else_="active"),
                sa.literal(0),
                sa.func.now(),
            ),
        )
    )


def downgrade():
    op.drop_table("device_platform_states")
