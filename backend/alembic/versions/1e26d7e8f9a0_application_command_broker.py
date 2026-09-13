"""Installation-scoped physical commands and lifecycle generation."""
from alembic import op
import sqlalchemy as sa
revision = '1e26d7e8f9a0'
down_revision = '0d15c6d7e8f9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('application_command_epochs',
        sa.Column('installation_id', sa.Integer(), sa.ForeignKey('application_extension_installations.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('generation', sa.String(32), nullable=False))
    op.create_table('application_command_requests',
        sa.Column('command_id', sa.String(64), sa.ForeignKey('device_commands.command_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('installation_id', sa.Integer(), sa.ForeignKey('application_extension_installations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('generation', sa.String(32), nullable=False),
        sa.Column('package_id', sa.Integer(), sa.ForeignKey('module_packages.id'), nullable=False),
        sa.Column('claimed', sa.Boolean(), nullable=False),
        sa.Column('passage_event_id', sa.String(64), nullable=True))


def downgrade():
    op.drop_table('application_command_requests')
    op.drop_table('application_command_epochs')
