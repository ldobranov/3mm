"""Persistence-backed creation and claiming of one-time pairing codes."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.device import Device, DeviceCredential, DevicePairingRequest

DEFAULT_PAIRING_TTL = timedelta(minutes=10)
PAIRING_TOKEN_BYTES = 18
CREDENTIAL_SECRET_BYTES = 32


class PairingCodeUnavailableError(RuntimeError):
    """The supplied code is invalid, expired or has already been claimed."""


class PairingApprovalError(RuntimeError):
    """The pending pairing request cannot be approved."""


class PairingCompletionError(RuntimeError):
    """The approved pairing request cannot issue a credential."""


@dataclass(frozen=True)
class IssuedPairingCode:
    request_id: int
    code: str
    expires_at: datetime


@dataclass(frozen=True)
class IssuedDeviceCredential:
    device_id: str
    credential_id: str
    secret: str


def pairing_code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def credential_secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def issue_pairing_code(
    db: Session,
    *,
    created_by_user_id: int,
    now: datetime | None = None,
    ttl: timedelta = DEFAULT_PAIRING_TTL,
) -> IssuedPairingCode:
    issued_at = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        raise ValueError("Pairing timestamps must include a timezone")
    if ttl <= timedelta(0):
        raise ValueError("Pairing code TTL must be positive")

    code = secrets.token_urlsafe(PAIRING_TOKEN_BYTES)
    expires_at = issued_at + ttl
    request = DevicePairingRequest(
        code_hash=pairing_code_hash(code),
        created_by_user_id=created_by_user_id,
        created_at=issued_at,
        expires_at=expires_at,
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return IssuedPairingCode(
        request_id=request.id,
        code=code,
        expires_at=expires_at,
    )


def claim_pairing_code(
    db: Session,
    *,
    code: str,
    requested_device_id: str,
    public_key: str,
    requested_metadata: dict[str, str],
    now: datetime | None = None,
) -> DevicePairingRequest:
    claimed_at = now or datetime.now(timezone.utc)
    if claimed_at.tzinfo is None:
        raise ValueError("Pairing timestamps must include a timezone")
    if not requested_device_id.strip() or not public_key.strip():
        raise ValueError("Device ID and public key are required")

    statement = (
        update(DevicePairingRequest)
        .where(
            DevicePairingRequest.code_hash == pairing_code_hash(code),
            DevicePairingRequest.claimed_at.is_(None),
            DevicePairingRequest.approved_at.is_(None),
            DevicePairingRequest.expires_at > claimed_at,
        )
        .values(
            requested_device_id=requested_device_id.strip(),
            public_key=public_key.strip(),
            requested_metadata=requested_metadata,
            claimed_at=claimed_at,
        )
    )
    result = db.execute(statement)
    if result.rowcount != 1:
        db.rollback()
        raise PairingCodeUnavailableError("Pairing code is invalid or unavailable")
    db.commit()

    request = db.scalar(
        select(DevicePairingRequest).where(
            DevicePairingRequest.code_hash == pairing_code_hash(code)
        )
    )
    if request is None:  # Defensive: the successful update must still be readable.
        raise PairingCodeUnavailableError("Pairing code is invalid or unavailable")
    return request


def approve_pairing_request(
    db: Session,
    *,
    request_id: int,
    approved_by_user_id: int,
    now: datetime | None = None,
) -> Device:
    approved_at = now or datetime.now(timezone.utc)
    if approved_at.tzinfo is None:
        raise ValueError("Pairing timestamps must include a timezone")

    request = db.get(DevicePairingRequest, request_id)
    if (
        request is None
        or request.claimed_at is None
        or request.approved_at is not None
        or request.device_id is not None
        or not request.requested_device_id
    ):
        raise PairingApprovalError("Pairing request is not pending approval")
    existing = db.scalar(
        select(Device).where(Device.device_id == request.requested_device_id)
    )
    if existing is not None:
        raise PairingApprovalError("Device identity is already registered")

    metadata = request.requested_metadata or {}
    required_metadata = {"display_name", "role", "protocol_version"}
    if not required_metadata.issubset(metadata):
        raise PairingApprovalError("Pairing request metadata is incomplete")

    device = Device(
        device_id=request.requested_device_id,
        display_name=metadata["display_name"],
        role=metadata["role"],
        protocol_version=metadata["protocol_version"],
        approved_at=approved_at,
    )
    request.device = device
    request.approved_by_user_id = approved_by_user_id
    request.approved_at = approved_at
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def complete_pairing_request(
    db: Session,
    *,
    code: str,
    requested_device_id: str,
    now: datetime | None = None,
) -> IssuedDeviceCredential:
    completed_at = now or datetime.now(timezone.utc)
    if completed_at.tzinfo is None:
        raise ValueError("Pairing timestamps must include a timezone")

    statement = (
        update(DevicePairingRequest)
        .where(
            DevicePairingRequest.code_hash == pairing_code_hash(code),
            DevicePairingRequest.requested_device_id == requested_device_id,
            DevicePairingRequest.claimed_at.is_not(None),
            DevicePairingRequest.approved_at.is_not(None),
            DevicePairingRequest.device_id.is_not(None),
            DevicePairingRequest.completed_at.is_(None),
        )
        .values(completed_at=completed_at)
    )
    result = db.execute(statement)
    if result.rowcount != 1:
        db.rollback()
        raise PairingCompletionError("Pairing request is not ready for completion")

    request = db.scalar(
        select(DevicePairingRequest).where(
            DevicePairingRequest.code_hash == pairing_code_hash(code)
        )
    )
    if request is None or request.device_id is None:
        db.rollback()
        raise PairingCompletionError("Pairing request is not ready for completion")

    credential_id = f"cred_{secrets.token_hex(16)}"
    secret = secrets.token_urlsafe(CREDENTIAL_SECRET_BYTES)
    credential = DeviceCredential(
        device_id=request.device_id,
        credential_id=credential_id,
        secret_hash=credential_secret_hash(secret),
        created_at=completed_at,
    )
    db.add(credential)
    db.commit()
    return IssuedDeviceCredential(
        device_id=requested_device_id,
        credential_id=credential_id,
        secret=secret,
    )
