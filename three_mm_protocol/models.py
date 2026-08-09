"""Protocol v1 models shared by every 3mm runtime."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION: Literal["1.0"] = "1.0"
DeviceId = str


class ProtocolModel(BaseModel):
    """Strict base model used at every protocol boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentRole(str, Enum):
    STANDALONE = "standalone"
    HUB = "hub"
    NODE = "node"


class AgentHello(ProtocolModel):
    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    agent_version: str
    device_id: DeviceId = Field(pattern=r"^dev_[0-9a-f]{32}$")
    display_name: str = Field(min_length=1, max_length=100)
    role: AgentRole
    started_at: datetime
    capabilities: tuple[str, ...] = ()


class AgentHealth(ProtocolModel):
    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    agent_version: str
    device_id: DeviceId = Field(pattern=r"^dev_[0-9a-f]{32}$")
    status: Literal["ok"] = "ok"
    uptime_seconds: float = Field(ge=0)
    checked_at: datetime


class AgentInventory(ProtocolModel):
    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    device_id: DeviceId = Field(pattern=r"^dev_[0-9a-f]{32}$")
    collected_at: datetime
    hostname: str
    model: str | None = None
    operating_system: str
    operating_system_version: str
    kernel_version: str
    architecture: str
    python_version: str
    logical_cpu_count: int | None = Field(default=None, ge=1)
    memory_total_bytes: int | None = Field(default=None, ge=1)
    root_total_bytes: int = Field(ge=1)
    root_free_bytes: int = Field(ge=0)
    network_manager_active: bool | None = None
    hardware_driver: str = Field(default="linux", min_length=1)
    capabilities: tuple[str, ...] = ()


class AgentHeartbeat(ProtocolModel):
    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    device_id: DeviceId = Field(pattern=r"^dev_[0-9a-f]{32}$")
    sent_at: datetime
    uptime_seconds: float = Field(ge=0)
    status: Literal["ready", "degraded"] = "ready"
