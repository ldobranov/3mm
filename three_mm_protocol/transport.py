"""Logical Node transport port. No URLs, HTTP responses or platform choices.

Delivery acknowledgement is not execution success. A transport failure may
mean a lost response after commit; journals/outboxes retain their existing
idempotency semantics. Adapters must authenticate every logical operation.
"""

from typing import Protocol

from three_mm_protocol import (
    AgentCommand,
    AgentCommandResult,
    AgentHeartbeat,
    AgentInventory,
    AgentReportedState,
    CapabilityProviderReportV1,
    CapabilityStateReportV1,
    CoreNodeProtocolV1,
    DeviceDesiredState,
    DeviceEventV1,
    DeviceInventoryV2,
    DeviceRuntimeFeaturesReportV1,
    DeviceRuntimeFeaturesSnapshotV1,
)
from three_mm_protocol.fleet_pairing import (
    NodeEnrollmentRequest,
    NodeEnrollmentResponse,
)
from three_mm_protocol.node_updates import NodeUpdateOperation
from three_mm_protocol.capability_availability import CapabilityAvailabilityReportV1

NodeReport = (
    AgentHeartbeat
    | AgentInventory
    | DeviceInventoryV2
    | AgentCommandResult
    | AgentReportedState
    | CapabilityStateReportV1
    | CapabilityProviderReportV1
    | DeviceEventV1
    | NodeUpdateOperation
    | CapabilityAvailabilityReportV1
)


class DeviceTransportError(RuntimeError):
    """Delivery was rejected or could not be confirmed; do not infer execution."""


class DeviceProtocolError(ValueError):
    """Logical rejection; transport boundaries translate kind, never vice versa."""

    def __init__(self, detail, *, kind="conflict"):
        self.detail = detail
        self.kind = kind
        super().__init__(str(detail))


class DeviceTransport(Protocol):
    device_id: str

    def enroll(self, request: NodeEnrollmentRequest) -> NodeEnrollmentResponse: ...
    def publish(self, report: NodeReport) -> None: ...
    def receive_command(self, *, timeout_seconds: float = 0) -> AgentCommand | None: ...
    def desired_state(self) -> DeviceDesiredState: ...
    def protocol(self) -> CoreNodeProtocolV1 | None: ...
    def report_features(
        self, report: DeviceRuntimeFeaturesReportV1
    ) -> DeviceRuntimeFeaturesSnapshotV1: ...
    def authorize_execution(self, command_id: str) -> dict: ...


class DevicePlatformTransport(DeviceTransport, Protocol):
    """Optional C12/C13 contract. Existing transports need not advertise it."""

    def platform(self): ...
    def report_lifecycle(self, report): ...
