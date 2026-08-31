import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from three_mm_protocol import AgentCommand, AgentCommandResult

import backend.database  # noqa: F401
from backend.db.base import Base
from backend.db.device import Device, DeviceCommand
from backend.routes.device_commands import next_command
from backend.services.device_commands import (
    command_envelope,
    commit_queued_command,
    deliver_next_command,
    queue_command,
    record_command_result,
)
from backend.services.device_command_notifier import (
    DeviceCommandNotifier,
    device_command_notifier,
)

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
        revision_before_commit = device_command_notifier.revision(device.id)
        assert device_command_notifier.revision(device.id) == revision_before_commit
        commit_queued_command(db, device=device, command=first)
        assert device_command_notifier.revision(device.id) == revision_before_commit + 1
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
        commit_queued_command(db, device=device, command=duplicate)

        delivered = deliver_next_command(db, device=device, now=now + timedelta(seconds=1))
        assert delivered is not None
        assert delivered.status == "delivered"
        assert delivered.delivery_attempts == 1
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


def test_queue_is_rollback_safe_and_only_commit_wakes_the_agent() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
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
        revision = device_command_notifier.revision(device.id)

        queue_command(
            db,
            device=device,
            command_type="agent.refresh_inventory",
            payload={},
            idempotency_key="rolled-back",
            ttl_seconds=60,
        )
        assert device_command_notifier.revision(device.id) == revision

        db.rollback()
        assert db.scalar(select(DeviceCommand)) is None
        assert device_command_notifier.revision(device.id) == revision
    engine.dispose()


def test_command_notifier_wakes_an_async_waiter_from_a_sync_queue_thread() -> None:
    notifier = DeviceCommandNotifier()
    device_id = 17
    revision = notifier.revision(device_id)

    async def wait_for_command() -> tuple[bool, float]:
        worker = threading.Thread(
            target=lambda: (time.sleep(0.02), notifier.notify(device_id)),
            daemon=True,
        )
        worker.start()
        started_at = time.monotonic()
        woke = await notifier.wait(device_id, after=revision, timeout=1.0)
        worker.join(timeout=1)
        return woke, time.monotonic() - started_at

    woke, elapsed = asyncio.run(wait_for_command())

    assert woke is True
    assert elapsed < 0.5


def test_command_notifier_does_not_lose_a_signal_before_wait_registration() -> None:
    notifier = DeviceCommandNotifier()
    device_id = 23
    revision = notifier.revision(device_id)
    notifier.notify(device_id)

    started_at = time.monotonic()
    woke = asyncio.run(notifier.wait(device_id, after=revision, timeout=1.0))

    assert woke is True
    assert time.monotonic() - started_at < 0.1


def test_long_poll_delivers_a_newly_committed_command_without_heartbeat_delay(
    tmp_path,
) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'commands.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as setup_db:
        setup_db.add(Device(
            device_id=DEVICE_ID,
            display_name="test-pi",
            role="node",
            protocol_version="1.0",
            approved_at=now,
        ))
        setup_db.commit()

    def queue_later() -> None:
        time.sleep(0.05)
        with Session(engine) as writer:
            writer_device = writer.scalar(select(Device).where(Device.device_id == DEVICE_ID))
            assert writer_device is not None
            command = queue_command(
                writer,
                device=writer_device,
                command_type="agent.refresh_inventory",
                payload={},
                idempotency_key="long-poll",
                ttl_seconds=60,
            )
            commit_queued_command(writer, device=writer_device, command=command)

    async def receive() -> tuple[AgentCommand | Response, float]:
        with Session(engine) as reader:
            reader_device = reader.scalar(select(Device).where(Device.device_id == DEVICE_ID))
            assert reader_device is not None
            worker = threading.Thread(target=queue_later, daemon=True)
            worker.start()
            started_at = time.monotonic()
            result = await next_command(
                DEVICE_ID,
                Response(),
                wait_seconds=1.0,
                device=reader_device,
                db=reader,
            )
            worker.join(timeout=1)
            return result, time.monotonic() - started_at

    result, elapsed = asyncio.run(receive())

    assert isinstance(result, AgentCommand)
    assert result.idempotency_key == "long-poll"
    assert elapsed < 0.5
    engine.dispose()


def test_unacknowledged_command_is_redelivered_after_lease() -> None:
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
            idempotency_key="redelivery-1",
            ttl_seconds=300,
            now=now,
        )
        commit_queued_command(db, device=device, command=command)

        first = deliver_next_command(db, device=device, now=now)
        assert first is not None
        assert deliver_next_command(db, device=device, now=now + timedelta(seconds=29)) is None

        redelivered = deliver_next_command(db, device=device, now=now + timedelta(seconds=30))
        assert redelivered is not None
        assert redelivered.command_id == first.command_id
        assert redelivered.delivery_attempts == 2
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
        commit_queued_command(db, device=device, command=command)

        assert deliver_next_command(db, device=device, now=now + timedelta(seconds=6)) is None
        db.refresh(command)
        assert command.status == "expired"
    engine.dispose()
