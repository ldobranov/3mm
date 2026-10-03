from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def test_feature_migration_is_additive_unique_and_reversible(monkeypatch):
    migration = import_module(
        "backend.alembic.versions.748cd3e4f5a6_device_runtime_features"
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE devices (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO devices VALUES (17)")
        monkeypatch.setattr(
            migration, "op", Operations(MigrationContext.configure(connection))
        )
        migration.upgrade()
        assert inspect(connection).get_indexes("device_runtime_features")[0]["unique"]
        migration.downgrade()
        assert "device_runtime_features" not in inspect(connection).get_table_names()
        assert connection.exec_driver_sql("SELECT id FROM devices").scalar_one() == 17
    engine.dispose()
