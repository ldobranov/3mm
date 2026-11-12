from __future__ import annotations

from sqlalchemy.orm import Session

from backend.db.settings import Settings


SESSION_DURATION_KEY = "session_duration_hours"
DEFAULT_SESSION_DURATION_HOURS = 7 * 24
MIN_SESSION_DURATION_HOURS = 1
MAX_SESSION_DURATION_HOURS = 30 * 24


def get_session_duration_hours(db: Session) -> int:
    setting = (
        db.query(Settings)
        .filter(
            Settings.key == SESSION_DURATION_KEY,
            Settings.user_id.is_(None),
            Settings.language_code.is_(None),
        )
        .first()
    )
    if setting is None or setting.value is None:
        return DEFAULT_SESSION_DURATION_HOURS

    try:
        value = int(setting.value)
    except (TypeError, ValueError):
        return DEFAULT_SESSION_DURATION_HOURS

    if not MIN_SESSION_DURATION_HOURS <= value <= MAX_SESSION_DURATION_HOURS:
        return DEFAULT_SESSION_DURATION_HOURS
    return value


def save_session_duration_hours(db: Session, duration_hours: int) -> Settings:
    if not MIN_SESSION_DURATION_HOURS <= duration_hours <= MAX_SESSION_DURATION_HOURS:
        raise ValueError("Session duration is outside the supported range")

    setting = (
        db.query(Settings)
        .filter(
            Settings.key == SESSION_DURATION_KEY,
            Settings.user_id.is_(None),
            Settings.language_code.is_(None),
        )
        .first()
    )
    if setting is None:
        setting = Settings(
            key=SESSION_DURATION_KEY,
            value=str(duration_hours),
            description="Maximum signed-in session duration in hours",
            user_id=None,
            language_code=None,
        )
        db.add(setting)
    else:
        setting.value = str(duration_hours)
    return setting
