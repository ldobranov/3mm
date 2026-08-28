"""Administrator-only device restart and factory reset requests."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.audit_log import AuditLog
from backend.db.user import User
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError

router = APIRouter(prefix="/api/v1/system-control", tags=["system-control"])


class SystemActionRequest(BaseModel):
    confirmation: str

    model_config = ConfigDict(extra="forbid")


class SystemActionQueued(BaseModel):
    status: Literal["queued"] = "queued"
    action: Literal["restart_device", "factory_reset"]


def _queue_system_action(
    *,
    action: Literal["restart_device", "factory_reset"],
    required_confirmation: str,
    payload: SystemActionRequest,
    admin: User,
    db: Session,
) -> SystemActionQueued:
    if payload.confirmation != required_confirmation:
        raise HTTPException(status_code=409, detail="Confirmation does not match")
    try:
        UpdateHelperClient(get_settings().updates.helper_socket).request_system_action(
            action,
            admin.id,
        )
    except (UpdateHelperError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add(
        AuditLog(
            user_id=admin.id,
            action=(
                "DEVICE_RESTART_REQUESTED"
                if action == "restart_device"
                else "FACTORY_RESET_REQUESTED"
            ),
            entity_type="system_control",
            entity_name="standalone",
            changes={"action": action},
        )
    )
    db.commit()
    return SystemActionQueued(action=action)


@router.post(
    "/restart",
    response_model=SystemActionQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
def restart_device(
    payload: SystemActionRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SystemActionQueued:
    return _queue_system_action(
        action="restart_device",
        required_confirmation="RESTART",
        payload=payload,
        admin=admin,
        db=db,
    )


@router.post(
    "/factory-reset",
    response_model=SystemActionQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
def factory_reset(
    payload: SystemActionRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SystemActionQueued:
    return _queue_system_action(
        action="factory_reset",
        required_confirmation="FACTORY RESET",
        payload=payload,
        admin=admin,
        db=db,
    )
