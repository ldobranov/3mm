"""Persistent account blocking and token revocation generation."""
from alembic import op
import sqlalchemy as sa

revision = "fc04b5c6d7e8"
down_revision = "ebf3a4b5c6d7"
branch_labels = None
depends_on = None

def upgrade():
    # The legacy baseline uses current model metadata on empty installations.
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('users')}
    if 'is_blocked' not in columns:
        op.add_column("users", sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    if 'token_version' not in columns:
        op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")))

def downgrade():
    op.drop_column("users", "token_version")
    op.drop_column("users", "is_blocked")
