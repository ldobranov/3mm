"""Bind new kiosk identities to an installation without adopting old credentials."""
from alembic import op
import sqlalchemy as sa
revision = 'b096b7e82f86'
down_revision = 'af85a6d71e75'
branch_labels = depends_on = None

def upgrade():
    for name in ('application_kiosk_enrollments','application_kiosk_terminals'):
        op.add_column(name,sa.Column('installation_incarnation',sa.String(32),nullable=True))

def downgrade():
    # Old code cannot enforce the new ownership boundary. Never silently turn
    # current credentials into identities with only a recyclable numeric owner.
    if any(op.get_bind().execute(sa.text('SELECT 1 FROM '+name+' LIMIT 1')).first() is not None for name in ('users','application_kiosk_terminals','application_kiosk_enrollments')):
        raise RuntimeError('Stable user subjects and kiosk identities require an explicitly reviewed recovery before downgrade')
    for name in ('application_kiosk_terminals','application_kiosk_enrollments'):
        op.drop_column(name,'installation_incarnation')
