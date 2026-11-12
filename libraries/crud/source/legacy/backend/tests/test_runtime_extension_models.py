from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from backend.db.base import Base
import backend.db.runtime_extension  # noqa: F401


def test_runtime_extension_tables_are_registered():
    assert "runtime_extension_definitions" in Base.metadata.tables
    assert "runtime_entity_records" in Base.metadata.tables


def test_runtime_extension_migration_upgrades_and_downgrades_sqlite():
    migration = import_module(
        "backend.alembic.versions.07c9d1e2f3a4_add_runtime_extensions"
    )
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        operations = Operations(MigrationContext.configure(connection))
        original = migration.op
        migration.op = operations
        try:
            migration.upgrade()
            names = set(inspect(connection).get_table_names())
            assert {"runtime_extension_definitions", "runtime_entity_records"} <= names

            migration.downgrade()
            names = set(inspect(connection).get_table_names())
            assert "runtime_extension_definitions" not in names
            assert "runtime_entity_records" not in names
        finally:
            migration.op = original
    engine.dispose()


def test_selected_version_migration_adds_lifecycle_constraints():
    base_migration = import_module(
        "backend.alembic.versions.07c9d1e2f3a4_add_runtime_extensions"
    )
    selected_migration = import_module(
        "backend.alembic.versions.18d2e3f4a5b6_add_runtime_selected_version"
    )
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        operations = Operations(MigrationContext.configure(connection))
        original_base = base_migration.op
        original_selected = selected_migration.op
        base_migration.op = operations
        selected_migration.op = operations
        try:
            base_migration.upgrade()
            selected_migration.upgrade()
            inspector = inspect(connection)
            columns = {item["name"] for item in inspector.get_columns("runtime_extension_definitions")}
            indexes = {item["name"] for item in inspector.get_indexes("runtime_extension_definitions")}
            assert "is_selected" in columns
            assert {
                "uq_runtime_extension_active_module",
                "uq_runtime_extension_selected_module",
            } <= indexes
        finally:
            selected_migration.op = original_selected
            base_migration.op = original_base
    engine.dispose()
