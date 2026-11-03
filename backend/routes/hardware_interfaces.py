"""Administrator-only, local-device-bound hardware setup. Not an application API."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.audit_log import AuditLog
from backend.db.device import Device
from backend.db.user import User
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError

router = APIRouter(prefix='/api/v1/devices', tags=['hardware-interfaces'])


class EnableI2cRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    expected_revision: str = Field(pattern=r'^[0-9a-f]{64}$')
    confirmation: str = Field(max_length=100)


class RestartRequest(EnableI2cRequest):
    source_request_id: str = Field(pattern=r'^[0-9a-f]{32}$')


def device(db, device_id):
    row = db.scalar(select(Device).where(Device.device_id == device_id))
    if row is None:
        raise HTTPException(404, 'Device not found')
    if row.revoked_at is not None:
        raise HTTPException(409, 'Device access is revoked')
    return row


def helper():
    return UpdateHelperClient(get_settings().updates.helper_socket)


@router.get('/{device_id}/hardware-interfaces')
def inspect(device_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    device(db, device_id)
    try:
        return helper().hardware_interfaces_status(device_id, admin.id)
    except (UpdateHelperError, ValueError, KeyError):
        raise HTTPException(503, 'Hardware inspection is unavailable; no device change was requested') from None


def mutate(device_id, payload, admin, db, *, restarting=False):
    device(db, device_id)
    phrase = ('RESTART ' if restarting else 'ENABLE I2C ') + device_id
    if payload.confirmation != phrase:
        raise HTTPException(409, 'Exact device confirmation is required')
    try:
        method = helper().restart_after_i2c if restarting else helper().enable_i2c
        identifier = method(device_id, admin.id, **payload.model_dump())
    except (UpdateHelperError, ValueError):
        raise HTTPException(409, 'Operation refused or unconfirmed. Preserve the request ID and inspect status; do not resend.') from None
    db.add(AuditLog(user_id=admin.id, action='HARDWARE_RESTART_REQUESTED' if restarting else 'HARDWARE_I2C_ENABLE_REQUESTED',
                    entity_type='device', entity_name=device_id,
                    changes={'request_id': identifier, 'expected_revision': payload.expected_revision}))
    db.commit()
    return {'status': 'queued', 'request_id': identifier}


@router.post('/{device_id}/hardware-interfaces/i2c/enable', status_code=202)
def enable(device_id: str, payload: EnableI2cRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return mutate(device_id, payload, admin, db)


@router.post('/{device_id}/hardware-interfaces/restart', status_code=202)
def restart(device_id: str, payload: RestartRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return mutate(device_id, payload, admin, db, restarting=True)
