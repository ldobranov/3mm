from datetime import datetime, timedelta, timezone

import backend.database  # noqa: F401
from backend.db.base import Base
from backend.db.device import Device
from backend.services.device_commands import (
    command_envelope,
    deliver_next_command,
    queue_command,
    record_command_result,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from three_mm_protocol import AgentCommandResult

DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"


def test_command_lifecycle_and_idempotent_queueing() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    with Session(engine) as db:
        device = Device(
            device_id=DEVICE_ID,
            display_name="test-pi",
            role="node",
            protocol_version="1.0",
            approved_at=now,
        )
        db.add(device)
        db.commit()

        first = queue_command(
            db,
            device=device,
            command_type="agent.refresh_inventory",
            payload={},
            idempotency_key="refresh-1",
            ttl_seconds=60,
            now=now,
        )
        duplicate = queue_command(
            db,
            device=device,
            command_type="agent.refresh_inventory",
            payload={},
            idempotency_key="refresh-1",
            ttl_seconds=60,
            now=now,
        )
        assert duplicate.id == first.id

        delivered = deliver_next_command(db, device=device, now=now + timedelta(seconds=1))
        assert delivered is not None
        assert delivered.status == "delivered"
        assert command_envelope(delivered, DEVICE_ID).command_type == "agent.refresh_inventory"

        completed = record_command_result(
            db,
            device=device,
            result=AgentCommandResult(
                command_id=delivered.command_id,
                device_id=DEVICE_ID,
                status="succeeded",
                completed_at=now + timedelta(seconds=2),
                output={"published": True},
            ),
        )
        assert completed.status == "succeeded"
        assert completed.result == {"published": True}
    engine.dispose()


def test_expired_command_is_not_delivered() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    with Session(engine) as db:
        device = Device(
            device_id=DEVICE_ID,
            display_name="test-pi",
            role="node",
            protocol_version="1.0",
            approved_at=now,
        )
        db.add(device)
        db.commit()
        command = queue_command(
            db,
            device=device,
            command_type="agent.refresh_inventory",
            payload={},
            idempotency_key="expired-1",
            ttl_seconds=5,
            now=now,
        )

        assert deliver_next_command(db, device=device, now=now + timedelta(seconds=6)) is None
        db.refresh(command)
        assert command.status == "expired"
    engine.dispose()
