"""Validated HTTP boundary models for setup."""

from __future__ import annotations

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr

from three_mm_protocol import AgentRole
from three_mm_provisioning import ProvisioningState


class SetupApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SetupConfiguration(SetupApiModel):
    network_name: str = Field(min_length=1, max_length=32)
    passphrase: SecretStr = Field(min_length=8, max_length=63)
    locale: str = Field(min_length=2, max_length=35)
    device_name: str = Field(
        min_length=1,
        max_length=63,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$",
    )
    administrator_name: str = Field(min_length=1, max_length=64)
    role: AgentRole
    hub_endpoint: AnyHttpUrl | None = None


class SetupStatus(SetupApiModel):
    state: ProvisioningState
    setup_active: bool
    role: AgentRole | None


class SetupOutcome(SetupApiModel):
    state: ProvisioningState
    role: AgentRole | None
    recovery_required: bool
    error_code: str | None = None


class WifiNetworkOption(SetupApiModel):
    network_name: str
    signal: int = Field(ge=0, le=100)
    secured: bool


class WifiNetworkList(SetupApiModel):
    items: list[WifiNetworkOption]


class SetupTheme(SetupApiModel):
    mode: str
    body_bg: str
    card_bg: str
    panel_bg: str
    text_primary: str
    text_secondary: str
    border: str
    primary: str
    header_bg: str
    header_text: str
    border_radius: int = Field(ge=0, le=50)
