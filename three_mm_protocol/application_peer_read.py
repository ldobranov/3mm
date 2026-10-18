"""Exact local peer metadata read, not enrollment, proof or remote access."""

from typing import Literal

from pydantic import Field, field_validator

from three_mm_protocol.installation_peer import PeerModel, PeerOutboundStatusV1
from three_mm_protocol.installation_peer_v2 import PeerOutboundStatusV2, parse_peer


class ApplicationPeerReadV1(PeerModel):
    read_version: Literal[1] = 1
    binding_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$", max_length=96)
    peer: PeerOutboundStatusV2 | PeerOutboundStatusV1

    @field_validator("read_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Peer read version must be an integer")
        return value

    @field_validator("peer", mode="before")
    @classmethod
    def exact_wire_peer(cls, value):
        return parse_peer(PeerOutboundStatusV1, value)
