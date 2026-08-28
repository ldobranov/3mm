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
    ModuleCapabilities,
    ModuleCompatibility,
    ModuleHealthCheck,
    ModuleManifestV2,
    ModuleRegistration,
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
from three_mm_protocol.compiled_extension import (
    CompiledUiEntrypointV1,
    CompiledUiExtensionV1,
)
from three_mm_protocol.capability_builder import (
    BuilderSettingV1,
    CapabilityBindingV1,
    CapabilityPlanV1,
    CapabilityPresentationV1,
    PresentationStateV1,
)
from three_mm_protocol.capability_state import (
    CapabilityStateReportV1,
    CapabilityStateSnapshotV1,
)
from three_mm_protocol.backup import (
    BACKUP_MANIFEST_VERSION,
    BackupCompatibilityV1,
    BackupEntryV1,
    BackupManifestV1,
    BackupProtectionV1,
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
    "CompiledUiEntrypointV1",
    "CompiledUiExtensionV1",
    "BuilderSettingV1",
    "CapabilityBindingV1",
    "CapabilityPlanV1",
    "CapabilityPresentationV1",
    "PresentationStateV1",
    "CapabilityStateReportV1",
    "CapabilityStateSnapshotV1",
    "BACKUP_MANIFEST_VERSION",
    "BackupCompatibilityV1",
    "BackupEntryV1",
    "BackupManifestV1",
    "BackupProtectionV1",
]
