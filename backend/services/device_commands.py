"""Persistence rules for expiring, idempotent device commands."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from backend.db.device import Device, DeviceCommand
from backend.services.device_command_notifier import device_command_notifier
from three_mm_protocol import AgentCommand, AgentCommandResult


class DeviceCommandError(RuntimeError):
    pass


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def queue_command(
    db: Session,
    *,
    device: Device,
    command_type: str,
    payload: dict,
    idempotency_key: str,
    ttl_seconds: int,
    now: datetime | None = None,
) -> DeviceCommand:
    if device.revoked_at is not None:
        raise DeviceCommandError("Device is revoked")
    created_at = now or datetime.now(timezone.utc)
    existing = db.scalar(
        select(DeviceCommand).where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return existing
    command = DeviceCommand(
        command_id=f"cmd_{uuid.uuid4().hex}",
        device_id=device.id,
        command_type=command_type,
        payload=payload,
        idempotency_key=idempotency_key,
        status="queued",
        created_at=created_at,
        expires_at=created_at + timedelta(seconds=ttl_seconds),
    )
    db.add(command)
    db.flush()
    return command


def commit_queued_command(
    db: Session,
    *,
    device: Device,
    command: DeviceCommand,
) -> DeviceCommand:
    """Commit the complete caller transaction before waking the Agent."""

    db.commit()
    db.refresh(command)
    device_command_notifier.notify(device.id)
    return command


def deliver_next_command(
    db: Session,
    *,
    device: Device,
    now: datetime | None = None,
    delivery_lease_seconds: int = 30,
) -> DeviceCommand | None:
    delivered_at = now or datetime.now(timezone.utc)
    lease_expired_at = delivered_at - timedelta(seconds=delivery_lease_seconds)
    db.execute(
        update(DeviceCommand)
        .where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.status.in_(("queued", "delivered")),
            DeviceCommand.expires_at <= delivered_at,
        )
        .values(status="expired"),
        execution_options={"synchronize_session": False},
    )
    command = db.scalar(
        select(DeviceCommand)
        .where(
            DeviceCommand.device_id == device.id,
            or_(
                DeviceCommand.status == "queued",
                (
                    (DeviceCommand.status == "delivered")
                    & (DeviceCommand.delivered_at <= lease_expired_at)
                ),
            ),
            DeviceCommand.expires_at > delivered_at,
        )
        .order_by(DeviceCommand.created_at, DeviceCommand.id)
        .limit(1)
    )
    if command is None:
        db.commit()
        return None
    command.status = "delivered"
    command.delivered_at = delivered_at
    command.delivery_attempts = (command.delivery_attempts or 0) + 1
    db.commit()
    db.refresh(command)
    return command


def command_envelope(command: DeviceCommand, device_id: str) -> AgentCommand:
    return AgentCommand(
        command_id=command.command_id,
        device_id=device_id,
        command_type=command.command_type,
        payload=command.payload or {},
        idempotency_key=command.idempotency_key,
        created_at=_utc(command.created_at),
        expires_at=_utc(command.expires_at),
    )


def record_command_result(
    db: Session, *, device: Device, result: AgentCommandResult
) -> DeviceCommand:
    command = db.scalar(
        select(DeviceCommand).where(
            DeviceCommand.command_id == result.command_id,
            DeviceCommand.device_id == device.id,
        )
    )
    if command is None:
        raise DeviceCommandError("Command was not found")
    if result.device_id != device.device_id:
        raise DeviceCommandError("Device identity mismatch")
    if command.status in {"succeeded", "failed"}:
        return command
    if command.status != "delivered":
        raise DeviceCommandError("Command has not been delivered")
    if _utc(command.expires_at) <= _utc(result.completed_at):
        command.status = "expired"
        db.commit()
        raise DeviceCommandError("Command has expired")
    command.status = result.status
    command.result = result.output
    command.error = result.error
    command.completed_at = result.completed_at
    db.commit()
    db.refresh(command)
    return command
