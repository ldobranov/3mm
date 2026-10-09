"""Persistence rules for expiring, idempotent device commands."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from backend.db.device import Device, DeviceCommand, DevicePlatformState, DeviceCredential
from backend.db.module import ModuleInstallation
from backend.services.device_command_notifier import device_command_notifier
from backend.services.device_authority import device_authority_write
from backend.services.device_module_authority import module_control_snapshot, record_module_transition
from backend.services.device_runtime_features import command_is_supported, lock_device, read_runtime_features
from three_mm_protocol import AgentCommand, AgentCommandResult
from three_mm_protocol.node_updates import NodeUpdateOperation
from three_mm_protocol.node_security import validate_command_payload
from backend.services.device_capability_registry import validate_invocation, can_dispatch_capability


NODE_UPDATE_TERMINAL_OUTCOMES = frozenset({"succeeded", "rolled_back", "failed"})
NODE_MUTATION_COMMAND_TYPES = frozenset({
    "gpio.write", "gpio.pulse", "capability.invoke", "application.capability.invoke",
    "agent.gpio.configure", "module.install", "module.disable",
})


class DeviceCommandError(RuntimeError):
    pass


def require_control_authority(db, device):
    state = db.get(DevicePlatformState, device.id, populate_existing=True)
    active = db.scalar(select(DeviceCredential.id).where(DeviceCredential.device_id == device.id, DeviceCredential.revoked_at.is_(None)))
    any_credential = db.scalar(select(DeviceCredential.id).where(DeviceCredential.device_id == device.id))
    if any_credential is not None and active is None:
        raise DeviceCommandError("Device credentials are revoked")
    if device.revoked_at is not None or (state is not None and (
        state.authority_status != "bound" or state.lifecycle in {"recovery", "revoked", "unowned", "enrollment_pending"})):
        raise DeviceCommandError("Device authority is revoked/released or runtime is in recovery")


def node_update_is_terminal(command: DeviceCommand) -> bool:
    """Validated completion or proven non-dispatch releases the OTA gate."""
    # A Core-side rejection before *any* dispatch cannot have begun an update.
    # Never infer this from a generic failed acknowledgement after delivery.
    if (command.status == "failed" and command.delivered_at is None
            and not command.delivery_attempts
            and (command.result or {}).get("execution_state") == "not_dispatched"):
        return True
    try:
        operation = NodeUpdateOperation.model_validate((command.result or {})["operation"])
        return operation.status in NODE_UPDATE_TERMINAL_OUTCOMES
    except (ValueError, TypeError, KeyError):
        return False


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
    not_after: datetime | None = None,
) -> DeviceCommand:
    if device.revoked_at is not None:
        raise DeviceCommandError("Device is revoked")
    try:
        validate_command_payload(command_type, payload)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 86400:
            raise ValueError("Command TTL is invalid")
    except ValueError as exc:
        raise DeviceCommandError(str(exc)) from exc
    if not_after is not None and not_after.utcoffset() is None:
        raise DeviceCommandError('Command deadline requires a timezone')
    guarded_node_mutation = device.role == "node" and command_type in NODE_MUTATION_COMMAND_TYPES
    # Serialize support changes against queueing, including non-Node devices.
    lock_device(db, device)
    db.refresh(device)
    require_control_authority(db, device)
    existing = db.scalar(
        select(DeviceCommand).where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        comparable = dict(payload)
        if (command_type in {"capability.invoke", "application.capability.invoke"}
                and "contract_digest" not in comparable and "contract_digest" in existing.payload):
            comparable["contract_digest"] = existing.payload["contract_digest"]
        if existing.command_type != command_type or existing.payload != comparable:
            raise DeviceCommandError('Command idempotency key has different content')
        return existing
    if command_type in {"capability.invoke", "application.capability.invoke"}:
        try:
            payload = validate_invocation(db, device, payload, prepare=True)
            # The canonical digest is part of the final wire payload too.
            validate_command_payload(command_type, payload)
        except ValueError as exc:
            raise DeviceCommandError(str(exc)) from exc
    if not command_is_supported(db, device, command_type):
        raise DeviceCommandError("Device runtime does not advertise support for this command")
    if guarded_node_mutation and any(
        not node_update_is_terminal(operation)
        for operation in db.scalars(select(DeviceCommand).where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.command_type == "agent.update.apply",
        ))
    ):
        raise DeviceCommandError("Node update is pending or unconfirmed; device mutations are paused")
    created_at = now or datetime.now(timezone.utc)
    expires_at = created_at + timedelta(seconds=ttl_seconds)
    if not_after is not None:
        expires_at = min(expires_at, not_after)
        if expires_at <= created_at:
            raise DeviceCommandError('Command absolute deadline has expired')
    command = DeviceCommand(
        command_id=f"cmd_{uuid.uuid4().hex}",
        device_id=device.id,
        command_type=command_type,
        payload=payload,
        idempotency_key=idempotency_key,
        status="queued",
        created_at=created_at,
        expires_at=expires_at,
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
    # Module pre-dispatch rejection can change authority. Take the common guard
    # BEFORE device/command locks, even when the poll ultimately has no work.
    with device_authority_write(db, device) as (mutation, current):
        command, recovery_required = _deliver_next_command(
            db, device=current, mutation=mutation, now=now,
            delivery_lease_seconds=delivery_lease_seconds,
        )
    if recovery_required:
        # Commit proven non-dispatch evidence before returning the existing error.
        raise DeviceCommandError("Stored command requires recovery; automatic dispatch refused")
    if command is not None:
        db.refresh(command)
    return command


def _update_module_receipt(db, device, command, mutation, *, source):
    if command.command_type not in {"module.install", "module.disable"}:
        return
    # A delayed old receipt must never overwrite the current installation episode.
    installation = db.scalar(select(ModuleInstallation).where(
        ModuleInstallation.command_id == command.command_id,
        ModuleInstallation.device_id == device.id,
    ).execution_options(populate_existing=True))
    if installation is None:
        return
    before = module_control_snapshot(installation)
    installation.status, installation.error = command.status, command.error
    if command.status == "succeeded":
        if command.command_type == "module.install":
            installation.installed_version = installation.desired_version
            installation.enabled = True
        else:
            installation.enabled = False
    record_module_transition(db, mutation, device, installation, before, source=source)


def _deliver_next_command(db, *, device, mutation, now, delivery_lease_seconds):
    mutation.require_session(db)
    delivered_at = now or datetime.now(timezone.utc)
    lock_device(db, device)
    db.refresh(device)
    require_control_authority(db, device)
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
    # Recheck withdrawals before first dispatch. Already delivered work remains
    # uncertain and follows the original lease/result/OTA recovery contract.
    support = read_runtime_features(db, device)
    if support is not None:
        commands = set(support.declaration["command_types"])
        for pending in db.scalars(select(DeviceCommand).where(
            DeviceCommand.device_id == device.id, DeviceCommand.status == "queued",
            DeviceCommand.delivered_at.is_(None), DeviceCommand.delivery_attempts == 0,
        )):
            if pending.command_type not in commands:
                pending.status = "failed"
                pending.error = "Runtime support withdrawn before dispatch"
                pending.result = {"execution_state": "not_dispatched"}
                pending.completed_at = delivered_at
                _update_module_receipt(db, device, pending, mutation, source="not_dispatched")
    db.flush()
    # New strict work is pinned at queue time. Reject withdrawal, incompatible
    # updates or same-version schema changes before its FIRST delivery only.
    # Previously delivered actions keep uncertainty/receipts; never replay them
    # as newly queued work or rewrite their evidence as not_dispatched.
    for pending in db.scalars(select(DeviceCommand).where(
        DeviceCommand.device_id == device.id, DeviceCommand.status == "queued",
        DeviceCommand.delivered_at.is_(None), DeviceCommand.delivery_attempts == 0,
        DeviceCommand.command_type.in_(("capability.invoke", "application.capability.invoke")),
    )):
        try:
            validate_invocation(db, device, pending.payload)
        except ValueError:
            pending.status = "failed"
            pending.error = "Capability contract unavailable or changed before dispatch"
            pending.result = {"execution_state": "not_dispatched"}
            pending.completed_at = delivered_at
    db.flush()
    candidates = db.scalars(
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
    )
    command = next((candidate for candidate in candidates
                    if candidate.delivered_at is not None
                    or candidate.command_type not in {"capability.invoke", "application.capability.invoke"}
                    or can_dispatch_capability(db, device, candidate.payload.get("capability_id"), now=delivered_at)), None)
    if command is None:
        return None, False
    try:
        command_envelope(command, device.device_id)
    except ValueError:
        # Historical rows are not rewritten by migration. Invalid work must
        # not gain a delivery attempt merely because stricter DTOs reject it.
        if command.delivered_at is None and not command.delivery_attempts:
            command.status = "failed"
            command.result = {**(command.result or {}), "execution_state": "not_dispatched", "recovery_code": "stored_command_invalid"}
            command.error = "Stored command cannot satisfy the Node contract"
            command.completed_at = delivered_at
            _update_module_receipt(db, device, command, mutation, source="not_dispatched")
        # Already dispatched work stays uncertain, with its original receipt
        # and delivery evidence. Never label it not_dispatched or replay it.
        return None, True
    command.status = "delivered"
    command.delivered_at = delivered_at
    command.delivery_attempts = (command.delivery_attempts or 0) + 1
    return command, False


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
    db: Session, *, device: Device, result: AgentCommandResult, credential_id=None,
) -> DeviceCommand:
    with device_authority_write(db, device, credential_id=credential_id) as (mutation, current):
        command, expired = _record_command_result(db, device=current, result=result, mutation=mutation)
    if expired:
        raise DeviceCommandError("Command has expired")
    db.refresh(command)
    return command


def _record_command_result(db, *, device, result, mutation):
    mutation.require_session(db)
    command = db.scalar(
        select(DeviceCommand).where(
            DeviceCommand.command_id == result.command_id,
            DeviceCommand.device_id == device.id,
        ).with_for_update().execution_options(populate_existing=True)
    )
    if command is None:
        raise DeviceCommandError("Command was not found")
    if command.command_type == "agent.update.apply":
        db.execute(
            update(DeviceCommand).where(DeviceCommand.id == command.id)
            .values(result=DeviceCommand.result)
        )
        db.refresh(command)
    if result.device_id != device.device_id:
        raise DeviceCommandError("Device identity mismatch")
    if command.status in {"succeeded", "failed"}:
        # Repair only the old two-commit gap from the persisted first receipt;
        # conflicting retries cannot change it or a newer installation episode.
        _update_module_receipt(db, device, command, mutation, source="agent_result")
        return command, False
    if command.status != "delivered":
        raise DeviceCommandError("Command has not been delivered")
    if _utc(command.expires_at) <= _utc(result.completed_at):
        command.status = "expired"
        return command, True
    command.status = result.status
    if command.command_type == "agent.update.apply":
        # Handoff acknowledgement is not installation completion. Independent
        # durable OTA reports may arrive before this acknowledgement.
        command.result = {**(command.result or {}), "handoff": result.output}
    else:
        command.result = result.output
    command.error = result.error
    command.completed_at = result.completed_at
    _update_module_receipt(db, device, command, mutation, source="agent_result")
    return command, False
