"""Retire product tables and AI settings without losing historical data.

Revision ID: 6b41c293da31
Revises: 5a30b182c920

Retired tables are recovery evidence, excluded from live Core metadata. This
revision does not activate a replacement application or issue a device command.
"""
from alembic import op
import sqlalchemy as sa

revision = "6b41c293da31"
down_revision = "5a30b182c920"
branch_labels = None
depends_on = None

PRODUCT_TABLES = (
    "extension_projects", "extension_project_files", "extension_project_builds",
    "automation_proposals", "automation_revisions", "automation_audit_events",
    "ai_credit_accounts", "ai_jobs", "ai_usage_ledger",
)
SETTING_KEYS = ("ai_provider", "ai_groq_api_key", "ai_openrouter_api_key")


def _table(name):
    return sa.Table(name, sa.MetaData(), autoload_with=op.get_bind())


def _archive_subset(source, name, predicate):
    # Historical snapshots have no active FK/cascade relationship to Core rows.
    target = op.create_table(name, *(
        sa.Column(column.name, column.type, nullable=column.nullable,
                  primary_key=column.primary_key)
        for column in source.columns
    ))
    columns = list(source.c.keys())
    op.get_bind().execute(target.insert().from_select(columns, sa.select(source).where(predicate)))


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    archives = {"retired_" + name for name in PRODUCT_TABLES} | {
        "retired_ai_settings", "retired_ai_setting_translations"}
    if archives & tables or not set(PRODUCT_TABLES) <= tables:
        raise RuntimeError("Product retirement requires an intact previous schema and no archive collision")
    settings = _table("settings")
    translations = _table("setting_translations")
    predicate = settings.c.key.in_(SETTING_KEYS)
    translated = translations.c.setting_id.in_(sa.select(settings.c.id).where(predicate))
    _archive_subset(translations, "retired_ai_setting_translations", translated)
    _archive_subset(settings, "retired_ai_settings", predicate)
    op.get_bind().execute(translations.delete().where(translated))
    op.get_bind().execute(settings.delete().where(predicate))
    for name in PRODUCT_TABLES:
        op.rename_table(name, "retired_" + name)


def downgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    archives = {"retired_" + name for name in PRODUCT_TABLES} | {
        "retired_ai_settings", "retired_ai_setting_translations"}
    if set(PRODUCT_TABLES) & tables or not archives <= tables:
        raise RuntimeError("Product recovery requires intact retired tables and no live name collision")
    settings, saved = _table("settings"), _table("retired_ai_settings")
    translations, saved_translations = _table("setting_translations"), _table("retired_ai_setting_translations")
    bind = op.get_bind()
    if (bind.scalar(sa.select(sa.func.count()).select_from(settings).where(
            sa.or_(settings.c.id.in_(sa.select(saved.c.id)), settings.c.key.in_(SETTING_KEYS))))
            or bind.scalar(sa.select(sa.func.count()).select_from(translations).where(
                translations.c.id.in_(sa.select(saved_translations.c.id))))):
        raise RuntimeError("Product recovery would overwrite current settings; use a verified backup")
    for name in PRODUCT_TABLES:
        op.rename_table("retired_" + name, name)
    for current, archived in ((settings, saved), (translations, saved_translations)):
        bind.execute(current.insert().from_select(list(current.c.keys()), sa.select(archived)))
    op.drop_table("retired_ai_setting_translations")
    op.drop_table("retired_ai_settings")
