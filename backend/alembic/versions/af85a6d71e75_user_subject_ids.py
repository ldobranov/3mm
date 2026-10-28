"""Stable application actor subjects without rebuilding users or their FKs."""
import uuid
from alembic import op
import sqlalchemy as sa

revision = "af85a6d71e75"
down_revision = "9e74f5c60d64"
branch_labels = None
depends_on = None


def upgrade():
    # Additive migration: account IDs/passwords/roles/sessions and every referencing
    # table stay in place. No reset, grant insertion or runtime identity creation.
    op.add_column("users", sa.Column("subject_id", sa.String(36), nullable=True))
    table = sa.table("users", sa.column("id", sa.Integer), sa.column("subject_id", sa.String(36)))
    connection = op.get_bind()
    for identifier in connection.execute(sa.select(table.c.id)).scalars():
        connection.execute(table.update().where(table.c.id == identifier).values(subject_id="usr_" + uuid.uuid4().hex))
    op.create_index("ix_users_subject_id", "users", ["subject_id"], unique=True)


def downgrade():
    # These subjects may already own application business records. Erasing and
    # regenerating them would silently orphan or reassign that ownership.
    if op.get_bind().execute(sa.text("SELECT 1 FROM users LIMIT 1")).first() is not None:
        raise RuntimeError("Stable user subjects cannot be removed from a populated database; preserve identities and use an explicitly reviewed recovery plan")
    op.drop_index("ix_users_subject_id", table_name="users")
    op.drop_column("users", "subject_id")
