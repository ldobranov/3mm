"""Authentication dependency for unique revocable device credentials."""

import hmac
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.device import Device, DeviceCredential
from backend.services.device_pairing import credential_secret_hash
from backend.utils.db_utils import get_db


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid device credential",
        headers={"WWW-Authenticate": "Device"},
    )


def require_device(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> Device:
    if not authorization or not authorization.startswith("Device "):
        raise _unauthorized()
    presented = authorization.removeprefix("Device ").strip()
    credential_id, separator, secret = presented.partition(":")
    if not separator or not credential_id or not secret:
        raise _unauthorized()

    credential = db.scalar(
        select(DeviceCredential).where(DeviceCredential.credential_id == credential_id)
    )
    if credential is None or credential.revoked_at is not None:
        raise _unauthorized()
    device = db.get(Device, credential.device_id)
    if device is None or device.revoked_at is not None:
        raise _unauthorized()
    if not hmac.compare_digest(
        credential.secret_hash,
        credential_secret_hash(secret),
    ):
        raise _unauthorized()

    credential.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return device
