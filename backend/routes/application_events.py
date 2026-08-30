"""Administrative observability and retry controls for the event broker."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.user import User
from backend.services.application_events import (
    application_event_status,
    retry_application_events_once,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db


router = APIRouter(
    prefix="/api/v1/application-events",
    tags=["application-events"],
)


@router.get("/status")
def event_broker_status(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return {"subscriptions": application_event_status(db)}


@router.post("/drain")
def drain_event_broker(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    retry_application_events_once(get_settings().applications)
    return {"status": "completed", "subscriptions": application_event_status(db)}
