"""M21 session discovery tests (M21.5): real registry wiring."""

import backend.database  # noqa: F401 - registers all table metadata
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.db.device import Device, DeviceCapabilityProvider, DeviceHeartbeat
from backend.services.interactive_session_discovery import build_session_discovery
from three_mm_protocol.interactive_session import SessionTargetV1

DEVICE_ONLINE = "dev_" + "1" * 32
DEVICE_OFFLINE = "dev_" + "2" * 32
DEVICE_NO_CAP = "dev_" + "3" * 32
DEVICE_REVOKED = "dev_" + "4" * 32
SESSION_CAP = "org.3mm.echo"
OTHER_CAP = "org.other.thing"


def _db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _device(db, device_id, *, revoked=False):
    device = Device(
        device_id=device_id,
        display_name=f"device-{device_id[-4:]}",
        role="node",
        protocol_version="1.0",
        approved_at=datetime.now(UTC),
        revoked_at=datetime.now(UTC) if revoked else None,
    )
    db.add(device)
    db.commit()
    return device


def _provider(db, device, capability_id):
    db.add(
        DeviceCapabilityProvider(
            device_id=device.id,
            provider_type="native",
            provider_id="org.3mm.echo",
            provider_version="1.0.0",
            capabilities=[{"capability_id": capability_id}],
            enabled=True,
            revision=1,
            reported_at=datetime.now(UTC),
        )
    )
    db.commit()


def _heartbeat(db, device, *, age_seconds=0):
    db.add(
        DeviceHeartbeat(
            device_id=device.id,
            protocol_version="1.0",
            payload={},
            received_at=datetime.now(UTC) - timedelta(seconds=age_seconds),
        )
    )
    db.commit()


def test_lists_only_devices_with_session_capability():
    db = _db()
    online = _device(db, DEVICE_ONLINE)
    _provider(db, online, SESSION_CAP)
    _heartbeat(db, online)
    no_cap = _device(db, DEVICE_NO_CAP)
    _heartbeat(db, no_cap)
    discovery = build_session_discovery(
        db, session_capability_ids={SESSION_CAP}
    )
    assert [t.device_id for t in discovery.targets] == [DEVICE_ONLINE]
    assert discovery.targets[0].available is True
    assert discovery.targets[0].unavailable_reason is None
    assert discovery.targets[0].sessions == (SESSION_CAP,)


def test_offline_device_with_capability_is_unavailable():
    db = _db()
    offline = _device(db, DEVICE_OFFLINE)
    _provider(db, offline, SESSION_CAP)
    discovery = build_session_discovery(
        db, session_capability_ids={SESSION_CAP}
    )
    target = discovery.targets[0]
    assert target.device_id == DEVICE_OFFLINE
    assert target.available is False
    assert target.unavailable_reason == "device_offline"


def test_revoked_device_is_not_listed():
    db = _db()
    revoked = _device(db, DEVICE_REVOKED, revoked=True)
    _provider(db, revoked, SESSION_CAP)
    _heartbeat(db, revoked)
    discovery = build_session_discovery(
        db, session_capability_ids={SESSION_CAP}
    )
    assert discovery.targets == ()


def test_non_session_capability_is_not_listed():
    db = _db()
    device = _device(db, DEVICE_NO_CAP)
    _provider(db, device, OTHER_CAP)
    _heartbeat(db, device)
    discovery = build_session_discovery(
        db, session_capability_ids={SESSION_CAP}
    )
    assert discovery.targets == ()


def test_remote_targets_are_merged():
    db = _db()
    remote = SessionTargetV1(
        device_id="dev_" + "9" * 32,
        display_name="remote",
        local=False,
        sessions=(SESSION_CAP,),
        available=True,
    )
    discovery = build_session_discovery(
        db,
        session_capability_ids={SESSION_CAP},
        remote_targets=[remote],
    )
    assert [t.device_id for t in discovery.targets] == [remote.device_id]
    assert discovery.targets[0].available is True
