"""Optional signed management/lifecycle adapter. Legacy device routes stay intact."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.db.device import Device
from backend.db.user import User
from backend.services.device_platform import (
    identity_proof,
    management_payload,
    sign_authority,
    platform_snapshot,
    report_lifecycle,
    release_authority,
    prepare_reenrollment,
)
from backend.services.installation_identity import InstallationIdentityError
from backend.services.device_command_notifier import device_command_notifier
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from backend.utils.device_auth import require_device
from backend.utils.device_protocol_http import call
from three_mm_protocol.device_platform import (
    AuthorityChallengeV1,
    AuthorityProofV1,
    Contract,
    DEVICE,
    LifecycleReportV1,
    DevicePlatformSnapshotV1,
)

router = APIRouter(prefix="/api/v1", tags=["device-platform"])


def _signed_call(function, *args, **kwargs):
    try:
        return call(function, *args, **kwargs)
    except (InstallationIdentityError, ValueError) as exc:
        raise HTTPException(
            503, "Installation authority is unavailable or challenge invalid"
        ) from exc


@router.post("/pairing/authority-proof", response_model=AuthorityProofV1)
def prove_identity(payload: AuthorityChallengeV1, db: Session = Depends(get_db)):
    return _signed_call(identity_proof, db, payload)


@router.post("/devices/{device_id}/authority-exchange", response_model=AuthorityProofV1)
async def exchange(
    device_id: str,
    payload: AuthorityChallengeV1,
    wait_seconds: float = Query(default=0, ge=0, le=20),
    device: Device = Depends(require_device),
    db: Session = Depends(get_db),
):
    if device_id != device.device_id or payload.device_id != device_id:
        raise HTTPException(403, "Device identity mismatch")
    revision = device_command_notifier.revision(device.id)
    result = _signed_call(management_payload, db, device, payload)
    if payload.operation == "command" and result["command"] is None and wait_seconds:
        await device_command_notifier.wait(
            device.id, after=revision, timeout=wait_seconds
        )
        db.rollback()
        # Recheck revocation after the wait; old principals never bypass release.
        db.refresh(device)
        result = _signed_call(management_payload, db, device, payload)
    proof = _signed_call(sign_authority, db, payload, result)
    db.commit()
    return proof


@router.put("/devices/{device_id}/lifecycle", response_model=DevicePlatformSnapshotV1)
def lifecycle(
    device_id: str,
    payload: LifecycleReportV1,
    authorization: str | None = Header(default=None),
    device: Device = Depends(require_device),
    db: Session = Depends(get_db),
):
    if device_id != device.device_id:
        raise HTTPException(403, "Device identity mismatch")
    # require_device has validated this exact header, including the secret.
    credential_id = (authorization or "").removeprefix("Device ").strip().partition(":")[0]
    return _signed_call(report_lifecycle, db, device, payload, credential_id=credential_id)


def _device(db, device_id):
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None:
        raise HTTPException(404, "Device not found")
    return device


@router.get("/devices/{device_id}/platform", response_model=DevicePlatformSnapshotV1)
def platform(
    device_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    result = _signed_call(platform_snapshot, db, _device(db, device_id))
    db.commit()
    return result


class ReleaseRequest(Contract):
    confirmed_device_id: str = Field(pattern=DEVICE)
    expected_revision: int = Field(ge=0, le=2147483646, strict=True)


@router.post(
    "/devices/{device_id}/authority/release", response_model=DevicePlatformSnapshotV1
)
def release(
    device_id: str,
    payload: ReleaseRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _signed_call(
        release_authority,
        db,
        _device(db, device_id),
        actor_id=admin.id,
        **payload.model_dump(),
    )


@router.post(
    "/devices/{device_id}/authority/prepare-enrollment",
    response_model=DevicePlatformSnapshotV1,
)
def prepare(
    device_id: str,
    payload: ReleaseRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _signed_call(
        prepare_reenrollment,
        db,
        _device(db, device_id),
        actor_id=admin.id,
        **payload.model_dump(),
    )
