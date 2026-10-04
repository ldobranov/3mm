"""HTTP error translation only; logical device operations live in services."""

from fastapi import HTTPException
from three_mm_protocol.transport import DeviceProtocolError


def call(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except DeviceProtocolError as exc:
        status = {
            "unauthorized": 401,
            "forbidden": 403,
            "conflict": 409,
            "capacity": 429,
        }[exc.kind]
        headers = {"WWW-Authenticate": "Device"} if exc.kind == "unauthorized" else None
        raise HTTPException(status, detail=exc.detail, headers=headers) from exc
