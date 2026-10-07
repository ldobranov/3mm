"""Module manifest v2 contract shared by Core, Agent and extension tooling."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from three_mm_protocol.capability_contracts import CapabilityContractV1, registration_contract

SEMVER_PATTERN = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
MODULE_ID_PATTERN = r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$"
PUBLISHER_ID_PATTERN = r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$"
EXTENSION_API_VERSION = "1.0"

CompatibilityIssueCode = Literal[
    "runtime",
    "protocol",
    "extension_api",
    "runtime_version",
    "runtime_version_invalid",
    "architecture",
]


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


def module_compatibility_issues(
    manifest: ModuleManifestV2,
    *,
    runtime: Literal["core", "agent", "ui"] | None = None,
    runtime_version: str | None = None,
    architecture: str | None = None,
    protocol_version: str = "1.0",
    extension_api_version: str = EXTENSION_API_VERSION,
    require_runtime: bool = False,
) -> tuple[CompatibilityIssueCode, ...]:
    """Evaluate one shared compatibility contract without runtime-specific policy.

    Core uses this while cataloging packages and only requires Core compatibility
    when a package actually targets Core. Agent uses the same evaluator with
    `require_runtime=True` before installation. The returned codes are stable,
    machine-readable input for developer tooling and the AI Extension Generator.
    """

    issues: list[CompatibilityIssueCode] = []

    if runtime is not None and require_runtime and runtime not in manifest.runtimes:
        issues.append("runtime")

    if manifest.compatibility.protocol != protocol_version:
        issues.append("protocol")

    try:
        api_supported = supports_extension_api(
            extension_api_version, manifest.compatibility.extension_api
        )
    except (TypeError, ValueError):
        api_supported = False
    if not api_supported:
        issues.append("extension_api")

    if runtime in {"core", "agent"} and runtime in manifest.runtimes:
        requirement = (
            manifest.compatibility.core
            if runtime == "core"
            else manifest.compatibility.agent
        )
        if runtime_version is None:
            issues.append("runtime_version_invalid")
        else:
            try:
                runtime_supported = meets_minimum_version(runtime_version, requirement)
            except (TypeError, ValueError):
                issues.append("runtime_version_invalid")
            else:
                if not runtime_supported:
                    issues.append("runtime_version")

    if (
        architecture
        and architecture not in manifest.compatibility.architectures
        and "any" not in manifest.compatibility.architectures
    ):
        issues.append("architecture")

    return tuple(issues)
