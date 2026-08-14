"""Versioned declarative automation contracts shared by Core and Agent."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictAutomationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CapabilityReference(StrictAutomationModel):
    device_id: str = Field(min_length=1, max_length=64)
    capability_id: str = Field(min_length=1, max_length=160)


class CapabilityEventTrigger(CapabilityReference):
    kind: Literal["capability_event"] = "capability_event"
    event: str = Field(min_length=1, max_length=100)
    conditions: dict[str, str | int | float | bool] = Field(default_factory=dict)


class CapabilityCommandAction(CapabilityReference):
    kind: Literal["capability_command"] = "capability_command"
    action: str = Field(min_length=1, max_length=100)
    arguments: dict[str, str | int | float | bool] = Field(default_factory=dict)


class AutomationDefinitionV1(StrictAutomationModel):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    execution: Literal["local", "core"] = "local"
    enabled: bool = True
    trigger: CapabilityEventTrigger
    actions: tuple[CapabilityCommandAction, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def local_execution_stays_on_one_device(self):
        if self.execution == "local":
            targets = {self.trigger.device_id, *(action.device_id for action in self.actions)}
            if len(targets) != 1:
                raise ValueError("local automations must reference exactly one device")
        return self


class CapabilityContextEntry(StrictAutomationModel):
    device_id: str
    device_name: str
    device_role: str
    capability_id: str
    module_id: str
    module_version: str
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class AutomationCapabilityContextV1(StrictAutomationModel):
    context_version: Literal[1] = 1
    capabilities: tuple[CapabilityContextEntry, ...] = ()

    def capability_ids_for(self, device_id: str) -> set[str]:
        return {
            item.capability_id
            for item in self.capabilities
            if item.device_id == device_id
        }


class AutomationValidationIssue(StrictAutomationModel):
    path: str
    code: Literal["device.unavailable", "capability.unavailable"]
    message: str


def validate_automation_capabilities(
    automation: AutomationDefinitionV1,
    context: AutomationCapabilityContextV1,
) -> tuple[AutomationValidationIssue, ...]:
    """Validate references without executing or mutating an automation."""

    device_ids = {item.device_id for item in context.capabilities}
    references: list[tuple[str, CapabilityReference]] = [("trigger", automation.trigger)]
    references.extend((f"actions.{index}", action) for index, action in enumerate(automation.actions))
    issues: list[AutomationValidationIssue] = []

    for path, reference in references:
        if reference.device_id not in device_ids:
            issues.append(AutomationValidationIssue(
                path=path,
                code="device.unavailable",
                message=f"Device {reference.device_id!r} is not available in the AI context",
            ))
        elif reference.capability_id not in context.capability_ids_for(reference.device_id):
            issues.append(AutomationValidationIssue(
                path=path,
                code="capability.unavailable",
                message=(
                    f"Capability {reference.capability_id!r} is not enabled on "
                    f"device {reference.device_id!r}"
                ),
            ))
        else:
            entry = next(item for item in context.capabilities if (
                item.device_id == reference.device_id and item.capability_id == reference.capability_id
            ))
            metadata = entry.metadata
            expected_role = "trigger" if path == "trigger" else "action"
            declared_role = metadata.get("automation_role")
            operation = automation.trigger.event if path == "trigger" else reference.action
            allowed_key = "automation_events" if path == "trigger" else "automation_actions"
            allowed = {item.strip() for item in str(metadata.get(allowed_key, "")).split(",") if item.strip()}
            values = automation.trigger.conditions if path == "trigger" else reference.arguments
            required = {item.strip() for item in str(metadata.get("automation_required_fields", "")).split(",") if item.strip()}
            channels = {item.strip() for item in str(metadata.get("automation_channels", "")).split(",") if item.strip()}
            reason = None
            if declared_role and declared_role != expected_role:
                reason = f"Capability {reference.capability_id!r} cannot be used as an automation {expected_role}"
            elif allowed and operation not in allowed:
                reason = f"Operation {operation!r} is not supported by capability {reference.capability_id!r}"
            elif required - values.keys():
                reason = f"Capability {reference.capability_id!r} requires fields {sorted(required)}"
            elif channels and values.get("channel") not in channels:
                reason = f"Channel {values.get('channel')!r} is not supported by capability {reference.capability_id!r}"
            elif metadata.get("automation_value_type") == "boolean" and not isinstance(values.get("value"), bool):
                reason = f"Capability {reference.capability_id!r} requires a Boolean value"
            if reason:
                issues.append(AutomationValidationIssue(
                    path=path,
                    code="capability.unavailable",
                    message=reason,
                ))

    return tuple(issues)
