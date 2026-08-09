"""Versioned contracts shared by 3mm Core and Agent."""

from three_mm_protocol.models import (
    PROTOCOL_VERSION,
    AgentHealth,
    AgentHeartbeat,
    AgentCommand,
    AgentCommandResult,
    AgentHello,
    AgentInventory,
    AgentRole,
)

__all__ = [
    "PROTOCOL_VERSION",
    "AgentHealth",
    "AgentHeartbeat",
    "AgentCommand",
    "AgentCommandResult",
    "AgentHello",
    "AgentInventory",
    "AgentRole",
]
