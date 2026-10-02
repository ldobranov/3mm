"""Administrator orchestration for one-device Node update preparation."""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    model_validator,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.audit_log import AuditLog
from backend.db.device import Device, DeviceCommand
from backend.db.user import User
from backend.services.device_commands import (
    DeviceCommandError,
    commit_queued_command,
    queue_command,
)
from backend.services.node_release_catalog import (
    NodeReleaseCatalogError,
    NodeUpdateChannel,
    download_published_node_archive,
    find_published_node_release,
)
from backend.services.node_update_delivery import (
    NodeDeliveryError,
    PreparedNodeDelivery,
    discard_node_delivery,
    read_node_delivery,
    stage_node_delivery,
)
from backend.services.node_update_approval import NodeApprovalError, public_approval_key
from backend.services.node_update_execution import (
    apply_command, approve_node_update, installation_outcome, record_node_update_outcome,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from backend.utils.device_auth import require_device
from three_mm_protocol.node_updates import (
    NodeUpdatePrepareRequest,
    NodeUpdateApprovalKey,
    NodeUpdateOperation,
)


router = APIRouter(
    prefix="/api/v1/devices",
    tags=["node-updates"],
)


class NodePrepareAdminRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    channel: NodeUpdateChannel = "beta"


class NodePrepareAdminResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    prepared: PreparedNodeDelivery

    version: str
    channel: NodeUpdateChannel

    command_id: str
    command_status: str


class NodeUpdateCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_release_id: str | None
    latest_release_id: str
    latest_version: str
    channel: NodeUpdateChannel
    update_available: bool | None


class NodePrepareStatusResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    operation_id: str
    device_id: str
    release_id: str

    archive_sha256: str
    archive_size_bytes: int

    state: Literal[
        "queued",
        "preparing",
        "prepared",
        "failed",
        "expired",
    ]

    command_id: str
    command_status: str

    hub_prepared_at: datetime
    hub_expires_at: datetime

    agent_prepared_at: datetime | None = None
    error: str | None = None
    apply_command_id: str | None = None
    apply_command_status: str | None = None
    installation: NodeUpdateOperation | None = None


class NodeApplyAdminRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed_install: StrictBool

    @model_validator(mode="after")
    def explicit_confirmation(self):
        if self.confirmed_install is not True:
            raise ValueError("Explicit installation confirmation is required")
        return self


class NodeApplyAdminResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str
    command_id: str
    command_status: str
    expires_at: datetime
    installation: NodeUpdateOperation | None = None


def _aware_utc(
    value: datetime,
) -> datetime:
    if value.tzinfo is None:
        return value.replace(
            tzinfo=UTC
        )

    return value.astimezone(
        UTC
    )
    

def _current_node_release_id(
    db: Session,
    device: Device,
) -> str | None:
    command = db.scalar(
        select(DeviceCommand)
        .where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.command_type == "agent.update.apply",
        )
        .order_by(DeviceCommand.created_at.desc(), DeviceCommand.id.desc())
        .limit(1)
    )

    # A newer unconfirmed attempt must not expose an older success as current.
    try:
        operation = installation_outcome(command)
    except (AttributeError, TypeError, ValueError):
        return None

    if operation is None or operation.device_id != device.device_id:
        return None

    if operation.status == "succeeded":
        return operation.release_id

    if operation.status == "rolled_back":
        return operation.previous_release_id

    return None


@router.get(
    "/{device_id}/node-updates/check",
    response_model=NodeUpdateCheckResponse,
)
def check_node_update(
    device_id: str,
    channel: NodeUpdateChannel = "beta",
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> NodeUpdateCheckResponse:
    device = db.scalar(
        select(Device).where(
            Device.device_id == device_id
        )
    )

    if device is None:
        raise HTTPException(
            status_code=404,
            detail="Device was not found",
        )

    if device.role != "node":
        raise HTTPException(
            status_code=409,
            detail="Node updates require a Node device",
        )

    if device.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Device is revoked")

    try:
        release = find_published_node_release(
            get_settings().updates,
            channel=channel,
        )
    except NodeReleaseCatalogError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    current_release_id = _current_node_release_id(
        db,
        device,
    )

    return NodeUpdateCheckResponse(
        current_release_id=current_release_id,
        latest_release_id=release.manifest.release_id,
        latest_version=release.manifest.version,
        channel=release.manifest.channel,
        update_available=(
            None
            if current_release_id is None
            else current_release_id
            != release.manifest.release_id
        ),
    )


@router.post(
    "/{device_id}/node-updates/prepare",
    response_model=NodePrepareAdminResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def prepare_node_update(
    device_id: str,
    payload: NodePrepareAdminRequest | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> NodePrepareAdminResponse:
    settings = get_settings().updates

    device = db.scalar(
        select(Device).where(
            Device.device_id == device_id
        )
    )

    if device is None:
        raise HTTPException(
            status_code=404,
            detail="Device was not found",
        )

    if device.revoked_at is not None:
        raise HTTPException(
            status_code=409,
            detail="Device is revoked",
        )

    if device.role != "node":
        raise HTTPException(
            status_code=409,
            detail="Node updates require a Node device",
        )

    request_payload = (
        payload
        or NodePrepareAdminRequest()
    )

    operation_id = (
        "nodeupd_"
        + uuid.uuid4().hex
    )

    candidate_directory = (
        Path(settings.staging_dir)
        / "node-candidates"
        / operation_id
    )

    candidate_directory.mkdir(
        parents=True,
        exist_ok=False,
    )

    delivery_created = False

    try:
        release = (
            find_published_node_release(
                settings,
                channel=(
                    request_payload.channel
                ),
            )
        )

        current_release_id = _current_node_release_id(
            db,
            device,
        )

        if (
            current_release_id is not None
            and current_release_id
            == release.manifest.release_id
        ):
            raise DeviceCommandError(
                "Node is already running the selected release"
            )

        candidate_archive = (
            candidate_directory
            / release.artifact.filename
        )

        download_published_node_archive(
            release,
            candidate_archive,
            settings,
        )

        prepared = stage_node_delivery(
            settings,
            operation_id=operation_id,
            device_id=device.device_id,
            release_id=(
                release.manifest.release_id
            ),
            archive_sha256=(
                release.artifact.sha256
            ),
            archive_size_bytes=(
                release.artifact.size_bytes
            ),
            source_path=candidate_archive,
        )

        delivery_created = True

        agent_request = (
            NodeUpdatePrepareRequest(
                operation_id=operation_id,
                device_id=device.device_id,
                release_id=(
                    release.manifest.release_id
                ),
                archive_sha256=(
                    release.artifact.sha256
                ),
                archive_size_bytes=(
                    release.artifact.size_bytes
                ),
            )
        )

        command = queue_command(
            db,
            device=device,
            command_type=(
                "agent.update.prepare"
            ),
            payload=agent_request.model_dump(
                mode="json"
            ),
            idempotency_key=(
                "node-update-prepare:"
                + operation_id
            ),
            ttl_seconds=900,
        )

        db.add(
            AuditLog(
                user_id=admin.id,
                action=(
                    "NODE_UPDATE_PREPARED"
                ),
                entity_type=(
                    "device_node_update"
                ),
                entity_name=device.device_id,
                changes={
                    "operation_id":
                        operation_id,
                    "release_id":
                        release.manifest.release_id,
                    "version":
                        release.manifest.version,
                    "channel":
                        release.manifest.channel,
                    "archive_sha256":
                        release.artifact.sha256,
                    "archive_size_bytes":
                        release.artifact.size_bytes,
                    "command_id":
                        command.command_id,
                },
            )
        )

        command = commit_queued_command(
            db,
            device=device,
            command=command,
        )

        return NodePrepareAdminResponse(
            prepared=prepared,
            version=release.manifest.version,
            channel=release.manifest.channel,
            command_id=command.command_id,
            command_status=command.status,
        )

    except (
        NodeReleaseCatalogError,
        NodeDeliveryError,
        DeviceCommandError,
    ) as exc:
        db.rollback()

        if delivery_created:
            try:
                discard_node_delivery(
                    settings,
                    operation_id,
                )
            except NodeDeliveryError:
                pass

        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    finally:
        shutil.rmtree(
            candidate_directory,
            ignore_errors=True,
        )
        
@router.get(
    "/{device_id}/node-updates/{operation_id}",
    response_model=NodePrepareStatusResponse,
)
def node_update_status(
    device_id: str,
    operation_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> NodePrepareStatusResponse:
    settings = get_settings().updates

    device = db.scalar(
        select(Device).where(
            Device.device_id
            == device_id
        )
    )

    if device is None:
        raise HTTPException(
            status_code=404,
            detail="Device was not found",
        )

    approved = apply_command(db, device, operation_id)
    try:
        prepared = read_node_delivery(
            settings,
            operation_id,
        )
    except NodeDeliveryError as exc:
        # Installation history survives removal of the downloaded delivery.
        try:
            prepared = PreparedNodeDelivery.model_validate((approved.result or {})["prepared"])
        except (AttributeError, KeyError, ValueError, TypeError):
            raise HTTPException(status_code=404, detail="Node update operation was not found") from exc

    if (
        prepared.device_id
        != device.device_id
    ):
        # Do not disclose an operation
        # prepared for another device.
        raise HTTPException(
            status_code=404,
            detail=(
                "Node update operation "
                "was not found"
            ),
        )

    command = db.scalar(
        select(DeviceCommand).where(
            DeviceCommand.device_id
            == device.id,
            DeviceCommand.idempotency_key
            == (
                "node-update-prepare:"
                + operation_id
            ),
        )
    )

    if command is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Node update operation "
                "has no command record"
            ),
        )

    now = datetime.now(UTC)

    agent_prepared_at = None
    error = command.error

    if command.status == "succeeded":
        result = command.result

        if not isinstance(
            result,
            dict,
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Node update result "
                    "is invalid"
                ),
            )

        expected = {
            "operation_id":
                prepared.operation_id,
            "release_id":
                prepared.release_id,
            "archive_sha256":
                prepared.archive_sha256,
            "archive_size_bytes":
                prepared.archive_size_bytes,
        }

        for key, value in expected.items():
            if (
                result.get(key)
                != value
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Node update result "
                        "identity mismatch"
                    ),
                )

        prepared_at = result.get(
            "prepared_at"
        )

        if not isinstance(
            prepared_at,
            str,
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Node update result "
                    "timestamp is invalid"
                ),
            )

        try:
            agent_prepared_at = (
                datetime.fromisoformat(
                    prepared_at.replace(
                        "Z",
                        "+00:00",
                    )
                )
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Node update result "
                    "timestamp is invalid"
                ),
            ) from exc

        if (
            agent_prepared_at.tzinfo
            is None
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Node update result "
                    "timestamp requires timezone"
                ),
            )

        state = "prepared"

    elif command.status == "failed":
        state = "failed"

    elif command.status == "expired":
        state = "expired"

    elif (
        _aware_utc(
            command.expires_at
        )
        <= now
        or prepared.expires_at
        <= now
    ):
        state = "expired"

    elif command.status == "delivered":
        state = "preparing"

    elif command.status == "queued":
        state = "queued"

    else:
        raise HTTPException(
            status_code=409,
            detail=(
                "Node update command "
                "state is invalid"
            ),
        )

    return NodePrepareStatusResponse(
        operation_id=(
            prepared.operation_id
        ),
        device_id=(
            prepared.device_id
        ),
        release_id=(
            prepared.release_id
        ),
        archive_sha256=(
            prepared.archive_sha256
        ),
        archive_size_bytes=(
            prepared.archive_size_bytes
        ),
        state=state,
        command_id=command.command_id,
        command_status=command.status,
        hub_prepared_at=(
            prepared.prepared_at
        ),
        hub_expires_at=(
            prepared.expires_at
        ),
        agent_prepared_at=(
            agent_prepared_at
        ),
        error=error,
        apply_command_id=approved.command_id if approved is not None else None,
        apply_command_status=approved.status if approved is not None else None,
        installation=installation_outcome(approved),
    )


@router.get("/node-updates/approval-key", response_model=NodeUpdateApprovalKey)
def node_update_approval_key() -> NodeUpdateApprovalKey:
    """Public identity for explicit root/fingerprint pinning, never a private key."""
    try:
        return public_approval_key(get_settings().updates)
    except NodeApprovalError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/{device_id}/node-updates/{operation_id}/apply",
             response_model=NodeApplyAdminResponse, status_code=202)
def apply_node_update(
    device_id: str, operation_id: str, payload: NodeApplyAdminRequest,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
) -> NodeApplyAdminResponse:
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None:
        raise HTTPException(404, "Device was not found")
    try:
        command = approve_node_update(db, device, operation_id, admin, get_settings())
        return NodeApplyAdminResponse(
            operation_id=operation_id, command_id=command.command_id,
            command_status=command.status, expires_at=_aware_utc(command.expires_at),
            installation=installation_outcome(command),
        )
    except (DeviceCommandError, NodeDeliveryError, NodeApprovalError, ValueError) as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc


@router.post("/{device_id}/node-updates/{operation_id}/report", response_model=NodeUpdateOperation)
def report_node_update(
    device_id: str, operation_id: str, payload: NodeUpdateOperation,
    device: Device = Depends(require_device), db: Session = Depends(get_db),
) -> NodeUpdateOperation:
    if device.device_id != device_id or payload.device_id != device_id or payload.operation_id != operation_id:
        raise HTTPException(403, "Node update identity mismatch")
    try:
        return record_node_update_outcome(db, device, payload)
    except (DeviceCommandError, ValueError) as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
