"""Explicit OTA approval and separately persisted installation outcomes."""

from datetime import UTC, datetime, timedelta
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.config import AppSettings
from backend.db.audit_log import AuditLog
from backend.db.device import Device, DeviceCapabilityState, DeviceCommand, DeviceEvent, DeviceHeartbeat, DeviceState
from backend.db.user import User
from backend.services.device_commands import (
    NODE_MUTATION_COMMAND_TYPES, NODE_UPDATE_TERMINAL_OUTCOMES,
    DeviceCommandError, commit_queued_command, node_update_is_terminal, queue_command,
)
from backend.services.node_update_approval import public_approval_key, sign_node_update, verify_node_update
from backend.services.device_capability_registry import has_registered_capability
from backend.services.node_update_delivery import open_node_delivery
from three_mm_protocol.node_updates import (
    MAX_HANDOFF_SECONDS, NodeUpdateApplyRequest, NodeUpdateAuthorization,
    NodeUpdateOperation, NodeUpdatePreparedArtifact,
)

TERMINAL_OUTCOMES = NODE_UPDATE_TERMINAL_OUTCOMES


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def apply_command(db: Session, device: Device, operation_id: str) -> DeviceCommand | None:
    return db.scalar(select(DeviceCommand).where(
        DeviceCommand.device_id == device.id,
        DeviceCommand.idempotency_key == "node-update-apply:" + operation_id,
    ))


def installation_outcome(command: DeviceCommand | None) -> NodeUpdateOperation | None:
    value = (command.result or {}).get("operation") if command is not None else None
    return NodeUpdateOperation.model_validate(value) if value is not None else None


def _identity_matches(operation: NodeUpdateOperation, authorization: NodeUpdateAuthorization) -> bool:
    return all(getattr(operation, name) == getattr(authorization.request, name) for name in (
        "operation_id", "device_id", "release_id", "archive_sha256",
    ))


def _check_original_deadline(command: DeviceCommand, authorization: NodeUpdateAuthorization) -> None:
    if (utc(command.created_at), utc(command.expires_at)) != (
        authorization.request.created_at, authorization.request.expires_at,
    ):
        raise DeviceCommandError("Node update approval deadline differs from its original command")


def _check_device_idle(db: Session, device: Device, settings: AppSettings, now: datetime) -> None:
    freshness = timedelta(seconds=settings.backend.device_offline_after_seconds)
    heartbeat = db.scalar(select(DeviceHeartbeat).where(
        DeviceHeartbeat.device_id == device.id,
    ).order_by(DeviceHeartbeat.received_at.desc()).limit(1))
    if heartbeat is None or not -timedelta(seconds=30) <= now - utc(heartbeat.received_at) <= freshness:
        raise DeviceCommandError("Node is offline or its heartbeat is stale")
    reported = db.scalar(select(DeviceState).where(DeviceState.device_id == device.id))
    if reported is None or reported.reported_at is None or not (
        -timedelta(seconds=30) <= now - utc(reported.reported_at) <= freshness
    ):
        raise DeviceCommandError("Node update support report is missing or stale; bootstrap is required")
    support = (reported.reported_state or {}).get("node_update")
    if not isinstance(support, dict) or (
        support.get("schema_version") != 1 or support.get("signed_apply_supported") is not True
        or support.get("trusted_device_id") != device.device_id
        or support.get("approval_key_id") != public_approval_key(settings.updates).key_id
    ):
        raise DeviceCommandError("Node signed update support and pinned Hub identity must be configured first")
    if has_registered_capability(db, device, "gpio.digital.control"):
        measurement = db.scalar(select(DeviceCapabilityState).where(
            DeviceCapabilityState.device_id == device.id,
            DeviceCapabilityState.capability_id == "gpio.digital.control",
        ))

        if measurement is None:
            raise DeviceCommandError("Node output state is missing")

        if not -timedelta(seconds=30) <= now - utc(measurement.observed_at) <= freshness:
            raise DeviceCommandError("Node output state is stale")

        channels = measurement.values

        if not isinstance(channels, dict) or not channels or any(
            active is not False
            for active in channels.values()
        ):
            raise DeviceCommandError(
                "Node outputs are active or their state is unconfirmed"
            )
    for other in db.scalars(select(DeviceCommand).where(DeviceCommand.device_id == device.id)):
        if other.command_type == "agent.update.apply":
            if not node_update_is_terminal(other):
                raise DeviceCommandError("Another Node update is pending or unconfirmed")
        elif other.command_type in NODE_MUTATION_COMMAND_TYPES and (
            other.status in {"queued", "delivered"} and utc(other.expires_at) > now
        ):
            raise DeviceCommandError("Node has pending physical commands")


def approve_node_update(
    db: Session, device: Device, operation_id: str, admin: User, settings: AppSettings,
) -> DeviceCommand:
    if device.revoked_at is not None or device.role != "node":
        raise DeviceCommandError("Node is unavailable or revoked")
    # Serialize approvals for this device, including SQLite's writer lock.
    db.execute(update(Device).where(Device.id == device.id).values(updated_at=Device.updated_at))
    existing = apply_command(db, device, operation_id)
    if existing is not None:
        # Exact durable replay: never renew timestamps/signature/expired handoff.
        authorization = NodeUpdateAuthorization.model_validate(existing.payload)
        _check_original_deadline(existing, authorization)
        verify_node_update(settings.updates, authorization)
        approved = db.scalar(select(AuditLog.id).where(
            AuditLog.entity_id == existing.id, AuditLog.action == "NODE_UPDATE_APPROVED",
        ))
        if approved is None or authorization.request.device_id != device.device_id:
            raise DeviceCommandError("Node update approval identity mismatch")
        db.rollback()
        return existing
    now = datetime.now(UTC)
    prepared, _archive = open_node_delivery(
        settings.updates, operation_id=operation_id, device_id=device.device_id, now=now,
    )
    preparation = db.scalar(select(DeviceCommand).where(
        DeviceCommand.device_id == device.id,
        DeviceCommand.idempotency_key == "node-update-prepare:" + operation_id,
    ))
    if preparation is None or preparation.command_type != "agent.update.prepare" or preparation.status != "succeeded":
        raise DeviceCommandError("Node has not confirmed update preparation")
    reported = preparation.result or {}
    if not isinstance(reported, dict) or reported.get("device_id", device.device_id) != device.device_id:
        raise DeviceCommandError("Prepared Node update device identity mismatch")
    result = NodeUpdatePreparedArtifact.model_validate({**reported, "device_id": device.device_id})
    if any(getattr(result, key) != getattr(prepared, key) for key in (
        "operation_id", "device_id", "release_id", "archive_sha256", "archive_size_bytes",
    )):
        raise DeviceCommandError("Prepared Node update identity mismatch")
    _check_device_idle(db, device, settings, now)
    request = NodeUpdateApplyRequest(
        operation_id=operation_id, device_id=device.device_id,
        release_id=prepared.release_id, archive_sha256=prepared.archive_sha256,
        confirmed_install=True, created_at=now,
        expires_at=min(now + timedelta(seconds=MAX_HANDOFF_SECONDS), prepared.expires_at),
    )
    authorization = sign_node_update(settings.updates, request)
    command = queue_command(
        db, device=device, command_type="agent.update.apply",
        payload=authorization.model_dump(mode="json"),
        idempotency_key="node-update-apply:" + operation_id,
        ttl_seconds=MAX_HANDOFF_SECONDS, now=request.created_at, not_after=request.expires_at,
    )
    command.result = {"prepared": prepared.model_dump(mode="json")}
    db.add(AuditLog(
        user_id=admin.id, action="NODE_UPDATE_APPROVED", entity_type="device_node_update",
        entity_id=command.id, entity_name=device.device_id,
        changes={"operation_id": operation_id, "release_id": prepared.release_id,
                 "archive_sha256": prepared.archive_sha256, "command_id": command.command_id,
                 "key_id": authorization.key_id},
    ))
    return commit_queued_command(db, device=device, command=command)


def record_node_update_outcome(
    db: Session, device: Device, operation: NodeUpdateOperation,
) -> NodeUpdateOperation:
    command = apply_command(db, device, operation.operation_id)
    if command is None or command.command_type != "agent.update.apply":
        raise DeviceCommandError("Node update was not approved")
    if db.scalar(select(AuditLog.id).where(
        AuditLog.entity_id == command.id, AuditLog.action == "NODE_UPDATE_APPROVED",
    )) is None:
        raise DeviceCommandError("Node update has no explicit approval audit")
    # Serialize result/report writes so a late handoff cannot overwrite reports.
    db.execute(update(DeviceCommand).where(DeviceCommand.id == command.id).values(result=DeviceCommand.result))
    db.refresh(command)
    authorization = NodeUpdateAuthorization.model_validate(command.payload)
    _check_original_deadline(command, authorization)
    if not _identity_matches(operation, authorization):
        raise DeviceCommandError("Node update outcome identity mismatch")
    if utc(operation.updated_at) < authorization.request.created_at:
        raise DeviceCommandError("Node update outcome predates approval")
    if operation.updated_at > datetime.now(UTC) + timedelta(seconds=30):
        raise DeviceCommandError("Node update outcome timestamp is in the future")
    previous = installation_outcome(command)
    if previous is not None:
        if operation == previous:
            db.rollback()
            return previous
        if operation.updated_at <= previous.updated_at or previous.status in TERMINAL_OUTCOMES:
            raise DeviceCommandError("Node update outcome cannot regress or replace a terminal outcome")
        if previous.status == "unknown" and operation.status not in TERMINAL_OUTCOMES:
            raise DeviceCommandError("Unknown Node update requires a terminal resolution")
        if previous.status in {"running", "unknown"} and operation.status == "accepted":
            raise DeviceCommandError("Node update outcome cannot regress")
    command.result = {**(command.result or {}), "operation": operation.model_dump(mode="json")}
    # Device audit is separate from the administrator's explicit approval audit.
    db.add(DeviceEvent(
        device_id=device.id, event_id="evt_" + uuid.uuid4().hex,
        event_type="agent.update.operation", payload=operation.model_dump(mode="json"),
        occurred_at=operation.updated_at, received_at=datetime.now(UTC),
    ))
    db.commit()
    return operation
