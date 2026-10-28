from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db.session import Session as UserSession
from backend.services.session_policy import (
    DEFAULT_SESSION_DURATION_HOURS,
    MAX_SESSION_DURATION_HOURS,
    MIN_SESSION_DURATION_HOURS,
    get_session_duration_hours,
    save_session_duration_hours,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token, decode_token_for_refresh

router = APIRouter()


class SessionSettingsResponse(BaseModel):
    duration_hours: int = DEFAULT_SESSION_DURATION_HOURS
    minimum_hours: int = MIN_SESSION_DURATION_HOURS
    maximum_hours: int = MAX_SESSION_DURATION_HOURS


class SessionSettingsUpdate(BaseModel):
    duration_hours: int = Field(
        ge=MIN_SESSION_DURATION_HOURS,
        le=MAX_SESSION_DURATION_HOURS,
    )


@router.post("/user/refresh")
async def refresh_access_token(request: Request, db: Session = Depends(get_db)):
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    raw_token = auth.split(" ", 1)[1].strip()

    # The JWT signature must be valid, but the short access-token lifetime may
    # have elapsed while a phone was asleep or Core was restarting.
    claims = decode_token_for_refresh(raw_token)
    if claims.get("token_type", "user") != "user":
        raise HTTPException(status_code=401, detail="A normal user token is required")
    from backend.services.application_access import validate_application_login
    validate_application_login(claims, db)

    subject = str(claims.get("sub") or claims.get("user_id") or "")
    if not subject:
        raise HTTPException(status_code=401, detail="Invalid subject")

    session = db.get(UserSession, claims["sid"])
    now = datetime.utcnow()
    if session is None or session.expires_at is None or session.expires_at <= now:
        if session is not None:
            session.is_active = False
            db.commit()
        raise HTTPException(status_code=401, detail="Session expired")

    extra = {k: v for k, v in claims.items() if k not in ("sub", "iat", "exp", "sid")}
    extra["sid"] = session.id
    new_token = create_access_token(subject=subject, extra_claims=extra)
    session.token = new_token
    session.last_activity = now
    session.expires_at = now + timedelta(hours=get_session_duration_hours(db))
    db.commit()
    return {"token": new_token}


@router.get(
    "/admin/session-settings",
    response_model=SessionSettingsResponse,
    dependencies=[Depends(require_admin)],
)
def read_session_settings(db: Session = Depends(get_db)) -> SessionSettingsResponse:
    return SessionSettingsResponse(duration_hours=get_session_duration_hours(db))


@router.put(
    "/admin/session-settings",
    response_model=SessionSettingsResponse,
    dependencies=[Depends(require_admin)],
)
def update_session_settings(
    payload: SessionSettingsUpdate,
    db: Session = Depends(get_db),
) -> SessionSettingsResponse:
    save_session_duration_hours(db, payload.duration_hours)
    expires_at = datetime.utcnow() + timedelta(hours=payload.duration_hours)
    db.query(UserSession).filter(UserSession.is_active.is_(True)).update(
        {UserSession.expires_at: expires_at},
        synchronize_session=False,
    )
    db.commit()
    return SessionSettingsResponse(duration_hours=payload.duration_hours)
