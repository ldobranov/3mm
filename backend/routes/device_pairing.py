"""Versioned Core endpoints for the device pairing bootstrap flow."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from sqlalchemy.orm import Session

from backend.db.audit_log import AuditLog
from backend.db.user import User
from backend.services.device_pairing import (
    DeviceCredentialRevocationError,
    PairingApprovalError,
    PairingCodeUnavailableError,
    PairingCompletionError,
    approve_pairing_request,
    claim_pairing_code,
    complete_pairing_request,
    issue_pairing_code,
    issue_replacement_device_credential,
    revoke_device_credential,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db

router = APIRouter(prefix="/api/v1", tags=["device-pairing"])


class PairingCodeResponse(BaseModel):
    request_id: int
    code: str
    expires_at: datetime

    model_config = ConfigDict(extra="forbid")


class PairingClaimRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    public_key: str = Field(min_length=16, max_length=8192)
    display_name: str = Field(min_length=1, max_length=100)
    role: Literal["standalone", "hub", "node"]
    protocol_version: Literal["1.0"]

    model_config = ConfigDict(extra="forbid")


class PairingClaimResponse(BaseModel):
    request_id: int
    status: str = "pending_approval"

    model_config = ConfigDict(extra="forbid")


class PairingApprovalResponse(BaseModel):
    request_id: int
    device_id: str
    status: str = "approved"

    model_config = ConfigDict(extra="forbid")


class PairingCompletionRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")

    model_config = ConfigDict(extra="forbid")


class DeviceCredentialResponse(BaseModel):
    device_id: str
    credential_id: str
    credential_secret: str

    model_config = ConfigDict(extra="forbid")


class CredentialRevocationResponse(BaseModel):
    device_id: str
    credential_id: str
    status: str = "revoked"

    model_config = ConfigDict(extra="forbid")


@router.post(
    "/pairing-codes",
    response_model=PairingCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_pairing_code(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PairingCodeResponse:
    issued = issue_pairing_code(db, created_by_user_id=admin.id)
    db.add(
        AuditLog(
            user_id=admin.id,
            action="PAIRING_CODE_CREATED",
            entity_type="device_pairing_request",
            entity_id=issued.request_id,
            changes={"expires_at": issued.expires_at.isoformat()},
        )
    )
    db.commit()
    return PairingCodeResponse(
        request_id=issued.request_id,
        code=issued.code,
        expires_at=issued.expires_at,
    )


@router.post(
    "/pairing/claim",
    response_model=PairingClaimResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def claim_pairing(
    payload: PairingClaimRequest,
    db: Session = Depends(get_db),
) -> PairingClaimResponse:
    try:
        request = claim_pairing_code(
            db,
            code=payload.code,
            requested_device_id=payload.device_id,
            public_key=payload.public_key,
            requested_metadata={
                "display_name": payload.display_name,
                "role": payload.role,
                "protocol_version": payload.protocol_version,
            },
        )
    except PairingCodeUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pairing code is invalid or unavailable",
        ) from exc
    return PairingClaimResponse(request_id=request.id)


@router.post(
    "/pairing/requests/{request_id}/approve",
    response_model=PairingApprovalResponse,
)
def approve_pairing(
    request_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PairingApprovalResponse:
    try:
        device = approve_pairing_request(
            db,
            request_id=request_id,
            approved_by_user_id=admin.id,
        )
    except PairingApprovalError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    db.add(
        AuditLog(
            user_id=admin.id,
            action="DEVICE_PAIRING_APPROVED",
            entity_type="device",
            entity_id=device.id,
            entity_name=device.device_id,
            changes={"pairing_request_id": request_id},
        )
    )
    db.commit()
    return PairingApprovalResponse(request_id=request_id, device_id=device.device_id)


@router.post(
    "/pairing/complete",
    response_model=DeviceCredentialResponse,
)
def complete_pairing(
    payload: PairingCompletionRequest,
    db: Session = Depends(get_db),
) -> DeviceCredentialResponse:
    try:
        credential = complete_pairing_request(
            db,
            code=payload.code,
            requested_device_id=payload.device_id,
        )
    except PairingCompletionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pairing request is not ready for completion",
        ) from exc
    return DeviceCredentialResponse(
        device_id=credential.device_id,
        credential_id=credential.credential_id,
        credential_secret=credential.secret,
    )


@router.post(
    "/devices/{device_id}/credentials/{credential_id}/revoke",
    response_model=CredentialRevocationResponse,
)
def revoke_credential(
    device_id: str,
    credential_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CredentialRevocationResponse:
    try:
        credential = revoke_device_credential(
            db,
            device_id=device_id,
            credential_id=credential_id,
        )
    except DeviceCredentialRevocationError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    db.add(
        AuditLog(
            user_id=admin.id,
            action="DEVICE_CREDENTIAL_REVOKED",
            entity_type="device",
            entity_id=credential.device_id,
            entity_name=device_id,
            changes={"credential_id": credential_id},
        )
    )
    db.commit()
    return CredentialRevocationResponse(
        device_id=device_id,
        credential_id=credential_id,
    )


@router.post(
    "/devices/{device_id}/credentials/replace",
    response_model=DeviceCredentialResponse,
)
def replace_credential(
    device_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DeviceCredentialResponse:
    try:
        credential = issue_replacement_device_credential(db, device_id=device_id)
    except DeviceCredentialRevocationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.add(AuditLog(
        user_id=admin.id,
        action="DEVICE_CREDENTIAL_REPLACED",
        entity_type="device",
        entity_name=device_id,
        changes={"credential_id": credential.credential_id},
    ))
    db.commit()
    return DeviceCredentialResponse(
        device_id=device_id,
        credential_id=credential.credential_id,
        credential_secret=credential.secret,
    )
