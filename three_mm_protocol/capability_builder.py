"""Versioned capability-plan contract for deterministic extension generation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Scalar = str | int | float | bool
SETTING_KEY_PATTERN = r"^[a-z][A-Za-z0-9]{0,63}$"
CAPABILITY_ID_PATTERN = r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$"
ACTION_PATTERN = r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"


class StrictBuilderModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BuilderSettingV1(StrictBuilderModel):
    key: str = Field(pattern=SETTING_KEY_PATTERN)
    label: str = Field(min_length=1, max_length=120)
    kind: Literal[
        "text", "number", "boolean", "select", "timezone", "color",
        "device", "capability_channel",
    ]
    required: bool = False
    default: Scalar | None = None
    options: tuple[Scalar, ...] = ()

    @model_validator(mode="after")
    def validate_options(self):
        if self.kind == "select" and not self.options:
            raise ValueError("select settings require options")
        if self.kind != "select" and self.options:
            raise ValueError("options are only valid for select settings")
        return self


class CapabilityBindingV1(StrictBuilderModel):
    alias: str = Field(pattern=SETTING_KEY_PATTERN)
    capability_id: str = Field(pattern=CAPABILITY_ID_PATTERN)
    operation: Literal["read_state", "subscribe", "invoke"]
    action: str | None = Field(default=None, pattern=ACTION_PATTERN)
    device_setting: str = Field(pattern=SETTING_KEY_PATTERN)
    channel_setting: str | None = Field(default=None, pattern=SETTING_KEY_PATTERN)
    value_path: str = Field(default="value", min_length=1, max_length=160)
    permissions: tuple[str, ...] = ()
    stale_after_seconds: int = Field(default=90, ge=1, le=3600)

    @model_validator(mode="after")
    def invoke_requires_an_action(self):
        if self.operation == "invoke" and not self.action:
            raise ValueError("invoke bindings require an action")
        if self.operation != "invoke" and self.action:
            raise ValueError("actions are only valid for invoke bindings")
        return self


class PresentationStateV1(StrictBuilderModel):
    state: Literal["value", "stale", "offline", "error"] = "value"
    value: Scalar | None = None
    label: str = Field(min_length=1, max_length=120)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class CapabilityPresentationV1(StrictBuilderModel):
    kind: Literal["indicator", "metric", "text", "list", "chart", "form"]
    source_binding: str | None = Field(default=None, pattern=SETTING_KEY_PATTERN)
    states: tuple[PresentationStateV1, ...] = ()

    @model_validator(mode="after")
    def indicator_has_value_and_failure_states(self):
        if self.kind != "indicator":
            return self
        state_kinds = {item.state for item in self.states}
        values = {item.value for item in self.states if item.state == "value"}
        if not {True, False}.issubset(values):
            raise ValueError("indicator presentations require true and false value states")
        if not {"stale", "offline", "error"}.issubset(state_kinds):
            raise ValueError("indicator presentations require stale, offline and error states")
        return self


class CapabilityPlanV1(StrictBuilderModel):
    schema_version: Literal[1] = 1
    target: Literal["dashboard_widget", "application_page"]
    settings: tuple[BuilderSettingV1, ...] = ()
    bindings: tuple[CapabilityBindingV1, ...] = ()
    presentations: tuple[CapabilityPresentationV1, ...] = ()

    @model_validator(mode="after")
    def references_are_declared_and_unique(self):
        setting_by_key = {item.key: item for item in self.settings}
        if len(setting_by_key) != len(self.settings):
            raise ValueError("setting keys must be unique")
        binding_by_alias = {item.alias: item for item in self.bindings}
        if len(binding_by_alias) != len(self.bindings):
            raise ValueError("binding aliases must be unique")
        for binding in self.bindings:
            device = setting_by_key.get(binding.device_setting)
            if device is None or device.kind != "device":
                raise ValueError(f"binding {binding.alias!r} requires a device setting")
            if binding.channel_setting:
                channel = setting_by_key.get(binding.channel_setting)
                if channel is None or channel.kind != "capability_channel":
                    raise ValueError(f"binding {binding.alias!r} requires a capability-channel setting")
        for presentation in self.presentations:
            if presentation.source_binding and presentation.source_binding not in binding_by_alias:
                raise ValueError(f"presentation references unknown binding {presentation.source_binding!r}")
        return self
