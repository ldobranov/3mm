from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def test_capability_state_migration_upgrades_and_downgrades_sqlite():
    migration = import_module("backend.alembic.versions.3af4b5c6d7e8_add_capability_states")
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE devices (id INTEGER PRIMARY KEY)")
        operations = Operations(MigrationContext.configure(connection))
        original = migration.op
        migration.op = operations
        try:
            migration.upgrade()
            assert "device_capability_states" in inspect(connection).get_table_names()
            indexes = {item["name"] for item in inspect(connection).get_indexes("device_capability_states")}
            assert "ix_device_capability_states_device_id" in indexes
            migration.downgrade()
            assert "device_capability_states" not in inspect(connection).get_table_names()
        finally:
            migration.op = original
    engine.dispose()
