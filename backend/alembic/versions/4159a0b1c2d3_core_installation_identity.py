"""Versioned whole-Core identity with an encrypted, durable key binding."""

from alembic import op
import sqlalchemy as sa

revision = "4159a0b1c2d3"
down_revision = "3048f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "core_installation_identity",
        sa.Column("singleton_id", sa.Integer(), primary_key=True),
        sa.Column("installation_id", sa.String(37), nullable=False, unique=True),
        sa.Column("identity_version", sa.Integer(), nullable=False),
        sa.Column("key_generation", sa.Integer(), nullable=False),
        sa.Column("key_id", sa.String(64), nullable=False),
        sa.Column("public_key", sa.String(44), nullable=False),
        sa.Column("encrypted_private_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "singleton_id = 1", name="ck_installation_identity_singleton"
        ),
    )


def downgrade():
    # Explicit downgrade loses identity; peers must be reenrolled after reupgrade.
    op.drop_table("core_installation_identity")
