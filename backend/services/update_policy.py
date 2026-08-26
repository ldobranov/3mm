"""Persistent operational policy for safe, administrator-controlled OTA updates."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import suppress
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from threading import RLock
from typing import Callable, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.config import UpdateCatalogSettings, get_settings
from backend.services.system_updates import (
    UpdateCatalogError,
    UpdateChannel,
    UpdateCheckResponse,
    check_update_catalog,
)

logger = logging.getLogger(__name__)
_state_lock = RLock()


class UpdatePolicyError(RuntimeError):
    """Raised when the persisted update policy cannot be trusted or applied."""


class UpdatePolicy(BaseModel):
    schema_version: Literal[1] = 1
    channel: UpdateChannel = "stable"
    automatic_checks_enabled: bool = False
    check_interval_hours: int = Field(default=6, ge=1, le=168)
    maintenance_window_enabled: bool = False
    maintenance_timezone: str = Field(default="UTC", min_length=1, max_length=64)
    maintenance_start: str = Field(
        default="03:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$"
    )
    maintenance_duration_minutes: int = Field(default=120, ge=15, le=720)

    model_config = ConfigDict(extra="forbid")

    @field_validator("maintenance_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown IANA maintenance timezone") from exc
        return value


class UpdatePolicyRequest(BaseModel):
    channel: UpdateChannel = "stable"
    automatic_checks_enabled: bool = False
    check_interval_hours: int = Field(default=6, ge=1, le=168)
    maintenance_window_enabled: bool = False
    maintenance_timezone: str = Field(default="UTC", min_length=1, max_length=64)
    maintenance_start: str = Field(
        default="03:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$"
    )
    maintenance_duration_minutes: int = Field(default=120, ge=15, le=720)

    model_config = ConfigDict(extra="forbid")

    @field_validator("maintenance_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return UpdatePolicy.validate_timezone(value)


class UpdateCheckCache(BaseModel):
    schema_version: Literal[1] = 1
    channel: UpdateChannel
    result: UpdateCheckResponse | None = None
    last_attempt_at: datetime
    last_success_at: datetime | None = None
    next_check_at: datetime
    consecutive_failures: int = Field(default=0, ge=0, le=1000)
    last_error: str | None = Field(default=None, max_length=300)

    model_config = ConfigDict(extra="forbid")


class UpdatePolicyStatus(BaseModel):
    policy: UpdatePolicy
    cached_check: UpdateCheckCache | None
    within_maintenance_window: bool
    current_window_started_at: datetime | None = None
    current_window_ends_at: datetime | None = None
    next_window_starts_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")


CatalogChecker = Callable[..., UpdateCheckResponse]


def _atomic_json_write(path: Path, payload: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(
                payload.model_dump(mode="json"),
                output,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise UpdatePolicyError("Update policy state could not be written") from exc


def _read_model(path: Path, model_type: type[BaseModel]) -> BaseModel | None:
    if not path.is_file():
        return None
    try:
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        raise UpdatePolicyError(f"Update policy state is invalid: {path.name}") from exc


def read_update_policy(settings: UpdateCatalogSettings) -> UpdatePolicy:
    with _state_lock:
        loaded = _read_model(settings.policy_file, UpdatePolicy)
    return loaded if isinstance(loaded, UpdatePolicy) else UpdatePolicy()


def save_update_policy(
    settings: UpdateCatalogSettings, request: UpdatePolicyRequest
) -> UpdatePolicy:
    policy = UpdatePolicy.model_validate(request.model_dump())
    with _state_lock:
        _atomic_json_write(settings.policy_file, policy)
    return policy


def read_update_check_cache(
    settings: UpdateCatalogSettings,
) -> UpdateCheckCache | None:
    with _state_lock:
        loaded = _read_model(settings.check_cache_file, UpdateCheckCache)
    return loaded if isinstance(loaded, UpdateCheckCache) else None


def _window_status(
    policy: UpdatePolicy, now: datetime
) -> tuple[bool, datetime | None, datetime | None, datetime | None]:
    if not policy.maintenance_window_enabled:
        return False, None, None, None
    zone = ZoneInfo(policy.maintenance_timezone)
    local_now = now.astimezone(zone)
    hour, minute = (int(part) for part in policy.maintenance_start.split(":"))
    start_time = time(hour, minute)
    duration = timedelta(minutes=policy.maintenance_duration_minutes)
    current_start: datetime | None = None
    current_end: datetime | None = None
    next_start: datetime | None = None
    for day_offset in range(-1, 9):
        day = local_now.date() + timedelta(days=day_offset)
        candidate = datetime.combine(day, start_time, tzinfo=zone)
        candidate_end = candidate + duration
        if candidate <= local_now < candidate_end:
            current_start, current_end = candidate, candidate_end
        elif candidate > local_now and next_start is None:
            next_start = candidate
    return (
        current_start is not None,
        current_start.astimezone(UTC) if current_start else None,
        current_end.astimezone(UTC) if current_end else None,
        next_start.astimezone(UTC) if next_start else None,
    )


def read_update_policy_status(
    settings: UpdateCatalogSettings, *, now: datetime | None = None
) -> UpdatePolicyStatus:
    policy = read_update_policy(settings)
    within, started, ends, next_start = _window_status(policy, now or datetime.now(UTC))
    return UpdatePolicyStatus(
        policy=policy,
        cached_check=read_update_check_cache(settings),
        within_maintenance_window=within,
        current_window_started_at=started,
        current_window_ends_at=ends,
        next_window_starts_at=next_start,
    )


def ensure_apply_is_allowed(
    settings: UpdateCatalogSettings,
    *,
    maintenance_override: bool,
    now: datetime | None = None,
) -> UpdatePolicyStatus:
    status = read_update_policy_status(settings, now=now)
    if (
        status.policy.maintenance_window_enabled
        and not status.within_maintenance_window
        and not maintenance_override
    ):
        raise UpdatePolicyError(
            "The update is outside the maintenance window; explicit override is required"
        )
    return status


def check_and_cache_update_catalog(
    settings: UpdateCatalogSettings,
    *,
    channel: UpdateChannel,
    checker: CatalogChecker = check_update_catalog,
    now: datetime | None = None,
) -> UpdateCheckResponse:
    attempted_at = now or datetime.now(UTC)
    previous = read_update_check_cache(settings)
    try:
        result = checker(settings, channel=channel)
    except Exception as exc:
        failures = (
            previous.consecutive_failures + 1
            if previous is not None and previous.channel == channel
            else 1
        )
        backoff_minutes = min(15 * (2 ** (failures - 1)), 24 * 60)
        failed = UpdateCheckCache(
            channel=channel,
            result=(
                previous.result
                if previous is not None and previous.channel == channel
                else None
            ),
            last_attempt_at=attempted_at,
            last_success_at=(
                previous.last_success_at
                if previous is not None and previous.channel == channel
                else None
            ),
            next_check_at=attempted_at + timedelta(minutes=backoff_minutes),
            consecutive_failures=failures,
            last_error=str(exc)[:300] or "Update catalog check failed",
        )
        with _state_lock:
            _atomic_json_write(settings.check_cache_file, failed)
        raise
    policy = read_update_policy(settings)
    succeeded = UpdateCheckCache(
        channel=channel,
        result=result,
        last_attempt_at=attempted_at,
        last_success_at=attempted_at,
        next_check_at=attempted_at + timedelta(hours=policy.check_interval_hours),
    )
    with _state_lock:
        _atomic_json_write(settings.check_cache_file, succeeded)
    return result


def run_due_automatic_check(
    settings: UpdateCatalogSettings,
    *,
    checker: CatalogChecker = check_update_catalog,
    now: datetime | None = None,
) -> bool:
    attempted_at = now or datetime.now(UTC)
    policy = read_update_policy(settings)
    if not policy.automatic_checks_enabled:
        return False
    cached = read_update_check_cache(settings)
    if (
        cached is not None
        and cached.channel == policy.channel
        and cached.next_check_at > attempted_at
    ):
        return False
    try:
        check_and_cache_update_catalog(
            settings, channel=policy.channel, checker=checker, now=attempted_at
        )
    except UpdateCatalogError:
        logger.warning("Automatic system update catalog check failed")
    except Exception:
        logger.exception("Unexpected automatic system update catalog check failure")
    return True


class SystemUpdateCheckManager:
    """Own the lifecycle of opt-in, read-only background catalog checks."""

    def __init__(self) -> None:
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._worker_task and not self._worker_task.done():
            return
        self._worker_task = asyncio.create_task(
            self._run(), name="system-update-check-worker"
        )

    async def stop(self) -> None:
        if not self._worker_task:
            return
        self._worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._worker_task
        self._worker_task = None

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.to_thread(run_due_automatic_check, get_settings().updates)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("System update check worker iteration failed")
            await asyncio.sleep(60)


system_update_check_manager = SystemUpdateCheckManager()
