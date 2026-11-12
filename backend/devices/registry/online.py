"""Read-side policy for the Core device registry."""

from datetime import datetime, timedelta, timezone


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def is_device_online(
    *,
    last_seen_at: datetime | None,
    now: datetime,
    offline_after: timedelta,
    revoked_at: datetime | None = None,
) -> bool:
    if now.tzinfo is None:
        raise ValueError("Online status timestamps must include a timezone")
    if offline_after <= timedelta(0):
        raise ValueError("Offline threshold must be positive")
    normalized_last_seen = as_utc(last_seen_at)
    if revoked_at is not None or normalized_last_seen is None:
        return False
    return normalized_last_seen >= now.astimezone(timezone.utc) - offline_after
