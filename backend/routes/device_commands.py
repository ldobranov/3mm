"""Core command queue endpoints for administrators and paired Agents."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.device import Device, DeviceCommand
from backend.db.module import ModuleInstallation
from backend.db.user import User
from backend.services.device_commands import (
    DeviceCommandError,
    command_envelope,
    deliver_next_command,
    queue_command,
    record_command_result,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from backend.utils.device_auth import require_device
from three_mm_protocol import AgentCommand, AgentCommandResult

router = APIRouter(prefix="/api/v1/devices", tags=["device-commands"])


class QueueCommandRequest(BaseModel):
    command_type: str = Field(min_length=1, max_length=100)
    payload: dict = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=128)
    ttl_seconds: int = Field(default=300, ge=5, le=86400)
    model_config = ConfigDict(extra="forbid")


class CommandStatusResponse(BaseModel):
    command_id: str
    status: str
    created_at: datetime
    expires_at: datetime
    delivery_attempts: int
    command_type: str
    idempotency_key: str
    delivered_at: datetime | None
    completed_at: datetime | None
    result: dict | None
    error: str | None
    model_config = ConfigDict(extra="forbid")


class CommandHistoryResponse(BaseModel):
    items: list[CommandStatusResponse]
    total: int
    model_config = ConfigDict(extra="forbid")


@router.post("/{device_id}/commands", response_model=CommandStatusResponse)
def create_command(
    device_id: str,
    payload: QueueCommandRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CommandStatusResponse:
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None:
        raise HTTPException(status_code=404, detail="Device was not found")
    try:
        command = queue_command(db, device=device, **payload.model_dump())
    except DeviceCommandError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return CommandStatusResponse.model_validate(command, from_attributes=True)


@router.get("/{device_id}/commands", response_model=CommandHistoryResponse)
def list_commands(
    device_id: str,
    limit: int = 50,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CommandHistoryResponse:
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None:
        raise HTTPException(status_code=404, detail="Device was not found")
    bounded_limit = max(1, min(limit, 200))
    commands = list(
        db.scalars(
            select(DeviceCommand)
            .where(DeviceCommand.device_id == device.id)
            .order_by(DeviceCommand.created_at.desc())
            .limit(bounded_limit)
        )
    )
    return CommandHistoryResponse(
        items=[CommandStatusResponse.model_validate(item, from_attributes=True) for item in commands],
        total=len(commands),
    )


@router.get("/{device_id}/commands/next", response_model=AgentCommand)
def next_command(
    device_id: str,
    response: Response,
    device: Device = Depends(require_device),
    db: Session = Depends(get_db),
) -> AgentCommand | Response:
    if device.device_id != device_id:
        raise HTTPException(status_code=403, detail="Device identity mismatch")
    command = deliver_next_command(db, device=device)
    if command is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return response
    return command_envelope(command, device.device_id)


@router.post("/{device_id}/commands/{command_id}/result", response_model=CommandStatusResponse)
def submit_command_result(
    device_id: str,
    command_id: str,
    payload: AgentCommandResult,
    device: Device = Depends(require_device),
    db: Session = Depends(get_db),
) -> CommandStatusResponse:
    if device.device_id != device_id or payload.command_id != command_id:
        raise HTTPException(status_code=403, detail="Command identity mismatch")
    try:
        command = record_command_result(db, device=device, result=payload)
    except DeviceCommandError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if command.command_type in {"module.install", "module.disable"}:
        installation = db.scalar(select(ModuleInstallation).where(ModuleInstallation.command_id == command.command_id))
        if installation is not None:
            installation.status = command.status
            installation.error = command.error
            if command.status == "succeeded":
                if command.command_type == "module.install":
                    installation.installed_version = installation.desired_version
                    installation.enabled = True
                else:
                    installation.enabled = False
            db.commit()
    return CommandStatusResponse.model_validate(command, from_attributes=True)
