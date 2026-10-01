"""Authenticated per-device delivery of prepared Node update archives."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.config import UpdateCatalogSettings, get_settings
from backend.db.device import Device
from backend.services.node_update_delivery import (
    NodeDeliveryError,
    open_node_delivery,
)
from backend.utils.device_auth import require_device


router = APIRouter(
    prefix="/api/v1/devices",
    tags=["node-updates"],
)

CHUNK_SIZE = 1024 * 1024


def _stream_archive(path: Path):
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
    )

    descriptor = os.open(
        path,
        flags,
    )

    try:
        with os.fdopen(
            descriptor,
            "rb",
        ) as source:
            while True:
                chunk = source.read(
                    CHUNK_SIZE
                )

                if not chunk:
                    break

                yield chunk

    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


@router.get(
    "/{device_id}/node-updates/{operation_id}/archive",
)
def download_node_update_archive(
    device_id: str,
    operation_id: str,
    device: Device = Depends(require_device),
    settings: UpdateCatalogSettings = Depends(
        lambda: get_settings().updates
    ),
):
    if device.device_id != device_id:
        raise HTTPException(
            status_code=403,
            detail="Device identity mismatch",
        )

    try:
        prepared, archive_path = (
            open_node_delivery(
                settings,
                operation_id=operation_id,
                device_id=device.device_id,
            )
        )
    except NodeDeliveryError:
        # Do not disclose whether an operation belongs
        # to another paired Node.
        raise HTTPException(
            status_code=404,
            detail="Node update artifact unavailable",
        )

    return StreamingResponse(
        _stream_archive(
            archive_path
        ),
        media_type="application/gzip",
        headers={
            "Content-Length": str(
                prepared.archive_size_bytes
            ),
            "X-3mm-Node-Operation":
                prepared.operation_id,
            "X-3mm-Node-Release":
                prepared.release_id,
            "X-3mm-Node-SHA256":
                prepared.archive_sha256,
        },
    )