from importlib import import_module
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from backend.db.base import Base
import backend.db.module  # noqa: F401

def test_module_tables_are_registered():
    assert "module_packages" in Base.metadata.tables
    assert "module_installations" in Base.metadata.tables

def test_module_migration_upgrades_and_downgrades_sqlite():
    migration=import_module("backend.alembic.versions.b274fa0b1243_add_module_lifecycle")
    engine=create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        operations=Operations(MigrationContext.configure(connection)); original=migration.op; migration.op=operations
        try:
            migration.upgrade(); names=set(inspect(connection).get_table_names())
            assert {"module_packages","module_installations"} <= names
            migration.downgrade(); names=set(inspect(connection).get_table_names())
            assert "module_packages" not in names and "module_installations" not in names
        finally: migration.op=original
    engine.dispose()
