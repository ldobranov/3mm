"""Group roles and resource-scoped role grants."""
from alembic import op
import sqlalchemy as sa

revision = '0d15c6d7e8f9'
down_revision = 'fc04b5c6d7e8'
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if 'group_roles' not in existing:
        op.create_table('group_roles',
            sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id', ondelete='CASCADE'), primary_key=True),
            sa.Column('role_id', sa.Integer(), sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True))
    if 'role_application_grants' not in existing:
        op.create_table('role_application_grants',
            sa.Column('role_id', sa.Integer(), sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
            sa.Column('installation_id', sa.Integer(), sa.ForeignKey('application_extension_installations.id', ondelete='CASCADE'), primary_key=True),
            sa.Column('permission_id', sa.String(100), primary_key=True))
    if 'role_dashboard_grants' not in existing:
        op.create_table('role_dashboard_grants',
            sa.Column('role_id', sa.Integer(), sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
            sa.Column('display_id', sa.Integer(), sa.ForeignKey('displays.id', ondelete='CASCADE'), primary_key=True),
            sa.Column('permission_level', sa.String(20), nullable=False))


def downgrade():
    op.drop_table('role_dashboard_grants')
    op.drop_table('role_application_grants')
    op.drop_table('group_roles')
