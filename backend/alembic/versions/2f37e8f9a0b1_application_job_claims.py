"""Durable singleton job claims and safe scheduler diagnostics."""
from alembic import op
import sqlalchemy as sa

revision = '2f37e8f9a0b1'
down_revision = '1e26d7e8f9a0'
branch_labels = None
depends_on = None


def upgrade():
    for name, kind in (
        ('lease_token', sa.String(32)), ('lease_instance_id', sa.String(24)),
        ('lease_package_id', sa.Integer()), ('last_scheduled_at', sa.DateTime(timezone=True)),
        ('last_duration_ms', sa.Integer()), ('last_lateness_ms', sa.Integer()),
    ):
        op.add_column('application_job_states', sa.Column(name, kind, nullable=True))
    op.execute("UPDATE application_job_states SET lease_token=lower(hex(randomblob(16))), last_outcome='unknown', last_error='legacy_inflight' WHERE lease_until IS NOT NULL OR last_outcome='running'")


def downgrade():
    with op.batch_alter_table('application_job_states') as batch:
        for name in ('last_lateness_ms', 'last_duration_ms', 'last_scheduled_at',
                     'lease_package_id', 'lease_instance_id', 'lease_token'):
            batch.drop_column(name)
