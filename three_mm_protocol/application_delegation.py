"""Bounded same-application operation delegation; no bearer or Core credential."""
import json
import math
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
from three_mm_protocol.module_manifest import MODULE_ID_PATTERN

ID = r"^[a-z][a-z0-9_]{0,95}$"
HEX = r"^[0-9a-f]{32}$"
DIGEST = r"^[0-9a-f]{64}$"


def bounded_object(value, *, limit=16_384):
    if type(value) is not dict:
        raise ValueError("An object is required")
    pending, count = [(value, 0)], 0
    while pending:
        item, depth = pending.pop(); count += 1
        if count > 2048 or depth > 12:
            raise ValueError("Delegation data exceeds its budget")
        if type(item) is dict:
            if any(type(k) is not str for k in item): raise ValueError("Invalid object key")
            if any(len(k) > 4096 or any(0xD800 <= ord(c) <= 0xDFFF for c in k) for k in item):
                raise ValueError("Invalid JSON key")
            pending.extend((v, depth + 1) for v in item.values())
        elif type(item) is list:
            pending.extend((v, depth + 1) for v in item)
        elif item is not None and (type(item) not in (str, bool, int, float)
                or type(item) is float and not math.isfinite(item)):
            raise ValueError("Invalid JSON value")
        if (type(item) is str and (len(item) > 4096 or any(0xD800 <= ord(c) <= 0xDFFF for c in item))
                or type(item) in (int, float) and abs(item) > 2**53-1):
            raise ValueError("JSON value exceeds the sealed journal profile")
    # Budget the exact ASCII escaping used by the existing sealed journal, so
    # every admitted request/result fits its storage and read-back budgets.
    if len(json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))) > limit:
        raise ValueError("Delegation data exceeds its budget")
    return value


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    @field_validator("expires_at", mode="before", check_fields=False)
    @classmethod
    def wire_datetime(cls, value):
        if isinstance(value, str):
            from datetime import datetime
            if "T" not in value: raise ValueError("An ISO datetime is required")
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @field_validator("access_version", "delegation_version", mode="before", check_fields=False)
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int: raise ValueError("Version must be an integer")
        return value

    @field_validator("automatic_retry", "admission_required", "redelegation_allowed", mode="before", check_fields=False)
    @classmethod
    def boolean_flag(cls, value):
        if type(value) is not bool: raise ValueError("Flag must be a boolean")
        return value


class DelegationCreateV1(Model):
    request_id: str = Field(pattern=HEX)
    operation_id: str = Field(pattern=ID)
    payload: dict
    ttl_seconds: int = Field(default=60, ge=5, le=300)

    @field_validator("payload", mode="before")
    @classmethod
    def bounded(cls, value): return bounded_object(value)


class UserActorV1(Model):
    kind: Literal["user"] = "user"
    user_id: int = Field(ge=1, le=2**53-1)
    subject_id: str = Field(pattern=r"^usr_[0-9a-f]{32}$")


class BrowserActorV1(Model):
    kind: Literal["user", "kiosk", "anonymous"]
    user_id: int | None = Field(ge=1, le=2**53-1)
    subject_id: str | None = Field(pattern=r"^usr_[0-9a-f]{32}$")
    terminal_id: str | None = Field(pattern=HEX)
    platform_administrator: bool

    @model_validator(mode="after")
    def consistent(self):
        import re
        if (self.kind == "user" and (self.user_id is None or self.subject_id is None or self.user_id < 1 or self.terminal_id is not None)
                or self.kind != "user" and (self.user_id is not None or self.subject_id is not None or self.platform_administrator)
                or self.kind == "kiosk" and (self.terminal_id is None or re.fullmatch(HEX, self.terminal_id) is None)
                or self.kind != "kiosk" and self.terminal_id is not None):
            raise ValueError("Actor fields disagree")
        return self


class OperationExecutorV1(Model):
    kind: Literal["application"] = "application"
    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    instance_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    artifact_sha256: str = Field(pattern=DIGEST)


class ActorAccessV1(Model):
    access_version: Literal[1] = 1
    entrypoint_id: str = Field(pattern=ID)
    audience: Literal["public", "kiosk", "operator", "administrator"]
    built_ui_sha256: str | None = Field(pattern=DIGEST)
    actor: BrowserActorV1
    executor: OperationExecutorV1
    permission_ids: list[str] = Field(max_length=96)
    allowed_operation_ids: list[str] = Field(max_length=256)
    delegated_operation_ids: list[str] = Field(max_length=16)
    service_authority: Literal["separate"] = "separate"
    admission_required: Literal[True] = True

    @field_validator("permission_ids", "allowed_operation_ids", "delegated_operation_ids")
    @classmethod
    def identifiers(cls, value):
        import re
        if len(value) != len(set(value)) or any(re.fullmatch(ID, item) is None for item in value):
            raise ValueError("Access IDs are invalid")
        return value

    @model_validator(mode="after")
    def consistent(self):
        if (self.actor.kind != "user" and self.permission_ids
                or set(self.delegated_operation_ids) - set(self.allowed_operation_ids)
                or self.audience != "operator" and self.delegated_operation_ids
                or self.audience in {"operator", "administrator"} and self.actor.kind != "user"
                or self.audience == "administrator" and not self.actor.platform_administrator
                or self.audience == "kiosk" and self.actor.kind != "kiosk"
                or self.audience == "public" and self.actor.kind != "anonymous"):
            raise ValueError("Access choices disagree")
        return self


class OperationDelegationV1(Model):
    delegation_version: Literal[1] = 1
    delegation_id: str = Field(pattern=HEX)
    operation_id: str = Field(pattern=ID)
    payload_sha256: str = Field(pattern=DIGEST)
    required_permission: str = Field(pattern=ID)
    initiator: UserActorV1
    executor: OperationExecutorV1
    expires_at: AwareDatetime
    redelegation_allowed: Literal[False] = False


class DelegationReceiptV1(Model):
    delegation_version: Literal[1] = 1
    delegation_id: str = Field(pattern=HEX)
    operation_id: str = Field(pattern=ID)
    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    status: Literal["pending", "running", "succeeded", "cancelled", "expired", "denied", "unknown"]
    initiator: UserActorV1
    executor: OperationExecutorV1
    expires_at: AwareDatetime
    result: dict | None
    error_code: Literal["expired", "authority_changed", "execution_unconfirmed"] | None
    automatic_retry: Literal[False] = False

    @field_validator("result", mode="before")
    @classmethod
    def bounded(cls, value): return None if value is None else bounded_object(value, limit=32_768)

    @model_validator(mode="after")
    def consistent(self):
        if (self.status == "succeeded") != (self.result is not None):
            raise ValueError("Only confirmed success contains an operation result")
        expected = {"expired": "expired", "unknown": "execution_unconfirmed", "denied": "authority_changed"}.get(self.status)
        if self.error_code != expected:
            raise ValueError("Delegation status and error disagree")
        return self
