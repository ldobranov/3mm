"""
Add HiveOS Keys Table
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_hiveos_keys_table'
down_revision = '7eb6dd15a4db'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'hiveos_keys',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('user_id', sa.Integer, nullable=False),
        sa.Column('api_key', sa.String, nullable=False)
    )

def downgrade():
    op.drop_table('hiveos_keys')
