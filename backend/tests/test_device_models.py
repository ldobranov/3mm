from datetime import datetime, timedelta, timezone
from importlib import import_module

import backend.database  # noqa: F401 - register complete model metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.db.base import Base
from backend.db.device import (
    Device,
    DeviceCredential,
    DeviceHeartbeat,
    DeviceInventorySnapshot,
    DevicePairingRequest,
)
from backend.db.user import User
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session


def test_device_registry_round_trip_uses_derived_online_state() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as db:
        owner = User(
            username="owner",
            email="owner@example.com",
            hashed_password="not-a-real-hash",
            role="admin",
        )
        device = Device(
            device_id="dev_0123456789abcdef0123456789abcdef",
            display_name="Workshop Pi",
            role="standalone",
            protocol_version="1.0",
            approved_at=now,
        )
        device.credentials.append(
            DeviceCredential(
                credential_id="cred_test",
                secret_hash="one-way-hash",
            )
        )
        device.inventory_snapshots.append(
            DeviceInventorySnapshot(inventory={"hostname": "rasp-3mm"})
        )
        device.heartbeats.append(
            DeviceHeartbeat(protocol_version="1.0", payload={"ready": True})
        )
        pairing = DevicePairingRequest(
            code_hash="pairing-code-hash",
            requested_device_id=device.device_id,
            public_key="test-public-key",
            created_by_user_id=1,
            expires_at=now + timedelta(minutes=10),
            device=device,
        )
        db.add_all([owner, device, pairing])
        db.commit()

        stored = db.query(Device).filter_by(device_id=device.device_id).one()
        assert stored.credentials[0].secret_hash == "one-way-hash"
        assert stored.inventory_snapshots[0].inventory["hostname"] == "rasp-3mm"
        assert stored.heartbeats[0].payload == {"ready": True}
        assert stored.pairing_requests[0].code_hash == "pairing-code-hash"
        assert not hasattr(stored, "online")

    engine.dispose()


def test_device_registry_tables_are_registered_for_migrations() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    assert {
        "devices",
        "device_credentials",
        "device_pairing_requests",
        "device_inventory_snapshots",
        "device_heartbeats",
    }.issubset(inspect(engine).get_table_names())

    engine.dispose()


def test_device_registry_migration_upgrades_and_downgrades_sqlite() -> None:
    migration = import_module(
        "backend.alembic.versions.7a31d5d293e1_add_device_registry"
    )
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        User.__table__.create(connection)
        migration_operations = Operations(MigrationContext.configure(connection))
        original_operations = migration.op
        migration.op = migration_operations
        try:
            migration.upgrade()
            assert "devices" in inspect(connection).get_table_names()
            assert "device_heartbeats" in inspect(connection).get_table_names()

            migration.downgrade()
            assert "devices" not in inspect(connection).get_table_names()
        finally:
            migration.op = original_operations

    engine.dispose()
