"""Authentication dependency for unique revocable device credentials."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.db.device import Device
from backend.services.device_protocol import authenticate_device
from backend.utils.device_protocol_http import call
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
    if not authorization or len(authorization) > 1024 or not authorization.startswith("Device "):
        raise _unauthorized()
    presented = authorization.removeprefix("Device ").strip()
    credential_id, separator, secret = presented.partition(":")
    if not separator or not credential_id or not secret:
        raise _unauthorized()

    return call(authenticate_device, db, credential_id, secret)
