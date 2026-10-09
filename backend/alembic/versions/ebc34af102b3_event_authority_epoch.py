"""Pin event backlog to its original opt-in authority epoch; no grant backfill."""

from alembic import op
import sqlalchemy as sa

revision = "ebc34af102b3"
down_revision = "dab239e0f1a2"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns("application_event_deliveries")}
    if "authority_epoch" in columns:
        column = columns["authority_epoch"]
        if not column["nullable"] or not isinstance(column["type"], sa.String) or column["type"].length != 32 or column["default"] is not None:
            raise RuntimeError("Unexpected event authority schema; explicit recovery required")
        return
    op.add_column("application_event_deliveries", sa.Column("authority_epoch", sa.String(32), nullable=True))


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM application_event_deliveries WHERE authority_epoch IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Event authority history exists; restore a verified pre-upgrade backup")
    # Refuse before any DDL if a caller continues through the preceding sealed
    # authority migration: SQLite DDL cannot promise atomic multi-step rollback.
    for table in ("application_native_reviews", "application_authority_plans", "application_authority_grants", "application_authority_actions"):
        if connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError("Authority history exists; restore a verified pre-upgrade backup")
    if connection.execute(sa.text("SELECT 1 FROM application_extension_installations WHERE authority_mode = 'enforced' LIMIT 1")).first():
        raise RuntimeError("Enforced installations require verified recovery")
    with op.batch_alter_table("application_event_deliveries") as batch:
        batch.drop_column("authority_epoch")
