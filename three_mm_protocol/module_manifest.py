"""Module manifest v2 contract shared by Core and Agent."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, model_serializer
from three_mm_protocol.capability_contracts import CapabilityContractV1, registration_contract

SEMVER_PATTERN = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
MODULE_ID_PATTERN = r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$"
PUBLISHER_ID_PATTERN = r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$"
EXTENSION_API_VERSION = "1.0"

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

class ModulePublisher(StrictModel):
    """Stable publisher identity metadata for distribution and registry layers."""

    id: str = Field(pattern=PUBLISHER_ID_PATTERN, max_length=120)
    name: str = Field(min_length=1, max_length=120)

class ModuleCompatibility(StrictModel):
    protocol: str = Field(pattern=r"^\d+\.\d+$")
    extension_api: str = Field(default=EXTENSION_API_VERSION, pattern=r"^\d+\.\d+$")
    agent: str = Field(default=">=0.1.0", pattern=r"^>=\d+\.\d+\.\d+$")
    core: str = Field(default=">=0.1.0", pattern=r"^>=\d+\.\d+\.\d+$")
    architectures: tuple[str, ...] = Field(min_length=1)

class ModuleCapabilities(StrictModel):
    provides: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()

class ModuleHealthCheck(StrictModel):
    type: Literal["file_exists", "json_file"]
    path: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def safe_relative_path(self):
        parts = self.path.replace("\\", "/").split("/")
        if self.path.startswith(("/", "\\")) or ".." in parts:
            raise ValueError("health check path must stay inside module data")
        return self

def supports_extension_api(supported: str, requested: str) -> bool:
    """Accept the same API major and any supported minor at or above the request."""
    supported_major, supported_minor = (int(part) for part in supported.split("."))
    requested_major, requested_minor = (int(part) for part in requested.split("."))
    return supported_major == requested_major and supported_minor >= requested_minor

def meets_minimum_version(current: str, requirement: str) -> bool:
    """Evaluate the deliberately small manifest-v2 `>=x.y.z` contract."""
    required = requirement.removeprefix(">=")
    def parts(value: str) -> tuple[int, int, int]:
        clean = value.split("-", 1)[0].split("+", 1)[0]
        major, minor, patch = clean.split(".")
        return int(major), int(minor), int(patch)
    return parts(current) >= parts(required)

class ModuleRegistration(StrictModel):
    kind: Literal["navigation", "service", "widget", "capability"]
    registration_id: str = Field(pattern=MODULE_ID_PATTERN)
    metadata: dict[str, str | bool | int] = Field(default_factory=dict)
    contract: CapabilityContractV1 | None = None

    @model_validator(mode="after")
    def valid_contract(self):
        if self.contract is not None and self.kind != "capability":
            raise ValueError("Only capabilities declare a capability contract")
        registration_contract(self.registration_id, self.contract)
        return self

    @model_serializer(mode="wrap")
    def wire(self, handler):
        data = handler(self)
        if self.contract is None:
            data.pop("contract", None)
        return data

class ModuleManifestV2(StrictModel):
    manifest_version: Literal[2]
    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(pattern=SEMVER_PATTERN)
    description: str = Field(default="", max_length=1000)
    publisher: ModulePublisher | None = None
    runtimes: tuple[Literal["core", "agent", "ui"], ...] = Field(min_length=1)
    entrypoints: dict[Literal["core", "agent", "ui"], str] = Field(default_factory=dict)
    compatibility: ModuleCompatibility
    capabilities: ModuleCapabilities = Field(default_factory=ModuleCapabilities)
    permissions: tuple[str, ...] = ()
    dependencies: dict[str, str] = Field(default_factory=dict)
    conflicts: tuple[str, ...] = ()
    configuration_schema: dict = Field(default_factory=dict)
    configuration_defaults: dict = Field(default_factory=dict)
    health_check: ModuleHealthCheck
    registrations: tuple[ModuleRegistration, ...] = ()

    @model_validator(mode="after")
    def validate_contract(self):
        if set(self.entrypoints) - set(self.runtimes):
            raise ValueError("entrypoints may only target declared runtimes")
        if len(set(self.runtimes)) != len(self.runtimes):
            raise ValueError("runtimes must be unique")
        if len(set(self.permissions)) != len(self.permissions):
            raise ValueError("permissions must be unique")
        ids = [item.registration_id for item in self.registrations]
        if len(set(ids)) != len(ids):
            raise ValueError("registration IDs must be unique")
        return self
