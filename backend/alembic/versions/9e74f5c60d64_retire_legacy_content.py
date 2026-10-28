"""Retire pre-v2 content while preserving navigation and language selection.

Revision ID: 9e74f5c60d64
Revises: 8d63e4b5fc53
"""
import importlib.util
from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision='9e74f5c60d64'
down_revision='8d63e4b5fc53'
branch_labels=None
depends_on=None
TABLES=('extensions','pages','extension_tables','extension_fields','table_translations','migration_history','setting_translations','language_packs')
OPTIONAL='extension_multilingual_content'
SUBSETS={name:'retired_content_'+name for name in ('permissions','role_permissions','group_permissions')}
SELECTION='language_extension_installations'
# Frozen predecessor Core names are filled at authoring time, never inferred
# from an arbitrary registration claim or used to load product code.
CORE_TABLES=frozenset(['application_authority_actions', 'application_authority_grants', 'application_authority_plans', 'application_command_epochs', 'application_command_requests', 'application_connector_attempts', 'application_connector_bindings', 'application_event_cursors', 'application_event_deliveries', 'application_extension_installations', 'application_job_states', 'application_kiosk_enrollments', 'application_kiosk_terminals', 'application_native_reviews', 'application_permission_grants', 'application_policy_review_decisions', 'application_policy_reviews', 'application_retained_data', 'application_secret_references', 'application_sync_checkpoints', 'application_task_runs', 'application_task_schedules', 'audit_logs', 'core_authority_guard', 'core_installation_identity', 'device_capability_health', 'device_capability_providers', 'device_capability_states', 'device_commands', 'device_credentials', 'device_events', 'device_heartbeats', 'device_inventory_snapshots', 'device_pairing_requests', 'device_platform_states', 'device_runtime_features', 'device_states', 'devices', 'group_permissions', 'group_roles', 'groups', 'installation_peer_audit', 'installation_peer_inbound', 'installation_peer_nonces', 'installation_peer_origin', 'installation_peer_outbound', 'menus', 'module_installations', 'module_package_retained_references', 'module_packages', 'notifications', 'permissions', 'role_application_grants', 'role_permissions', 'roles', 'sessions', 'settings', 'theme_extension_installations', 'user_groups', 'user_roles', 'users'])

def table(name):return sa.Table(name,sa.MetaData(),autoload_with=op.get_bind())

def copy(source,name,predicate=None):
    def archived_type(c):
        return sa.String(max(map(len,c.type.enums))) if isinstance(c.type,sa.Enum) else c.type
    target=op.create_table(name,*(sa.Column(c.name,archived_type(c),nullable=c.nullable,primary_key=c.primary_key) for c in source.c))
    statement=sa.select(*(sa.cast(c,archived_type(c)) if isinstance(c.type,sa.Enum) else c for c in source.c))
    if predicate is not None:statement=statement.where(predicate)
    op.get_bind().execute(target.insert().from_select(list(source.c.keys()),statement))

def upgrade():
    bind=op.get_bind();inspector=sa.inspect(bind);names=set(inspector.get_table_names())
    sources=(*TABLES,*((OPTIONAL,) if OPTIONAL in names else ()))
    archives={'retired_'+name for name in (*TABLES,OPTIONAL)}|set(SUBSETS.values())
    if not set(TABLES)<=names or archives&names or SELECTION in names:
        raise RuntimeError('Content retirement requires intact predecessor tables without archive collisions')
    # Old registrations could claim arbitrary SQL tables, including Core tables.
    # Keep live Core data intact; require explicit ownership/export review for an
    # actual custom table instead of guessing which independent work to retire.
    for name in bind.scalars(sa.select(table('extension_tables').c.table_name)):
        if name in names and name not in CORE_TABLES and name not in sources and not name.startswith('retired_'):
            raise RuntimeError('Registered custom data requires an explicit ownership/export plan before content retirement')
    for name in names-set(sources):
        if any(fk.get('referred_table') in sources for fk in inspector.get_foreign_keys(name)):
            raise RuntimeError('A retained table references legacy content; review its ownership before retirement')
    packages=table('module_packages')
    language_packages={row.id for row in bind.execute(sa.select(packages.c.id,packages.c.manifest))
        if isinstance(row.manifest,dict) and (row.manifest.get('entrypoints') or {}).get('ui')=='language-extension.json'}
    selected=[dict(code=row.code,module_package_id=row.module_package_id,enabled=bool(row.is_active))
        for row in bind.execute(sa.select(table('language_packs'))) if row.module_package_id in language_packages]
    if len({row['module_package_id'] for row in selected})!=len(selected):
        raise RuntimeError('Conflicting language selections require review before retirement')
    for name in sources:copy(table(name),'retired_'+name)
    for name,archive in SUBSETS.items():
        source=table(name);owned=source.c.entity_type.in_(('page','extension'))
        copy(source,archive,owned);bind.execute(source.delete().where(owned))
    selection=op.create_table(SELECTION,
        sa.Column('code',sa.String(10),primary_key=True),
        sa.Column('module_package_id',sa.Integer(),sa.ForeignKey('module_packages.id',ondelete='RESTRICT'),nullable=False,unique=True),
        sa.Column('enabled',sa.Boolean(),nullable=False,server_default=sa.false()))
    if selected:bind.execute(selection.insert(),selected)
    for name in reversed(sources):op.drop_table(name)

def downgrade():
    bind=op.get_bind();names=set(sa.inspect(bind).get_table_names())
    archives=['retired_'+name for name in TABLES]+list(SUBSETS.values())
    if 'retired_'+OPTIONAL in names:archives.append('retired_'+OPTIONAL)
    if set(TABLES)&names or not set(archives+[SELECTION])<=names:
        raise RuntimeError('Content recovery requires intact archives and no live table collisions')
    if 'retired_'+OPTIONAL in names:
        raise RuntimeError('Optional prototype-table schema requires verified prior-backup recovery')
    if any(bind.scalar(sa.select(sa.func.count()).select_from(table(name))) for name in archives+[SELECTION]):
        raise RuntimeError('Populated content/language history requires verified prior-backup recovery, not automatic authority restoration')
    path=Path(__file__).with_name('0f1e2d3c4b5a_legacy_schema_baseline.py')
    spec=importlib.util.spec_from_file_location('historical_content',path);historical=importlib.util.module_from_spec(spec);spec.loader.exec_module(historical)
    metadata=sa.MetaData()
    for name in ('users','settings','module_packages'):sa.Table(name,metadata,autoload_with=bind)
    historical._historical_content(metadata)
    metadata.create_all(bind,tables=[metadata.tables[name] for name in TABLES])
    op.drop_table(SELECTION)
    for name in reversed(archives):op.drop_table(name)
