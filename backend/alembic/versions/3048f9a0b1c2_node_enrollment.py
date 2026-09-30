"""Permit device-originated pairing without attributing it to an administrator."""
from alembic import op
import sqlalchemy as sa

revision = "3048f9a0b1c2"
down_revision = "2f37e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("device_pairing_requests") as batch:
        batch.alter_column("created_by_user_id", existing_type=sa.Integer(), nullable=True)
    op.create_index("uq_node_enrollment_device", "device_pairing_requests",
                    ["requested_device_id"], unique=True,
                    sqlite_where=sa.text("created_by_user_id IS NULL"),
                    postgresql_where=sa.text("created_by_user_id IS NULL"))


def downgrade():
    # Older code has no enrollment receipts. Devices and credentials remain intact.
    op.execute("DELETE FROM device_pairing_requests WHERE created_by_user_id IS NULL")
    op.drop_index("uq_node_enrollment_device", table_name="device_pairing_requests")
    with op.batch_alter_table("device_pairing_requests") as batch:
        batch.alter_column("created_by_user_id", existing_type=sa.Integer(), nullable=False)
