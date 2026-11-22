"""Separate sender approval and bounded status-report checkpoint."""
from alembic import op
import sqlalchemy as sa

revision = "c1a9e0d46b32"
down_revision = "b096b7e82f86"
branch_labels = depends_on = None


def upgrade():
    op.add_column("installation_peer_outbound", sa.Column("send_approval", sa.String(88)))
    op.add_column("installation_peer_outbound", sa.Column("send_revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("installation_peer_outbound", sa.Column("report_sequence", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("installation_peer_outbound", sa.Column("report_contact", sa.JSON(), nullable=True))
    # An existing slot is the first known sample, not proof of its delivery.
    op.execute("UPDATE installation_peer_outbound SET report_sequence=1 WHERE report_id IS NOT NULL")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM installation_peer_outbound WHERE state != 'revoked' LIMIT 1")).first():
        raise RuntimeError("Withdraw live outgoing links before removing sender approval enforcement")
    for name in ("report_contact", "report_sequence", "send_revision", "send_approval"):
        op.drop_column("installation_peer_outbound", name)
