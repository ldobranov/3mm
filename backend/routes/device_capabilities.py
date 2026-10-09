"""Common Core capability contracts, independent of Fleet and node runtime."""

from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.device import Device
from backend.db.user import User
from backend.services.device_capability_registry import (
    CapabilityRegistryError,
    has_registered_capability,
    provider_snapshot,
    provider_snapshots,
    read_provider,
    registered_capabilities,
    set_provider_enabled,
    configure_provider,
    capability_catalog,
)
from backend.services.device_commands import (
    DeviceCommandError,
    commit_queued_command,
    queue_command,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from backend.utils.device_auth import require_device
from backend.services.device_protocol import DeviceOperations
from backend.services.authority_metadata import AuthorityMetadataError
from backend.utils.device_protocol_http import call
from three_mm_protocol import (
    CapabilityProviderControlV1,
    CapabilityProviderReportV1,
    CapabilityProviderSnapshotV1,
    CapabilityRegistrationV2,
)
from three_mm_protocol.capability_contracts import ContractVersion
from three_mm_protocol.device_capabilities import CapabilityProviderReportV2, CapabilityProviderSnapshotV2
from three_mm_protocol.capability_availability import (
    CapabilityConfigurationV1, CapabilityAvailabilityReportV1, CapabilityDiscoveryV3,
)

router = APIRouter(prefix="/api/v1/devices", tags=["device-capabilities"])


class CapabilityRegistration(BaseModel):
    capability_id: str
    module_id: str
    version: str
    metadata: dict
    model_config = ConfigDict(extra="forbid")


class InvokeCapabilityRequest(BaseModel):
    capability_id: str = Field(min_length=1, max_length=160)
    action: str = Field(min_length=1, max_length=100)
    arguments: dict = Field(default_factory=dict)
    contract_version: ContractVersion | None = None
    model_config = ConfigDict(extra="forbid")


class CapabilityCommandResponse(BaseModel):
    command_id: str
    status: str
    model_config = ConfigDict(extra="forbid")


def _device(db: Session, device_id: str) -> Device:
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None:
        raise HTTPException(404, "Device was not found")
    return device


def _own_device(device: Device, device_id: str):
    if device.device_id != device_id:
        raise HTTPException(403, "Device identity does not match the credential")


@router.get(
    "/{device_id}/capabilities",
    response_model=list[CapabilityDiscoveryV3] | list[CapabilityRegistrationV2] | list[CapabilityRegistration],
)
def list_capabilities(
    device_id: str,
    registry_version: int = Query(default=1, ge=1, le=3),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    device = _device(db, device_id)
    if registry_version == 3:
        return capability_catalog(db, device)
    rows = registered_capabilities(db, device)
    if registry_version == 2:
        return [CapabilityRegistrationV2.model_validate(row) for row in rows]
    # Legacy serialization of the same registry, not a separate capability source.
    return [
        CapabilityRegistration(
            capability_id=row["capability_id"],
            module_id=row["provider_id"],
            version=row["provider_version"],
            metadata=row["metadata"],
        )
        for row in rows
        if row["provider_type"] == "agent_module"
    ]


@router.get(
    "/{device_id}/capability-providers",
    response_model=list[CapabilityProviderSnapshotV2 | CapabilityProviderSnapshotV1],
)
def list_providers(
    device_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    return provider_snapshots(db, _device(db, device_id))


@router.get(
    "/{device_id}/capability-providers/{provider_type}/{provider_id}",
    response_model=CapabilityProviderSnapshotV2 | CapabilityProviderSnapshotV1,
)
def get_provider(
    device_id: str,
    provider_type: str,
    provider_id: str,
    device: Device = Depends(require_device),
    db: Session = Depends(get_db),
):
    _own_device(device, device_id)
    provider = read_provider(db, device, provider_type, provider_id)
    if provider is None:
        raise HTTPException(404, "Provider was not found")
    return provider_snapshot(device, provider)


@router.put(
    "/{device_id}/capability-providers/{provider_type}/{provider_id}",
    response_model=CapabilityProviderSnapshotV2 | CapabilityProviderSnapshotV1,
)
def report_provider(
    device_id: str,
    provider_type: str,
    provider_id: str,
    payload: CapabilityProviderReportV2 | CapabilityProviderReportV1,
    authorization: str | None = Header(default=None),
    device: Device = Depends(require_device),
    db: Session = Depends(get_db),
):
    _own_device(device, device_id)
    _own_device(device, payload.device_id)
    if (provider_type, provider_id) != (payload.provider_type, payload.provider_id):
        raise HTTPException(409, "Provider identity does not match the report")
    # require_device validated this exact header and its secret before entry.
    credential_id = (authorization or "").removeprefix("Device ").strip().partition(":")[0]
    return call(DeviceOperations(db, device, credential_id=credential_id).provider, payload)


@router.post(
    "/{device_id}/capability-providers/{provider_type}/{provider_id}/enabled",
    response_model=CapabilityProviderSnapshotV2 | CapabilityProviderSnapshotV1,
)
def control_provider(
    device_id: str,
    provider_type: str,
    provider_id: str,
    payload: CapabilityProviderControlV1,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    device = _device(db, device_id)
    try:
        provider = set_provider_enabled(
            db,
            device,
            provider_type,
            provider_id,
            expected_revision=payload.expected_revision,
            enabled=payload.enabled,
            actor_user_id=admin.id,
        )
        snapshot = provider_snapshot(device, provider)
        return snapshot
    except (CapabilityRegistryError, AuthorityMetadataError) as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc


@router.post("/{device_id}/capability-providers/{provider_type}/{provider_id}/configuration",
             response_model=CapabilityProviderSnapshotV2)
def configure_capabilities(device_id: str, provider_type: str, provider_id: str,
        payload: CapabilityConfigurationV1, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    device = _device(db, device_id)
    try:
        provider = configure_provider(db, device, provider_type, provider_id, payload, actor_user_id=admin.id)
        snapshot = provider_snapshot(device, provider)
        return snapshot
    except (CapabilityRegistryError, AuthorityMetadataError) as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc


@router.post("/{device_id}/capability-availability", response_model=dict[str, str])
def publish_availability(device_id: str, payload: CapabilityAvailabilityReportV1,
        device: Device = Depends(require_device), db: Session = Depends(get_db)):
    _own_device(device, device_id)
    call(DeviceOperations(db, device).availability, payload)
    return {"status": "accepted"}


@router.post("/{device_id}/capabilities/invoke", response_model=CapabilityCommandResponse)
def invoke_capability(
    device_id: str,
    payload: InvokeCapabilityRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    device = _device(db, device_id)
    if not has_registered_capability(db, device, payload.capability_id):
        raise HTTPException(409, "Capability is not enabled on this device")
    try:
        command = queue_command(
            db,
            device=device,
            command_type="capability.invoke",
            payload=payload.model_dump(exclude_none=True),
            idempotency_key=f"capability:{payload.capability_id}:{uuid4().hex}",
            ttl_seconds=300,
        )
        commit_queued_command(db, device=device, command=command)
        return CapabilityCommandResponse(
            command_id=command.command_id, status=command.status
        )
    except DeviceCommandError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
