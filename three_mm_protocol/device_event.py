"""Generic device event envelope on the existing protocol 1.0 transport.

Event-specific payload contracts are separate. This extraction deliberately
preserves the old envelope, including legacy naive datetime acceptance; new
clients must send aware timestamps under the Node conformance requirements.
"""

from datetime import datetime

from pydantic import Field, model_validator
from three_mm_protocol.node_security import bounded_node_message

from three_mm_protocol.models import ProtocolModel


class DeviceEventV1(ProtocolModel):
    _bounded = model_validator(mode="after")(bounded_node_message)
    event_id: str = Field(pattern=r"^evt_[0-9a-f]{32}$")
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    event_type: str = Field(min_length=1, max_length=120)
    payload: dict = Field(default_factory=dict)
    occurred_at: datetime
