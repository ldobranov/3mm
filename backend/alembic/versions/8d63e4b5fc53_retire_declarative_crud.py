"""Preserve declarative data without owning application records in live Core.

Revision ID: 8d63e4b5fc53
Revises: 7c52d3a4eb42
"""
import hashlib,importlib.util,json
from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision='8d63e4b5fc53'
down_revision='7c52d3a4eb42'
branch_labels=None
depends_on=None
TABLES=('runtime_extension_definitions','runtime_entity_records')

def table(name):return sa.Table(name,sa.MetaData(),autoload_with=op.get_bind())

def upgrade():
    bind=op.get_bind();names=set(sa.inspect(bind).get_table_names())
    if not set(TABLES)<=names or any('retired_'+name in names for name in TABLES):
        raise RuntimeError('Declarative retirement requires intact previous tables and no archive collision')
    refs=table('module_package_retained_references');packages=table('module_packages')
    package_ids={(r.module_id,r.version):r.id for r in bind.execute(sa.select(packages.c.id,packages.c.module_id,packages.c.version))}
    definitions=table(TABLES[0])
    for row in bind.execute(sa.select(definitions.c.id,definitions.c.module_id,definitions.c.version)):
        package_id=package_ids.get((row.module_id,row.version))
        if package_id is not None:
            identity=hashlib.sha256(json.dumps([revision,row.id,package_id]).encode()).hexdigest()
            bind.execute(refs.insert().values(reference_id=identity,package_id=package_id,source='archive:'+revision,resource_ref='resource:'+str(row.id)))
    for name in TABLES:
        source=table(name)
        archive=op.create_table('retired_'+name,*(sa.Column(c.name,c.type,nullable=c.nullable,primary_key=c.primary_key) for c in source.c))
        bind.execute(archive.insert().from_select(list(source.c.keys()),sa.select(source)))
    for name in reversed(TABLES):op.drop_table(name)

def downgrade():
    bind=op.get_bind();names=set(sa.inspect(bind).get_table_names());archives=['retired_'+name for name in TABLES]
    if set(TABLES)&names or not set(archives)<=names:raise RuntimeError('Declarative recovery requires intact archives without live table collisions')
    refs=table('module_package_retained_references')
    own_refs=refs.c.source=='archive:'+revision
    if any(bind.scalar(sa.select(sa.func.count()).select_from(table(name))) for name in archives) or bind.scalar(sa.select(sa.func.count()).select_from(refs).where(own_refs)):
        raise RuntimeError('Populated declarative archives require verified backup recovery and a reviewed application data import')
    # Reuse only immutable historical DDL, not optional product models.
    for filename in ('07c9d1e2f3a4_add_runtime_extensions.py','18d2e3f4a5b6_add_runtime_selected_version.py'):
        spec=importlib.util.spec_from_file_location('historical_crud_'+filename[:12],Path(__file__).with_name(filename))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.upgrade()
    op.create_index('ix_runtime_extension_definitions_is_selected','runtime_extension_definitions',['is_selected'])
    for name in reversed(archives):op.drop_table(name)
