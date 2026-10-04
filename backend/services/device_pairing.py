"""Persistence-backed creation and claiming of one-time pairing codes."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.device import Device, DeviceCredential, DevicePairingRequest, DevicePlatformState, DeviceEvent

DEFAULT_PAIRING_TTL = timedelta(minutes=10)
PAIRING_TOKEN_BYTES = 18
CREDENTIAL_SECRET_BYTES = 32


class PairingCodeUnavailableError(RuntimeError):
    """The supplied code is invalid, expired or has already been claimed."""


class PairingApprovalError(RuntimeError):
    """The pending pairing request cannot be approved."""


class PairingCompletionError(RuntimeError):
    """The approved pairing request cannot issue a credential."""


class DeviceCredentialRevocationError(RuntimeError):
    """The selected active device credential cannot be revoked."""


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

    # Serialize approval against another approval or rejection, including sessions
    # whose identity map still contains an older version of the request.
    reserved = db.execute(
        update(DevicePairingRequest)
        .where(
            DevicePairingRequest.id == request_id,
            *_pending_request_conditions(approved_at),
        )
        .values(approved_at=approved_at, approved_by_user_id=approved_by_user_id)
        .execution_options(synchronize_session=False)
    )
    if reserved.rowcount != 1:
        db.rollback()
        raise PairingApprovalError("Pairing request is not pending approval")
    db.expire_all()
    request = db.get(DevicePairingRequest, request_id)
    if (
        request is None
        or request.claimed_at is None
        or request.device_id is not None
        or not request.requested_device_id
    ):
        db.rollback()
        raise PairingApprovalError("Pairing request is not pending approval")
    existing = db.scalar(
        select(Device).where(Device.device_id == request.requested_device_id)
    )
    platform = db.get(DevicePlatformState, existing.id) if existing else None
    if existing is not None and (request.created_by_user_id is not None or platform is None or
        (platform.authority_status, platform.lifecycle, platform.reason) != (
            "released", "enrollment_pending", "authority.enrollment_authorized")):
        db.rollback()
        raise PairingApprovalError("Device identity is already registered")

    metadata = request.requested_metadata or {}
    required_metadata = {"display_name", "role", "protocol_version"}
    if not required_metadata.issubset(metadata):
        db.rollback()
        raise PairingApprovalError("Pairing request metadata is incomplete")

    device = existing or Device(
        device_id=request.requested_device_id,
        display_name=metadata["display_name"],
        role=metadata["role"],
        protocol_version=metadata["protocol_version"],
        approved_at=approved_at,
    )
    if existing is not None:
        device.revoked_at = None
        platform.authority_status, platform.lifecycle, platform.reason = "bound", "active", None
        platform.revision += 1
        platform.updated_at = approved_at
        db.add(DeviceEvent(device_id=device.id, event_id="evt_" + secrets.token_hex(16),
            event_type="device.authority.bound", payload={"revision": platform.revision, "actor_id": approved_by_user_id},
            occurred_at=approved_at))
    request.device = device
    request.approved_by_user_id = approved_by_user_id
    request.approved_at = approved_at
    db.add(device)
    if request.created_by_user_id is None:
        # Node already persisted the secret; Core receives only its verifier.
        if metadata.get("enrollment_version") != 1:
            db.rollback()
            raise PairingApprovalError("Unsupported enrollment request")
        db.add(DeviceCredential(
            device=device, credential_id=metadata["credential_id"],
            secret_hash=metadata["credential_secret_hash"], created_at=approved_at,
        ))
        request.completed_at = approved_at
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise PairingApprovalError("Device identity is already registered") from exc
    db.refresh(device)
    return device


def _pending_request_conditions(now: datetime) -> tuple:
    return (
        DevicePairingRequest.claimed_at.is_not(None),
        DevicePairingRequest.requested_device_id.is_not(None),
        DevicePairingRequest.approved_at.is_(None),
        DevicePairingRequest.completed_at.is_(None),
        DevicePairingRequest.device_id.is_(None),
        DevicePairingRequest.expires_at > now,
    )


def list_pending_pairing_requests(
    db: Session, *, after_id: int = 0, limit: int = 50,
    now: datetime | None = None,
) -> list[DevicePairingRequest]:
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        raise ValueError("Pairing timestamps must include a timezone")
    if after_id < 0 or not 1 <= limit <= 100:
        raise ValueError("Invalid pairing page")
    return list(db.scalars(
        select(DevicePairingRequest)
        .where(DevicePairingRequest.id > after_id, *_pending_request_conditions(checked_at))
        .order_by(DevicePairingRequest.id).limit(limit)
    ))


def reject_pairing_request(
    db: Session, *, request_id: int, now: datetime | None = None,
) -> None:
    """Expire a pending request without creating or changing a managed device.

    The caller commits the rejection together with its administrator audit row.
    Rejection provenance lives in that audit; no new persistent status is invented.
    """
    rejected_at = now or datetime.now(timezone.utc)
    if rejected_at.tzinfo is None:
        raise ValueError("Pairing timestamps must include a timezone")
    result = db.execute(
        update(DevicePairingRequest)
        .where(DevicePairingRequest.id == request_id, *_pending_request_conditions(rejected_at))
        .values(expires_at=rejected_at)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise PairingApprovalError("Pairing request is not pending approval")
    db.expire_all()
    request = db.get(DevicePairingRequest, request_id)
    if request.created_by_user_id is None:
        request.requested_metadata = {**request.requested_metadata, "rejected": True}


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
            DevicePairingRequest.created_by_user_id.is_not(None),
            DevicePairingRequest.expires_at > completed_at,
            DevicePairingRequest.device_id.in_(
                select(Device.id).where(Device.revoked_at.is_(None))
            ),
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


def revoke_device_credential(
    db: Session,
    *,
    device_id: str,
    credential_id: str,
    now: datetime | None = None,
) -> DeviceCredential:
    revoked_at = now or datetime.now(timezone.utc)
    if revoked_at.tzinfo is None:
        raise ValueError("Credential timestamps must include a timezone")

    credential = db.scalar(
        select(DeviceCredential)
        .join(Device)
        .where(
            Device.device_id == device_id,
            DeviceCredential.credential_id == credential_id,
            DeviceCredential.revoked_at.is_(None),
        )
    )
    if credential is None:
        raise DeviceCredentialRevocationError("Active device credential was not found")
    credential.revoked_at = revoked_at
    db.commit()
    db.refresh(credential)
    return credential


def issue_replacement_device_credential(
    db: Session, *, device_id: str, now: datetime | None = None
) -> IssuedDeviceCredential:
    issued_at = now or datetime.now(timezone.utc)
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None or device.revoked_at is not None:
        raise DeviceCredentialRevocationError("Active device was not found")
    credential_id = f"cred_{secrets.token_hex(16)}"
    secret = secrets.token_urlsafe(CREDENTIAL_SECRET_BYTES)
    db.add(DeviceCredential(
        device_id=device.id,
        credential_id=credential_id,
        secret_hash=credential_secret_hash(secret),
        created_at=issued_at,
    ))
    db.commit()
    return IssuedDeviceCredential(device_id=device_id, credential_id=credential_id, secret=secret)
