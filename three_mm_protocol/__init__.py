"""Versioned contracts shared by 3mm Core and Agent."""

from three_mm_protocol.models import (
    PROTOCOL_VERSION,
    AgentHealth,
    AgentHeartbeat,
    AgentCommand,
    AgentCommandResult,
    AgentReportedState,
    DeviceDesiredState,
    AgentHello,
    AgentInventory,
    AgentRole,
)
from three_mm_protocol.module_manifest import (
    ModuleCapabilities, ModuleCompatibility, ModuleHealthCheck,
    ModuleManifestV2, ModuleRegistration,
    meets_minimum_version,
)
from three_mm_protocol.automation import (
    AutomationCapabilityContextV1,
    AutomationDefinitionV1,
    AutomationValidationIssue,
    CapabilityCommandAction,
    CapabilityContextEntry,
    CapabilityEventTrigger,
    validate_automation_capabilities,
)
from three_mm_protocol.runtime_extension import (
    LocalizedTextV1,
    RuntimeEntityV1,
    RuntimeExtensionV1,
    RuntimeFieldV1,
    RuntimeNavigationItemV1,
    RuntimePageV1,
)

__all__ = [
    "PROTOCOL_VERSION",
    "AgentHealth",
    "AgentHeartbeat",
    "AgentCommand",
    "AgentCommandResult",
    "AgentReportedState",
    "DeviceDesiredState",
    "AgentHello",
    "AgentInventory",
    "AgentRole",
    "ModuleCapabilities",
    "ModuleCompatibility",
    "ModuleHealthCheck",
    "ModuleManifestV2",
    "ModuleRegistration",
    "meets_minimum_version",
    "AutomationCapabilityContextV1",
    "AutomationDefinitionV1",
    "AutomationValidationIssue",
    "CapabilityCommandAction",
    "CapabilityContextEntry",
    "CapabilityEventTrigger",
    "validate_automation_capabilities",
    "LocalizedTextV1",
    "RuntimeEntityV1",
    "RuntimeExtensionV1",
    "RuntimeFieldV1",
    "RuntimeNavigationItemV1",
    "RuntimePageV1",
]
