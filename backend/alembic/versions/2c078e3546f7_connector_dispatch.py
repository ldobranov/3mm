"""Durable connector dispatch correlation without credentials or request bodies."""
from alembic import op
import sqlalchemy as sa
revision = "2c078e3546f7"
down_revision = "1bf67d2435e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("application_connector_attempts", sa.Column("dispatch_metadata", sa.JSON(), nullable=True))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM application_connector_attempts WHERE outcome = 'in_progress' AND dispatch_metadata IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Resolve in-flight connector attempts before schema downgrade")
    with op.batch_alter_table("application_connector_attempts") as batch:
        batch.drop_column("dispatch_metadata")
