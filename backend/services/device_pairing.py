"""Persistence-backed creation and claiming of one-time pairing codes."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.device import DevicePairingRequest

DEFAULT_PAIRING_TTL = timedelta(minutes=10)
PAIRING_TOKEN_BYTES = 18


class PairingCodeUnavailableError(RuntimeError):
    """The supplied code is invalid, expired or has already been claimed."""


@dataclass(frozen=True)
class IssuedPairingCode:
    request_id: int
    code: str
    expires_at: datetime


def pairing_code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


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
