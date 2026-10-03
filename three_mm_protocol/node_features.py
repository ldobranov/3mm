"""Runtime support is not an application capability or an authorization grant."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StrictInt, model_validator

from three_mm_protocol.models import ProtocolModel

FeatureId = Annotated[
    str, Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_.-]*$")
]
FeatureRevision = Annotated[StrictInt, Field(ge=0, le=2_147_483_646)]
MANDATORY_NODE_FEATURES = frozenset(
    {
        "inventory",
        "heartbeat",
        "commands",
        "events",
        "capability_invocation",
        "capability_state",
        "desired_reported_state",
    }
)
# Generic transport contracts, not hardware/platform names. Firmware OTA may
# advertise a different feature; it does not implement Linux release updates.
FEATURE_COMMANDS = {
    "capability_invocation": frozenset({"capability.invoke"}),
    "module_lifecycle": frozenset({"module.install", "module.disable"}),
    "local_automations": frozenset({"automation.apply", "automation.remove"}),
    "gpio_configuration": frozenset({"agent.gpio.configure"}),
    "inventory_refresh": frozenset({"agent.refresh_inventory"}),
    "release_update_prepare": frozenset({"agent.update.prepare"}),
    "release_update_apply": frozenset({"agent.update.apply"}),
    "application_execution_permits": frozenset({"application.capability.invoke"}),
}


class DeviceRuntimeFeaturesV1(ProtocolModel):
    schema_version: Literal[1] = 1
    protocol_version: Literal["1.0"] = "1.0"
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    runtime_name: str = Field(min_length=1, max_length=100)
    runtime_version: str = Field(min_length=1, max_length=64)
    features: tuple[FeatureId, ...] = Field(max_length=64)
    command_types: tuple[FeatureId, ...] = Field(max_length=64)

    @model_validator(mode="after")
    def consistent_support(self):
        features, commands = set(self.features), set(self.command_types)
        if len(features) != len(self.features) or len(commands) != len(
            self.command_types
        ):
            raise ValueError("Duplicate runtime feature or command type")
        if not MANDATORY_NODE_FEATURES <= features:
            raise ValueError("Mandatory node features are missing")
        for feature, required in FEATURE_COMMANDS.items():
            if (feature in features) != (required <= commands):
                raise ValueError(f"Feature/command support is inconsistent: {feature}")
            if feature not in features and required & commands:
                raise ValueError(f"Partial command support requires feature: {feature}")
        if len(self.model_dump_json().encode()) > 16384:
            raise ValueError("Runtime feature report is too large")
        return self


class DeviceRuntimeFeaturesReportV1(DeviceRuntimeFeaturesV1):
    expected_revision: FeatureRevision


class DeviceRuntimeFeaturesSnapshotV1(ProtocolModel):
    schema_version: Literal[1] = 1
    device_id: str
    source: Literal["advertised", "legacy_unadvertised"]
    revision: FeatureRevision
    declaration: DeviceRuntimeFeaturesV1 | None = None
    received_at: datetime | None = None


class CoreNodeProtocolV1(ProtocolModel):
    schema_version: Literal[1] = 1
    protocol_version: Literal["1.0"] = "1.0"
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    inventory_schema_versions: tuple[int, ...] = (1, 2)
    runtime_feature_schema_versions: tuple[int, ...] = (1,)
    capability_registry_versions: tuple[int, ...] = (1, 2)
    capability_provider_report_versions: tuple[int, ...] = (1,)
    runtime_features_revision: FeatureRevision = 0
