"""One device-owned, revisioned runtime contract for every Core installation."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update

from backend.db.device import Device, DeviceEvent, DeviceRuntimeFeatures
from three_mm_protocol.node_features import DeviceRuntimeFeaturesSnapshotV1


def lock_device(db, device):
    # Also serializes writes on SQLite; no platform-specific locking path.
    db.execute(
        update(Device)
        .where(Device.id == device.id)
        .values(updated_at=Device.updated_at)
    )


def read_runtime_features(db, device):
    return db.scalar(
        select(DeviceRuntimeFeatures)
        .where(DeviceRuntimeFeatures.device_id == device.id)
        .execution_options(populate_existing=True)
    )


def runtime_features_snapshot(db, device):
    row = read_runtime_features(db, device)
    return DeviceRuntimeFeaturesSnapshotV1(
        device_id=device.device_id,
        source="advertised" if row is not None else "legacy_unadvertised",
        revision=row.revision if row is not None else 0,
        declaration=row.declaration if row is not None else None,
        received_at=row.received_at if row is not None else None,
    )


def command_is_supported(db, device, command_type):
    row = read_runtime_features(db, device)
    # Unknown legacy support preserves the existing protocol. It is not a
    # declaration of support, nor does it bypass any authorization/OTA checks.
    return row is None or command_type in row.declaration["command_types"]


def replace_runtime_features(db, device, report):
    if report.device_id != device.device_id:
        raise ValueError("Runtime feature report identity mismatch")
    lock_device(db, device)
    row = read_runtime_features(db, device)
    revision = row.revision if row is not None else 0
    declaration = report.model_dump(mode="json", exclude={"expected_revision"})
    if (
        row is not None
        and row.declaration == declaration
        and report.expected_revision in {revision, revision - 1}
    ):
        return runtime_features_snapshot(db, device)
    if report.expected_revision != revision or revision >= 2_147_483_646:
        raise ValueError("Runtime feature revision changed; read protocol and retry")
    now = datetime.now(UTC)
    if row is None:
        row = DeviceRuntimeFeatures(device_id=device.id)
        db.add(row)
    row.revision = revision + 1
    row.declaration = declaration
    row.received_at = now
    db.add(
        DeviceEvent(
            device_id=device.id,
            event_id="evt_" + uuid4().hex,
            event_type="runtime.features.updated",
            payload={"revision": row.revision, "declaration": declaration},
            occurred_at=now,
        )
    )
    db.flush()
    return runtime_features_snapshot(db, device)
