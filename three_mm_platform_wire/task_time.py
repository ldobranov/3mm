"""Bounded calendar arithmetic shared by a worker and Core's admission verifier.

No timers, registry, database, environment mutation or third-party dependency.
Missed occurrences are coalesced; gaps skip and folds use their earliest instant.
"""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


def instant(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("Schedule instants require a timezone")
    return value.astimezone(UTC)


def calendar_instant(rule, day):
    if day.weekday() not in rule["weekdays"]:
        return None
    zone = ZoneInfo(rule["timezone"])
    wall = datetime(day.year, day.month, day.day, rule["hour"], rule["minute"])
    candidates = []
    for fold in (0, 1):
        candidate = wall.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if candidate.astimezone(zone).replace(tzinfo=None) == wall:
            candidates.append(candidate)
    return min(candidates) if candidates else None


def latest_occurrence(rule, start_at, end_at, at):
    start, end, at = instant(start_at), instant(end_at), instant(at)
    if at < start:
        return None
    limit = min(at, end - timedelta(microseconds=1))
    if rule["kind"] == "interval":
        step = timedelta(seconds=rule["every_seconds"])
        return start + ((limit - start) // step) * step
    day = limit.astimezone(ZoneInfo(rule["timezone"])).date()
    # A weekly rule can lose one scheduled day to a clock gap or skipped date.
    # Fifteen days covers its preceding/next valid weekly occurrence.
    for offset in range(15):
        value = calendar_instant(rule, day - timedelta(days=offset))
        if value is not None and start <= value <= limit:
            return value
    return None


def next_occurrence(rule, start_at, end_at, after):
    start, end, after = instant(start_at), instant(end_at), instant(after)
    if rule["kind"] == "interval":
        step = timedelta(seconds=rule["every_seconds"])
        value = start + max(0, (after - start) // step + 1) * step
        return value if value < end else None
    day = max(start, after).astimezone(ZoneInfo(rule["timezone"])).date()
    for offset in range(15):
        value = calendar_instant(rule, day + timedelta(days=offset))
        if value is not None and start <= value < end and value > after:
            return value
    return None


def occurrence_count(rule, start_at, after, through):
    """Count skipped occurrences with at most 368 local-day probes."""
    start, through = instant(start_at), instant(through)
    after = instant(after) if after is not None else start - timedelta(microseconds=1)
    if through <= after or through < start:
        return 0
    if rule["kind"] == "interval":
        step = timedelta(seconds=rule["every_seconds"])
        return max(0, (through - start) // step - max(-1, (after - start) // step))
    zone = ZoneInfo(rule["timezone"])
    first, last = max(start, after).astimezone(zone).date(), through.astimezone(zone).date()
    days = (last - first).days
    if not 0 <= days <= 367:
        raise ValueError("Schedule count exceeds the one-year horizon")
    count = 0
    for offset in range(days + 1):
        value = calendar_instant(rule, first + timedelta(days=offset))
        count += value is not None and start <= value <= through and value > after
    return count
