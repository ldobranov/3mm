"""Keep retained application data discoverable after code/package removal."""
from alembic import op
import hashlib
import re
import sqlalchemy as sa

revision = '3e189f465708'
down_revision = '2c078e3546f7'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if 'application_retained_data' not in existing:
        op.create_table('application_retained_data',
            sa.Column('module_id', sa.String(160), primary_key=True),
            sa.Column('instance_id', sa.String(24), nullable=False),
            sa.Column('name', sa.String(255), nullable=True),
            sa.UniqueConstraint('instance_id', name='uq_application_retained_instance'),
            sa.CheckConstraint('length(module_id) > 0 AND length(module_id) <= 160', name='ck_application_retained_module'),
            sa.CheckConstraint('length(instance_id) = 24', name='ck_application_retained_instance'))
    else:
        inspector = sa.inspect(bind)
        columns = {item['name']: item for item in inspector.get_columns('application_retained_data')}
        if (set(columns) != {'module_id', 'instance_id', 'name'}
            or columns['module_id']['nullable'] or columns['instance_id']['nullable']
            or inspector.get_pk_constraint('application_retained_data')['constrained_columns'] != ['module_id']
            or not any(item['column_names'] == ['instance_id'] for item in inspector.get_unique_constraints('application_retained_data'))):
            raise RuntimeError('Existing retained application data schema is invalid')
    retained = sa.table('application_retained_data', sa.column('module_id'), sa.column('instance_id'), sa.column('name'))
    audit = sa.table('audit_logs', sa.column('id'), sa.column('action'), sa.column('entity_type'), sa.column('entity_name'))
    installations = sa.table('application_extension_installations', sa.column('module_id'))
    packages = sa.table('module_packages', sa.column('module_id'), sa.column('manifest', sa.JSON))
    installed = set(bind.execute(sa.select(installations.c.module_id)).scalars())
    already = set(bind.execute(sa.select(retained.c.module_id)).scalars())
    latest = {}
    for row in bind.execute(sa.select(audit.c.action, audit.c.entity_name).where(
            audit.c.entity_type == 'application_extension', audit.c.action.in_([
                'APPLICATION_EXTENSION_UNINSTALLED', 'APPLICATION_EXTENSION_DATA_ERASED',
            ])).order_by(audit.c.id)):
        module_id = row.entity_name
        if type(module_id) is str and len(module_id) <= 160 and re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)+', module_id):
            latest[module_id] = row.action
    for module_id, action in latest.items():
        if action != 'APPLICATION_EXTENSION_UNINSTALLED' or module_id in installed or module_id in already:
            continue
        name = module_id
        for manifest in bind.execute(sa.select(packages.c.manifest).where(packages.c.module_id == module_id)).scalars():
            value = manifest.get('name') if isinstance(manifest, dict) else None
            if type(value) is str and value.strip():
                name = value[:255]
                break
        bind.execute(retained.insert().values(module_id=module_id,
            instance_id=hashlib.sha256(module_id.encode('utf-8')).hexdigest()[:24], name=name))


def downgrade():
    bind = op.get_bind()
    retained = sa.table('application_retained_data', sa.column('module_id'))
    if bind.execute(sa.select(retained.c.module_id).limit(1)).first() is not None:
        raise RuntimeError('Erase retained application data before downgrading its cleanup catalog')
    op.drop_table('application_retained_data')
