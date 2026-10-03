from datetime import UTC, datetime
from importlib import import_module
import sqlite3

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

import backend.database  # noqa: F401 - register all related ORM models
from backend.db.device import (
    Device,
    DeviceCapabilityProvider,
    DeviceCredential,
    DeviceState,
)
from backend.db.module import ModuleInstallation, ModulePackage
from backend.services.device_capability_registry import (
    registered_capabilities,
    replace_provider,
)
from backend.services.device_runtime_features import (
    replace_runtime_features,
    runtime_features_snapshot,
)
from three_mm_protocol.node_features import (
    DeviceRuntimeFeaturesReportV1,
    MANDATORY_NODE_FEATURES,
)
from backend.tests.test_migration_history import _alembic
from three_mm_protocol import CapabilityProviderReportV1


def test_provider_migration_is_additive_and_reversible(monkeypatch):
    migration = import_module(
        "backend.alembic.versions.637bc2d3e4f5_device_capability_providers"
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE devices (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO devices VALUES (17)")
        monkeypatch.setattr(
            migration, "op", Operations(MigrationContext.configure(connection))
        )
        migration.upgrade()
        assert "device_capability_providers" in inspect(connection).get_table_names()
        assert inspect(connection).get_unique_constraints(
            "device_capability_providers"
        )[0]["column_names"] == ["device_id", "provider_type", "provider_id"]
        migration.downgrade()
        assert (
            "device_capability_providers" not in inspect(connection).get_table_names()
        )
        assert connection.exec_driver_sql("SELECT id FROM devices").scalar_one() == 17
    engine.dispose()


def test_populated_upgrade_and_sqlite_backup_preserve_module_and_native_providers(
    tmp_path,
):
    path = tmp_path / "previous.db"
    url = f"sqlite:///{path.as_posix()}"
    _alembic(url, "upgrade", "526ab1c2d3e4")
    engine = create_engine(url)
    device_id = "dev_" + "1" * 32
    with Session(engine) as db:
        device = Device(
            device_id=device_id,
            role="standalone",
            protocol_version="1.0",
            approved_at=datetime.now(UTC),
        )
        package = ModulePackage(
            module_id="org.example.module",
            version="1.0",
            manifest={},
            sha256="a" * 64,
            size_bytes=1,
            file_path="unused",
            registrations=[{"kind": "capability", "registration_id": "module.control"}],
        )
        db.add_all([device, package])
        db.flush()
        db.add(
            DeviceCredential(
                device_id=device.id,
                credential_id="cred_existing",
                secret_hash="unchanged",
            )
        )
        db.add(
            DeviceState(
                device_id=device.id,
                desired_revision=7,
                desired_state={"keep": True},
                reported_revision=6,
            )
        )
        db.add(
            ModuleInstallation(
                device_id=device.id,
                module_package_id=package.id,
                module_id=package.module_id,
                installed_version="1.0",
                desired_version="1.0",
                status="succeeded",
                enabled=True,
            )
        )
        db.commit()
    _alembic(url, "upgrade", "head")
    _alembic(url, "check")
    with Session(engine) as db:
        device = db.query(Device).filter_by(device_id=device_id).one()
        assert registered_capabilities(db, device)[0]["provider_type"] == "agent_module"
        assert db.query(DeviceCredential).one().secret_hash == "unchanged"
        assert db.query(DeviceState).one().desired_revision == 7
        provider = replace_provider(
            db,
            device,
            CapabilityProviderReportV1.model_validate(
                {
                    "schema_version": 1,
                    "device_id": device_id,
                    "provider_type": "native",
                    "provider_id": "example.runtime",
                    "provider_version": "0.1",
                    "expected_revision": 0,
                    "capabilities": [{"capability_id": "firmware.control"}],
                }
            ),
        )
        provider.enabled = False
        replace_runtime_features(
            db,
            device,
            DeviceRuntimeFeaturesReportV1(
                device_id=device_id,
                runtime_name="reference",
                runtime_version="1",
                features=tuple(sorted(MANDATORY_NODE_FEATURES)),
                command_types=("capability.invoke",),
                expected_revision=0,
            ),
        )
        db.commit()
    engine.dispose()
    backup = tmp_path / "restored.db"
    with sqlite3.connect(path) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
    restored_engine = create_engine(f"sqlite:///{backup.as_posix()}")
    with Session(restored_engine) as db:
        device = db.query(Device).filter_by(device_id=device_id).one()
        assert (
            registered_capabilities(db, device)[0]["provider_id"]
            == "org.example.module"
        )
        provider = db.query(DeviceCapabilityProvider).one()
        assert (
            provider.revision,
            provider.enabled,
            provider.capabilities[0]["capability_id"],
        ) == (1, False, "firmware.control")
        assert db.query(DeviceCredential).one().credential_id == "cred_existing"
        assert db.query(DeviceState).one().desired_state == {"keep": True}
        assert db.query(ModuleInstallation).one().installed_version == "1.0"
        features = runtime_features_snapshot(db, device)
        assert features.revision == 1 and features.source == "advertised"
        assert features.declaration.command_types == ("capability.invoke",)
    restored_engine.dispose()
