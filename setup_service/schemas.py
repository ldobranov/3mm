"""Validated HTTP boundary models for setup."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from three_mm_protocol import AgentRole
from three_mm_provisioning import ProvisioningState
from three_mm_provisioning.models import NetworkMode


class SetupApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SetupConfiguration(SetupApiModel):
    network_mode: NetworkMode = NetworkMode.PRESERVE
    network_interface: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,14}$")
    network_name: str | None = Field(default=None, min_length=1, max_length=32)
    passphrase: SecretStr | None = Field(default=None, min_length=8, max_length=63)
    locale: str = Field(min_length=2, max_length=35)
    device_name: str = Field(
        min_length=1,
        max_length=63,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$",
    )
    administrator_name: str = Field(min_length=1, max_length=64)
    role: AgentRole
    hub_endpoint: str | None = Field(default=None, max_length=2048)
    administrator_email: str | None = Field(default=None, max_length=254)
    administrator_password: SecretStr | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_choices(self):
        if self.network_mode is NetworkMode.WIFI:
            if not self.network_interface or not self.network_name or not self.passphrase:
                raise ValueError("wifi_settings_required")
            if len(self.network_name.encode()) > 32 or any(c in self.passphrase.get_secret_value() for c in "\r\n\0"):
                raise ValueError("wifi_settings_invalid")
        elif any(value is not None for value in (self.network_interface, self.network_name, self.passphrase)):
            raise ValueError("host_network_accepts_no_wifi_settings")
        if self.network_mode is NetworkMode.LOCAL and self.role is not AgentRole.STANDALONE:
            raise ValueError("local_mode_requires_standalone")
        if self.role is AgentRole.NODE:
            from agent.hub_connection import normalize_hub_endpoint
            if self.hub_endpoint is not None:
                self.hub_endpoint = normalize_hub_endpoint(self.hub_endpoint)
            if self.administrator_email is not None or self.administrator_password is not None:
                raise ValueError("node_has_no_core_administrator")
        elif self.hub_endpoint is not None:
            raise ValueError("hub_endpoint_is_node_only")
        return self


class SetupStatus(SetupApiModel):
    state: ProvisioningState
    setup_active: bool
    role: AgentRole | None


class SetupPrefill(SetupApiModel):
    locale: str | None = None
    device_name: str | None = None
    administrator_name: str | None = None
    role: AgentRole | None = None
    hub_endpoint: str | None = None
    network_mode: NetworkMode = NetworkMode.PRESERVE
    network_interface: str | None = None


class SetupOutcome(SetupApiModel):
    state: ProvisioningState
    role: AgentRole | None
    recovery_required: bool
    error_code: str | None = None
    enrollment: str | None = None


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
