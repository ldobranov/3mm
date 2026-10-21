"""Exact interactive-session requests; declarations are never executable grants."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from three_mm_protocol.interactive_session import SESSION_CONTROL_ACTION_PATTERN
from three_mm_protocol.module_manifest import MODULE_ID_PATTERN
from three_mm_protocol.node_security import validate_node_json


class SessionContractV1(BaseModel):
    """M20 support-profile v1 for the existing interactive-session.v1 wire.

    This profile's integer version is not another stream protocol or the SDK
    provider's semantic contract version. It adds reviewed access/control bounds
    to the existing scalar-valued capability metadata; it grants no isolation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    contract_version: Literal[1]
    access_modes: tuple[Literal["read", "write"], ...] = Field(
        min_length=1, max_length=2
    )
    control_actions: tuple[str, ...] = Field(max_length=16)

    @field_validator("contract_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Session contract version must be an integer")
        return value

    @model_validator(mode="after")
    def unique_sets(self):
        import re

        if len(self.access_modes) != len(set(self.access_modes)) or len(
            self.control_actions
        ) != len(set(self.control_actions)):
            raise ValueError("Session contract sets must be unique")
        if any(
            re.fullmatch(SESSION_CONTROL_ACTION_PATTERN, value) is None
            for value in self.control_actions
        ):
            raise ValueError("Session control action is invalid")
        return self


class ApplicationSessionBindingV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: Literal[1]
    binding_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    target_device_config_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    provider_id: str = Field(pattern=MODULE_ID_PATTERN, max_length=160)
    capability_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
    access_mode: Literal["read", "write"]
    control_actions: tuple[str, ...] = Field(max_length=16)
    required_permission: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    options: dict[str, object] = Field(default_factory=dict)

    @field_validator("contract_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        return SessionContractV1.integer_version(value)

    @model_validator(mode="after")
    def exact_controls(self):
        SessionContractV1(
            contract_version=self.contract_version,
            access_modes=(self.access_mode,),
            control_actions=self.control_actions,
        )
        validate_node_json(self.options, max_bytes=8192)
        return self


class ApplicationSessionProviderV1(BaseModel):
    """Factory in the SAME reviewed service wheel; no executable host policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    capability_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
    factory: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$", max_length=240
    )
    resource_profile: Literal["isolated_session_v1"]
    contract: SessionContractV1

    @field_validator("contract", mode="before")
    @classmethod
    def parse_contract(cls, value):
        if isinstance(value, SessionContractV1):
            return value
        return SessionContractV1.model_validate_json(json.dumps(value), strict=True)


def session_contract(metadata: dict) -> SessionContractV1:
    """No inventory/hello fallback. Metadata remains the legacy scalar dialect."""
    raw = metadata.get("interactive_session_contract")
    if type(raw) is not str or len(raw.encode("utf-8")) > 512:
        raise ValueError("An exact provider session contract is required")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate session contract field")
            result[key] = value
        return result

    data = json.loads(raw, object_pairs_hook=unique)
    if type(data) is not dict or type(data.get("contract_version")) is not int:
        raise ValueError("Session contract version must be an integer")
    return SessionContractV1.model_validate_json(json.dumps(data), strict=True)
