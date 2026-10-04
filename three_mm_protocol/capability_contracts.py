"""Small, provider/transport-neutral capability contracts; no hardware catalog.

Exact versions only. The deliberately limited schema dialect has strict objects
and bounded scalars, not refs, executable validators, regexes or remote schemas.
"""

import hashlib
import json
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from three_mm_protocol.node_security import validate_node_json

ContractVersion = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,3}\.[0-9]{1,4}$")]
ContractName = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")]
CONTRACT_FEATURE = "capability_contracts.v1"


class CapabilityContractError(ValueError):
    pass


def _finite_number(value):
    try:
        return type(value) in {int, float} and math.isfinite(value)
    except OverflowError:
        return False


def _scalar_matches(value, kind):
    return (
        type(value) is bool
        if kind == "boolean"
        else (
            isinstance(value, str)
            if kind == "string"
            else (
                type(value) is int
                if kind == "integer"
                else (
                    _finite_number(value)
                    if kind == "number"
                    else value is None if kind == "null" else False
                )
            )
        )
    )


def validate_schema(schema, *, depth=0):
    if not isinstance(schema, dict) or depth > 4:
        raise CapabilityContractError("Contract schema depth/type is invalid")
    kind = schema.get("type")
    if kind == "object":
        properties = schema.get("properties")
        required = schema.get("required", [])
        if (
            set(schema) - {"type", "properties", "required", "additionalProperties"}
            or schema.get("additionalProperties") is not False
            or not isinstance(properties, dict)
            or len(properties) > 32
            or not isinstance(required, list)
            or any(not isinstance(k, str) for k in required)
            or len(required) != len(set(required))
            or set(required) - set(properties)
        ):
            raise CapabilityContractError(
                "Contract requires a bounded strict object schema"
            )
        for key, field in properties.items():
            if not isinstance(key, str) or not 1 <= len(key) <= 160:
                raise CapabilityContractError("Contract field name is invalid")
            validate_schema(field, depth=depth + 1)
        return
    allowed = {"type", "enum"}
    if kind == "string":
        allowed |= {"minLength", "maxLength"}
        if (
            type(schema.get("maxLength")) is not int
            or not 1 <= schema["maxLength"] <= 512
            or type(schema.get("minLength", 0)) is not int
            or not 0 <= schema.get("minLength", 0) <= schema["maxLength"]
        ):
            raise CapabilityContractError("Contract strings require bounded lengths")
    elif kind in {"integer", "number"}:
        allowed |= {"minimum", "maximum"}
        if (
            not all(_finite_number(schema.get(k)) for k in ("minimum", "maximum"))
            or schema["minimum"] > schema["maximum"]
        ):
            raise CapabilityContractError(
                "Contract numbers require finite ordered bounds"
            )
    elif kind not in {"boolean", "null"}:
        raise CapabilityContractError("Unsupported contract schema type")
    if set(schema) - allowed:
        raise CapabilityContractError("Unsupported contract schema keyword")
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list) or not 1 <= len(enum) <= 32:
            raise CapabilityContractError("Contract enum must be bounded")
        for value in enum:
            validate_value(value, {k: v for k, v in schema.items() if k != "enum"})


def validate_value(value, schema):
    """Use only with a validated contract. No coercion (notably bool != int)."""
    kind = schema["type"]
    if kind == "object":
        properties = schema["properties"]
        if (
            not isinstance(value, dict)
            or set(value) - set(properties)
            or set(schema.get("required", [])) - set(value)
        ):
            raise CapabilityContractError("Contract object fields do not match")
        for name, item in value.items():
            validate_value(item, properties[name])
        return
    if not _scalar_matches(value, kind):
        raise CapabilityContractError("Contract value type does not match")
    if (
        kind == "string"
        and not schema.get("minLength", 0) <= len(value) <= schema["maxLength"]
    ):
        raise CapabilityContractError("Contract string length does not match")
    if (
        kind in {"integer", "number"}
        and not schema["minimum"] <= value <= schema["maximum"]
    ):
        raise CapabilityContractError("Contract number is outside bounds")
    if "enum" in schema and value not in schema["enum"]:
        raise CapabilityContractError("Contract value is not in enum")


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CapabilityActionV1(StrictContract):
    arguments_schema: dict
    result_schema: dict

    @model_validator(mode="after")
    def valid(self):
        for schema in (self.arguments_schema, self.result_schema):
            validate_node_json(schema, max_bytes=8192)
            validate_schema(schema)
            if schema.get("type") != "object":
                raise CapabilityContractError(
                    "Action arguments/result require object schemas"
                )
        return self


class CapabilityContractV1(StrictContract):
    schema_version: Literal[1] = 1
    capability_id: ContractName
    contract_version: ContractVersion
    actions: dict[ContractName, CapabilityActionV1] = Field(
        default_factory=dict, max_length=32
    )
    state_schema: dict | None = None
    events: dict[ContractName, dict] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def valid(self):
        validate_node_json(self.model_dump(mode="json"), max_bytes=16384)
        for schema in [
            *self.events.values(),
            *([self.state_schema] if self.state_schema is not None else []),
        ]:
            validate_schema(schema)
            if schema.get("type") != "object":
                raise CapabilityContractError("State/event schemas require objects")
        return self

    def digest(self):
        data = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(data.encode()).hexdigest()

    def invocation(self, payload, *, require_digest=False):
        if (
            payload.get("capability_id") != self.capability_id
            or payload.get("contract_version") != self.contract_version
            or (require_digest and payload.get("contract_digest") != self.digest())
            or (
                payload.get("contract_digest") is not None
                and payload["contract_digest"] != self.digest()
            )
        ):
            raise CapabilityContractError(
                "Capability contract version/definition mismatch"
            )
        name = payload.get("action")
        action = self.actions.get(name) if isinstance(name, str) else None
        if action is None:
            raise CapabilityContractError("Action is not declared by this contract")
        arguments = payload.get("arguments", {})
        validate_node_json(arguments)
        validate_value(arguments, action.arguments_schema)
        return action


def registration_contract(capability_id, value):
    if value is None:
        return None  # Legacy unknown, never infer v1 from provider version/name.
    contract = CapabilityContractV1.model_validate(value)
    if contract.capability_id != capability_id:
        raise CapabilityContractError(
            "Registration/contract capability identity mismatch"
        )
    return contract
