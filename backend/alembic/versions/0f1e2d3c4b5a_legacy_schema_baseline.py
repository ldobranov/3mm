"""create the legacy Core schema baseline

Revision ID: 0f1e2d3c4b5a
Revises:

The project originally used ``Base.metadata.create_all()`` before introducing
Alembic.  This baseline captures those pre-device tables so a clean database
can now be built entirely through the migration history.
"""

from alembic import op
from sqlalchemy import MetaData
import sqlalchemy as sa

revision = "0f1e2d3c4b5a"
down_revision = None
branch_labels = None
depends_on = None


POST_BASELINE_TABLES = {
    "language_extension_installations",
    "module_package_retained_references",
    "application_native_reviews", "application_authority_plans",
    "application_authority_grants", "application_authority_actions",
    "application_policy_reviews", "application_policy_review_decisions",
    "core_authority_guard",
    "installation_peer_origin", "installation_peer_inbound",
    "installation_peer_outbound", "installation_peer_nonces", "installation_peer_audit",
    "core_installation_identity",
    "application_command_epochs",
    "application_command_requests",
    "application_task_runs",
    "application_task_schedules",
    "group_roles",
    "role_application_grants",
    "role_dashboard_grants",
    "devices",
    "device_credentials",
    "device_pairing_requests",
    "device_inventory_snapshots",
    "device_heartbeats",
    "device_commands",
    "device_states",
    "device_events",
    "device_capability_states",
    "device_capability_providers",
    "device_runtime_features",
    "device_platform_states",
    "device_capability_health",
    "module_packages",
    "module_installations",
    "theme_extension_installations",
    "application_extension_installations",
    "application_retained_data",
    "application_permission_grants",
    "application_kiosk_enrollments",
    "application_kiosk_terminals",
    "application_event_deliveries",
    "application_event_cursors",
    "application_secret_references",
    "application_connector_bindings",
    "application_connector_attempts",
    "application_job_states",
    "application_sync_checkpoints",
    "automation_proposals",
    "automation_revisions",
    "automation_audit_events",
    "ai_credit_accounts",
    "ai_jobs",
    "ai_usage_ledger",
    "runtime_extension_definitions",
    "runtime_entity_records",
    "extension_projects",
    "extension_project_files",
    "extension_project_builds",
}


def _historical_displays(metadata):
    # Freeze the original schema here: retired products must not be imported to
    # reconstruct historical migrations on a clean installation or downgrade.
    sa.Table("displays", metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "slug", name="uq_user_slug"))
    sa.Table("widgets", metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("display_id", sa.Integer(), sa.ForeignKey("displays.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(), nullable=False), sa.Column("config", sa.JSON(), nullable=False),
        *(sa.Column(name, sa.Integer(), nullable=False) for name in ("x", "y", "width", "height", "z_index")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)))



def _historical_content(metadata):
    # Original pre-v2 content DDL, independent of retired product imports.
    sa.Table('extensions', metadata,
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('author', sa.String(), nullable=True),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=True),
        sa.Column('integrity_hash', sa.String(), nullable=True),
        sa.Column('security_status', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    sa.Table('pages', metadata,
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('title', sa.JSON(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=True),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('is_public', sa.Boolean(), nullable=False),
        sa.Column('allowed_roles', sa.JSON(), nullable=False),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.UniqueConstraint('slug'))
    sa.Table('extension_tables', metadata,
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('extension_id', sa.Integer(), sa.ForeignKey('extensions.id'), nullable=False),
        sa.Column('table_name', sa.String(length=100), nullable=False),
        sa.Column('table_schema', sa.JSON(), nullable=False),
        sa.Column('translatable_fields', sa.JSON(), nullable=False),
        sa.Column('primary_key_field', sa.String(length=100), nullable=False),
        sa.Column('is_multilingual', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True))
    sa.Index('ix_extension_tables_id', metadata.tables['extension_tables'].c['id'], unique=False)
    sa.Table('extension_fields', metadata,
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('extension_id', sa.Integer(), sa.ForeignKey('extensions.id'), nullable=False),
        sa.Column('table_name', sa.String(length=100), nullable=False),
        sa.Column('field_name', sa.String(length=100), nullable=False),
        sa.Column('field_type', sa.String(length=50), nullable=False),
        sa.Column('is_translatable', sa.Boolean(), nullable=True),
        sa.Column('validation_rules', sa.JSON(), nullable=True),
        sa.Column('field_order', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True))
    sa.Index('ix_extension_fields_id', metadata.tables['extension_fields'].c['id'], unique=False)
    sa.Table('table_translations', metadata,
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('extension_id', sa.Integer(), sa.ForeignKey('extensions.id'), nullable=False),
        sa.Column('table_name', sa.String(length=100), nullable=False),
        sa.Column('record_id', sa.Integer(), nullable=False),
        sa.Column('language_code', sa.String(length=10), nullable=False),
        sa.Column('translation_data', sa.JSON(), nullable=False),
        sa.Column('translation_coverage', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('is_fallback', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True))
    sa.Index('ix_table_translations_id', metadata.tables['table_translations'].c['id'], unique=False)
    sa.Table('migration_history', metadata,
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('migration_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('records_processed', sa.Integer(), nullable=True),
        sa.Column('total_records', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True))
    sa.Index('ix_migration_history_id', metadata.tables['migration_history'].c['id'], unique=False)
    sa.Table('setting_translations', metadata,
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('setting_id', sa.Integer(), sa.ForeignKey('settings.id'), nullable=False),
        sa.Column('language_code', sa.String(length=10), nullable=False),
        sa.Column('translated_value', sa.Text(), nullable=True),
        sa.Column('translated_description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True))
    sa.Index('ix_setting_translations_id', metadata.tables['setting_translations'].c['id'], unique=False)
    sa.Table('language_packs', metadata,
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('code', sa.String(length=10), nullable=False),
        sa.Column('native_name', sa.String(length=255), nullable=False),
        sa.Column('locale', sa.String(length=20), nullable=False),
        sa.Column('direction', sa.String(length=10), nullable=True),
        sa.Column('frontend_coverage', sa.Integer(), nullable=True),
        sa.Column('backend_coverage', sa.Integer(), nullable=True),
        sa.Column('extensions_coverage', sa.Integer(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('date_format', sa.String(length=50), nullable=True),
        sa.Column('time_format', sa.String(length=20), nullable=True),
        sa.Column('number_format', sa.JSON(), nullable=True),
        sa.Column('frontend_translations', sa.JSON(), nullable=True),
        sa.Column('backend_translations', sa.JSON(), nullable=True),
        sa.Column('extensions_translations', sa.JSON(), nullable=True),
        sa.Column('extension_id', sa.Integer(), sa.ForeignKey('extensions.id'), nullable=True),
        sa.Column('module_package_id', sa.Integer(), sa.ForeignKey('module_packages.id', name='fk_language_pack_module'), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('code'))
    sa.Index('ix_language_packs_id', metadata.tables['language_packs'].c['id'], unique=False)

def _baseline_metadata() -> MetaData:
    # Reading the revision graph must not initialize the runtime database.
    # Only an actual upgrade/downgrade needs the populated model metadata.
    import backend.database  # noqa: F401 - populate model metadata
    from backend.db.base import Base

    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name not in POST_BASELINE_TABLES:
            table.to_metadata(metadata)
    # This identity is introduced and backfilled by af85a6d71e75. Keep the
    # historical baseline independent of the current ORM's additive column.
    users = metadata.tables.get("users")
    if users is not None and "subject_id" in users.c:
        column = users.c.subject_id
        for index in list(users.indexes):
            if column in index.columns.values(): users.indexes.remove(index)
        users._columns.remove(column)
    _historical_displays(metadata)
    _historical_content(metadata)
    languages = metadata.tables.get("language_packs")
    if languages is not None and "module_package_id" in languages.c:
        column = languages.c.module_package_id
        for constraint in list(languages.constraints):
            if column in constraint.columns.values():
                languages.constraints.remove(constraint)
        for foreign_key in list(column.foreign_keys):
            languages.foreign_keys.discard(foreign_key)
        languages._columns.remove(column)
    return metadata


def upgrade() -> None:
    _baseline_metadata().create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    metadata = _baseline_metadata()
    metadata.drop_all(bind=op.get_bind(), checkfirst=True)
