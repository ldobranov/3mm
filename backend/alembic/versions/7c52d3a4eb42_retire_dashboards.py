"""Retain dashboard data without live Core ownership or cascading deletion.

Revision ID: 7c52d3a4eb42
Revises: 6b41c293da31
"""
import hashlib
import importlib.util
import json
from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision = "7c52d3a4eb42"
down_revision = "6b41c293da31"
branch_labels = None
depends_on = None

PRODUCTS = ("displays", "widgets", "role_dashboard_grants")
SUBSETS = {"permissions": "retired_dashboard_permissions",
    "role_permissions": "retired_dashboard_role_permissions",
    "group_permissions": "retired_dashboard_group_permissions"}
REFERENCES = "module_package_retained_references"


def _table(name):
    return sa.Table(name, sa.MetaData(), autoload_with=op.get_bind())


def _copy(source, name, predicate=None):
    # No FK to active Core principals: deleting a user/role must not cascade into
    # preserved product evidence. Ownership IDs remain data for explicit export.
    def archive_type(column):
        # Reflected PostgreSQL native enums already exist. Historical evidence
        # keeps their labels without attempting to create another live enum type.
        return sa.String(max(map(len, column.type.enums))) if isinstance(column.type, sa.Enum) else column.type
    target = op.create_table(name, *(sa.Column(c.name, archive_type(c),
        nullable=c.nullable, primary_key=c.primary_key) for c in source.c))
    statement = sa.select(*(sa.cast(c, archive_type(c)) if isinstance(c.type, sa.Enum) else c for c in source.c))
    if predicate is not None: statement = statement.where(predicate)
    op.get_bind().execute(target.insert().from_select(list(source.c.keys()), statement))


def upgrade():
    bind = op.get_bind(); names = set(sa.inspect(bind).get_table_names())
    archives = {"retired_" + name for name in PRODUCTS} | set(SUBSETS.values())
    if archives & names or REFERENCES in names or not set(PRODUCTS) <= names:
        raise RuntimeError("Dashboard retirement requires an intact previous schema and no archive collision")
    refs = op.create_table(REFERENCES,
        sa.Column("reference_id", sa.String(64), primary_key=True),
        sa.Column("package_id", sa.Integer(), sa.ForeignKey("module_packages.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("resource_ref", sa.String(160), nullable=False))
    op.create_index("ix_module_package_retained_references_package_id", REFERENCES, ["package_id"])
    packages = _table("module_packages")
    package_ids = {(row.module_id, row.version): row.id
        for row in bind.execute(sa.select(packages.c.id, packages.c.module_id, packages.c.version))}
    widgets = _table("widgets")
    for row in bind.execute(sa.select(widgets.c.id, widgets.c.type)):
        parts = row.type.split(":", 3) if isinstance(row.type, str) else []
        if len(parts) != 4 or parts[0] != "compiled" or not parts[3]: continue
        package_id = package_ids.get((parts[1], parts[2]))
        if package_id is not None:
            identity = hashlib.sha256(json.dumps([revision, row.id, package_id]).encode()).hexdigest()
            bind.execute(refs.insert().values(reference_id=identity, package_id=package_id,
                source="archive:" + revision, resource_ref="resource:" + str(row.id)))
    for name in PRODUCTS: _copy(_table(name), "retired_" + name)
    for name, archive in SUBSETS.items():
        table = _table(name); predicate = table.c.entity_type.in_(("dashboard", "widget"))
        _copy(table, archive, predicate)
        bind.execute(table.delete().where(predicate))
    for name in reversed(PRODUCTS): op.drop_table(name)


def downgrade():
    bind = op.get_bind()
    archives = [*("retired_" + name for name in PRODUCTS), *SUBSETS.values()]
    names = set(sa.inspect(bind).get_table_names())
    if set(PRODUCTS) & names or not set(archives + [REFERENCES]) <= names:
        raise RuntimeError("Dashboard recovery requires intact archives and no current table collision")
    if any(bind.scalar(sa.select(sa.func.count()).select_from(_table(name))) for name in archives + [REFERENCES]):
        raise RuntimeError("Retained dashboard data/grants require verified backup recovery, not automatic authority restoration")
    # Empty retirement is reversible. Populated evidence never becomes live
    # authority again against potentially changed/reused Core principal IDs.
    path = Path(__file__).with_name("0f1e2d3c4b5a_legacy_schema_baseline.py")
    spec = importlib.util.spec_from_file_location("historical_dashboard_schema", path)
    historical = importlib.util.module_from_spec(spec); spec.loader.exec_module(historical)
    metadata = sa.MetaData(); sa.Table("users", metadata, autoload_with=bind)
    historical._historical_displays(metadata)
    metadata.create_all(bind, tables=[metadata.tables["displays"], metadata.tables["widgets"]])
    op.create_table("role_dashboard_grants",
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("display_id", sa.Integer(), sa.ForeignKey("displays.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_level", sa.String(20), nullable=False))
    op.drop_index("ix_module_package_retained_references_package_id", table_name=REFERENCES)
    op.drop_table(REFERENCES)
    for name in reversed(archives): op.drop_table(name)
