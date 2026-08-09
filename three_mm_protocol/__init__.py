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
]
