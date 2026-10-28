"""First task profile: bounded, result-only, one-shot application work."""
from datetime import UTC, timedelta
from typing import Annotated, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
import json
import math


def scalar_object(value):
    if type(value) is not dict or len(value) > 8:
        raise ValueError("Task data requires at most eight scalar fields")
    for key, item in value.items():
        if type(key) is not str or not 1 <= len(key) <= 128:
            raise ValueError("Task field name is invalid")
        if not (type(item) is bool or type(item) is str and len(item) <= 512
                or type(item) in (int, float) and math.isfinite(item) and abs(item) <= 2**53 - 1):
            raise ValueError("Task values require bounded finite scalars")
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode()) > 8192:
        raise ValueError("Task data exceeds its byte budget")
    return value

class TaskModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def utc_time(value):
    from three_mm_platform_wire.task_time import instant
    return instant(value)


def task_command_request_id(task_run_id, binding_id, request_id):
    import hashlib
    return hashlib.sha256(json.dumps([task_run_id, binding_id, request_id], separators=(",", ":")).encode()).hexdigest()


class ApplicationTaskV1(TaskModel):
    task_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    handler_operation_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    profile: Literal["bounded_result_once_v1", "bounded_task_v1"]
    max_runtime_seconds: int = Field(ge=1, le=10)
    max_delay_seconds: int = Field(ge=0, le=3600)
    max_pending: int = Field(default=8, ge=1, le=8)


class TaskSubmitV1(TaskModel):
    task_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    payload: dict
    due_at: AwareDatetime
    not_after: AwareDatetime

    @field_validator("payload", mode="before")
    @classmethod
    def bounded_payload(cls, value):
        return scalar_object(value)

    @field_validator("due_at", "not_after", mode="before")
    @classmethod
    def utc(cls, value):
        return utc_time(value)


class TaskLookupV1(TaskModel):
    task_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    request_id: str = Field(pattern=r"^(?:occ_)?[0-9a-f]{32}$")


class TaskExecutionV1(TaskModel):
    task_run_id: str = Field(pattern=r"^task_[0-9a-f]{32}$")
    task_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    lease_token: str = Field(pattern=r"^[0-9a-f]{64}$")


class TaskProgressV1(TaskModel):
    execution: TaskExecutionV1
    progress: int = Field(ge=0, le=99)


class TaskStartV1(TaskModel):
    task_run_id: str = Field(pattern=r"^task_[0-9a-f]{32}$")
    task_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    lease_until: AwareDatetime
    lease_remaining_seconds: float = Field(gt=0, le=10, allow_inf_nan=False)


class TaskStatusV1(TaskModel):
    task_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    request_id: str = Field(pattern=r"^(?:occ_)?[0-9a-f]{32}$")
    task_run_id: str | None = Field(pattern=r"^task_[0-9a-f]{32}$")
    status: Literal["not_found", "queued", "running", "succeeded", "failed", "expired", "cancelled", "unknown", "resolved"]
    progress: int = Field(ge=0, le=100)
    result: dict | None
    error_code: Literal["handler_failed", "not_dispatched", "execution_unconfirmed", "authority_changed", "deadline_exceeded"] | None

    @model_validator(mode="after")
    def consistent(self):
        if (self.status == "not_found") != (self.task_run_id is None):
            raise ValueError("Task result identity is inconsistent")
        if self.status == "succeeded":
            scalar_object(self.result)
            if self.progress != 100 or self.error_code is not None:
                raise ValueError("Successful task requires a confirmed result")
        elif self.result is not None:
            raise ValueError("Unconfirmed task cannot expose a successful result")
        return self


class IntervalRuleV1(TaskModel):
    kind: Literal["interval"]
    every_seconds: int = Field(ge=5, le=31_536_000)
    misfire: Literal["skip"] = "skip"


class CalendarRuleV1(TaskModel):
    kind: Literal["calendar"]
    timezone: str = Field(min_length=1, max_length=128)
    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)
    weekdays: tuple[int, ...] = Field(default=(0, 1, 2, 3, 4, 5, 6), min_length=1, max_length=7)
    misfire: Literal["skip"] = "skip"
    gap: Literal["skip"] = "skip"
    fold: Literal["earliest"] = "earliest"

    @field_validator("timezone")
    @classmethod
    def known_zone(cls, value):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("An installed IANA timezone is required") from None
        return value

    @field_validator("weekdays", mode="before")
    @classmethod
    def distinct_days(cls, value):
        if type(value) not in (list, tuple) or len(set(value)) != len(value) or any(type(day) is not int or not 0 <= day <= 6 for day in value):
            raise ValueError("Weekdays must be distinct integers 0..6")
        return tuple(sorted(value))


class TaskScheduleCreateV1(TaskModel):
    task_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    payload: dict
    start_at: AwareDatetime
    end_at: AwareDatetime
    rule: Annotated[IntervalRuleV1 | CalendarRuleV1, Field(discriminator="kind")]
    max_occurrences: int = Field(default=1_000_000, ge=1, le=1_000_000)
    history_limit: int = Field(default=16, ge=1, le=64)
    start_window_seconds: int = Field(default=5, ge=1, le=20)

    @field_validator("payload", mode="before")
    @classmethod
    def bounded_payload(cls, value):
        return scalar_object(value)

    @field_validator("start_at", "end_at", mode="before")
    @classmethod
    def utc(cls, value):
        return utc_time(value)

    @model_validator(mode="after")
    def finite_horizon(self):
        if not timedelta(0) < self.end_at - self.start_at <= timedelta(days=366):
            raise ValueError("Schedule horizon must be positive and at most 366 days")
        return self


class TaskScheduleLookupV1(TaskModel):
    task_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class TaskScheduleStatusV1(TaskModel):
    task_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    schedule_id: str | None = Field(pattern=r"^schedule_[0-9a-f]{32}$")
    status: Literal["not_found", "active", "cancelled", "exhausted", "blocked"]
    admitted: int = Field(ge=0)
    skipped: int = Field(ge=0)
    last_request_id: str | None = Field(default=None, pattern=r"^occ_[0-9a-f]{32}$")
    last_due_at: AwareDatetime | None = None
    error_code: Literal["authority_changed", "execution_unconfirmed", "history_full"] | None = None

    @model_validator(mode="after")
    def identity(self):
        if (self.status == "not_found") != (self.schedule_id is None):
            raise ValueError("Schedule identity is inconsistent")
        return self
