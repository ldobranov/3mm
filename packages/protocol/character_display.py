"""Bounded character-display wire contract, independent of panel geometry.

Core treats provider geometry as contract data, never a catalog of LCD sizes.
Hardware drivers validate their own addressing limits before activation/I/O.
"""
from __future__ import annotations
import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from packages.protocol.capability_contracts import CapabilityContractError, CapabilityContractV1, validate_value

DISPLAY_CAPABILITY = "display.character"
DISPLAY_ENTRYPOINT = "builtin:display.character.v1"
DISPLAY_CONTRACT_VERSION = "2.0"
MAX_COLUMNS, MAX_ROWS = 80, 4  # Wire/resource budgets, not supported-panel lists.


def _object(properties: dict) -> dict:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def frame_arguments_schema() -> dict:
    """Identical for all profiles; exact profile consent is pinned by M20."""
    return _object({
        "display_id": {"type": "string", "maxLength": 64},
        "profile_sha256": {"type": "string", "minLength": 64, "maxLength": 64},
        "text": {"type": "string", "maxLength": 512},
        "backlight": {"type": "boolean"},
    })


class CharacterDisplayProfileV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[2] = 2
    display_id: str = Field(default="display.main", pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    driver: str = Field(default="mock", pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    controller: str = Field(default="hd44780", pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    pin_map: str = Field(default="rs0_rw1_e2_bl3_d4_7", max_length=64)
    backlight_active_high: bool = Field(default=True, strict=True)
    bus: int = Field(default=1, ge=0, le=255, strict=True)
    address: int = Field(default=0x27, ge=0x08, le=0x77, strict=True)
    columns: int = Field(default=20, ge=1, le=MAX_COLUMNS, strict=True)
    rows: int = Field(default=2, ge=1, le=MAX_ROWS, strict=True)

    def digest(self) -> str:
        raw = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("ascii")).hexdigest()

    def contract(self) -> CapabilityContractV1:
        # State-schema singleton declarations advertise the exact immutable
        # geometry. Its digest changes even though frame input stays stable.
        state = _object({
            **frame_arguments_schema()["properties"],
            "display_id": {"type": "string", "maxLength": 64, "enum": [self.display_id]},
            "profile_sha256": {"type": "string", "maxLength": 64, "enum": [self.digest()]},
            "columns": {"type": "integer", "minimum": 1, "maximum": MAX_COLUMNS, "enum": [self.columns]},
            "rows": {"type": "integer", "minimum": 1, "maximum": MAX_ROWS, "enum": [self.rows]},
            "has_frame": {"type": "boolean"}, "last_write_at": {"type": "string", "maxLength": 40},
            "simulated": {"type": "boolean", "enum": [self.driver == "mock"]},
        })
        return CapabilityContractV1.model_validate({
            "schema_version": 1, "capability_id": DISPLAY_CAPABILITY,
            "contract_version": DISPLAY_CONTRACT_VERSION, "state_schema": state,
            "actions": {"write_frame": {"arguments_schema": frame_arguments_schema(),
                "result_schema": _object({**state["properties"],
                    "has_frame": {"type": "boolean", "enum": [True]}})}},
        })

    def frame(self, arguments: dict) -> tuple[list[str], bool]:
        validate_value(arguments, frame_arguments_schema())
        if arguments['display_id'] != self.display_id or arguments['profile_sha256'] != self.digest():
            raise CapabilityContractError("Display profile changed; review the selected provider")
        lines = arguments['text'].split('\n')
        if len(lines) != self.rows or any(len(line) > self.columns for line in lines):
            raise CapabilityContractError("Display frame does not fit the approved geometry")
        if any(any(not 0x20 <= ord(char) <= 0x7E for char in line) for line in lines):
            raise CapabilityContractError("Display lines require printable ASCII")
        return [line.ljust(self.columns) for line in lines], arguments['backlight']
