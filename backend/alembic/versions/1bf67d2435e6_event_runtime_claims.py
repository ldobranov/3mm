"""Durable event attempt ownership across independent Runtime restarts."""
from alembic import op
import sqlalchemy as sa

revision = "1bf67d2435e6"
down_revision = "0ae56c1324d5"
branch_labels = None
depends_on = None


def upgrade():
    for name, kind in (("dispatch_id", sa.String(32)), ("dispatch_metadata", sa.JSON()),
                       ("retry_boot_id", sa.String(36)), ("retry_not_before_ms", sa.BigInteger())):
        op.add_column("application_event_deliveries", sa.Column(name, kind, nullable=True))


def downgrade():
    # Never discard an unresolved attempt and silently revive its handler.
    if op.get_bind().execute(sa.text("SELECT 1 FROM application_event_deliveries WHERE status = 'delivering' LIMIT 1")).first():
        raise RuntimeError("Resolve in-flight event deliveries before schema downgrade")
    with op.batch_alter_table("application_event_deliveries") as batch:
        for name in ("retry_not_before_ms", "retry_boot_id", "dispatch_metadata", "dispatch_id"):
            batch.drop_column(name)
