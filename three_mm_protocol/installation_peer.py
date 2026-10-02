"""Core-owned installation peer v1: no user/Agent tokens or reverse commands."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictBool,
    StrictStr,
    field_validator,
    model_validator,
)

from three_mm_protocol.installation_identity import (
    InstallationIdentityV1,
    InstallationProofRequestV1,
    InstallationProofV1,
)
from three_mm_protocol.module_manifest import MODULE_ID_PATTERN

PEER_PREFIX = "/api/v1/installation-peers/v1"
PEER_ID_PATTERN = r"^peer_[0-9a-f]{32}$"
PEER_SCOPE = "installation.status.report"
PEER_MAX_BYTES = 128 * 1024
PROJECTION_MAX_BYTES = 64 * 1024
PEER_CREDENTIAL_DOMAIN = b"3mm.installation.peer.credential.v1\n"
PEER_REQUEST_DOMAIN = b"3mm.installation.peer.request.v1\n"
PEER_START_DOMAIN = b"3mm.installation.peer.start.v1\n"
SummaryField = Literal["core_version", "protocol_version", "sdk_version"]
NodeField = Literal[
    "display_name",
    "role",
    "protocol_version",
    "agent_version",
    "online",
    "last_seen_at",
    "architecture",
    "memory_total_bytes",
    "root_free_bytes",
]


class PeerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("*", mode="before")
    @classmethod
    def strict_contract_numbers(cls, value, info):
        if (
            info.field_name
            in {
                "peer_version",
                "credential_version",
                "projection_version",
                "consent_version",
            }
            and type(value) is not int
        ):
            raise ValueError("Contract versions must be integers")
        return value

    @field_validator("*", mode="after")
    @classmethod
    def normalize_time(cls, value):
        return value.astimezone(UTC) if isinstance(value, datetime) else value


class ProjectionConsentV1(PeerModel):
    consent_version: Literal[1] = 1
    summary_fields: tuple[SummaryField, ...] = Field(default=(), max_length=3)
    node_ids: tuple[str, ...] = Field(default=(), max_length=64)
    node_fields: tuple[NodeField, ...] = Field(default=(), max_length=9)

    @model_validator(mode="after")
    def exact_selection(self):
        import re

        for values in (self.summary_fields, self.node_ids, self.node_fields):
            if len(values) != len(set(values)):
                raise ValueError("Consent selections must be unique")
        if any(not re.fullmatch(r"dev_[0-9a-f]{32}", item) for item in self.node_ids):
            raise ValueError("Consent device identity is invalid")
        if bool(self.node_ids) != bool(self.node_fields):
            raise ValueError("Selected Nodes require an explicit field selection")
        return self


class ProjectionValueV1(PeerModel):
    status: Literal["known", "unknown"]
    value: StrictStr | StrictBool | StrictInt | None = None
    source: (
        Literal[
            "core.runtime",
            "device.registry",
            "device.heartbeat",
            "device.inventory",
            "device.reported",
        ]
        | None
    ) = None
    observed_at: AwareDatetime | None = None
    received_at: AwareDatetime | None = None
    revision: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def bounded_value(self):
        if isinstance(self.value, str) and len(self.value) > 255:
            raise ValueError("Projection string exceeds its limit")
        if (self.status == "unknown") != (self.value is None):
            raise ValueError("Unknown values must be null; known values must not")
        return self


class ProjectedNodeV1(PeerModel):
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    fields: dict[NodeField, ProjectionValueV1] = Field(max_length=9)


class InstallationProjectionV1(PeerModel):
    projection_version: Literal[1] = 1
    installation_id: str = Field(pattern=r"^inst_[0-9a-f]{32}$")
    consent_revision: StrictInt = Field(ge=1)
    generated_at: AwareDatetime
    summary: dict[SummaryField, ProjectionValueV1] = Field(max_length=3)
    nodes: tuple[ProjectedNodeV1, ...] = Field(max_length=64)

    @model_validator(mode="after")
    def bounded_result(self):
        if len({item.device_id for item in self.nodes}) != len(self.nodes):
            raise ValueError("Projected device IDs must be unique")
        if len(canonical_json(self.model_dump(mode="json"))) > PROJECTION_MAX_BYTES:
            raise ValueError("Projection exceeds its byte limit")
        return self


class PeerEnrollmentStartV1(PeerModel):
    peer_version: Literal[1] = 1
    request_id: str = Field(pattern=PEER_ID_PATTERN)
    target_module_id: str = Field(pattern=MODULE_ID_PATTERN, max_length=160)
    sender: InstallationIdentityV1
    receiver: InstallationIdentityV1
    scopes: tuple[Literal["installation.status.report"], ...] = (PEER_SCOPE,)
    receiver_challenge: InstallationProofRequestV1
    signature: str = Field(min_length=88, max_length=88)
    _signature = field_validator("signature")(
        InstallationProofV1.canonical_signature.__func__
    )

    @model_validator(mode="after")
    def exact_scope(self):
        if self.scopes != (PEER_SCOPE,):
            raise ValueError("Exactly the reporting scope is supported")
        return self


def enrollment_resource(
    request_id: str, module_id: str, scopes: tuple[str, ...]
) -> str:
    digest = hashlib.sha256(
        canonical_json({"module_id": module_id, "scopes": list(scopes)})
    ).hexdigest()
    return f"peer.enroll:{request_id}:{digest}"


class PeerEnrollmentChallengeV1(PeerModel):
    peer_version: Literal[1] = 1
    binding_id: str = Field(pattern=PEER_ID_PATTERN)
    receiver_proof: InstallationProofV1
    sender_challenge: InstallationProofRequestV1


class PeerEnrollmentCompleteV1(PeerModel):
    peer_version: Literal[1] = 1
    binding_id: str = Field(pattern=PEER_ID_PATTERN)
    sender_proof: InstallationProofV1


class PeerCredentialClaimsV1(PeerModel):
    credential_version: Literal[1] = 1
    binding_id: str = Field(pattern=PEER_ID_PATTERN)
    issuer: InstallationIdentityV1
    subject: InstallationIdentityV1
    origin: str
    target_module_id: str = Field(pattern=MODULE_ID_PATTERN, max_length=160)
    scopes: tuple[Literal["installation.status.report"], ...] = (PEER_SCOPE,)
    generation: StrictInt = Field(ge=1)
    issued_at: AwareDatetime
    expires_at: AwareDatetime

    _origin = field_validator("origin")(
        InstallationProofRequestV1.canonical_origin.__func__
    )

    @model_validator(mode="after")
    def limited_credential(self):
        if (
            self.scopes != (PEER_SCOPE,)
            or not 0 < (self.expires_at - self.issued_at).total_seconds() <= 86400
        ):
            raise ValueError("Peer credential scope or lifetime is invalid")
        if self.issuer.installation_id == self.subject.installation_id:
            raise ValueError("An installation cannot enroll itself")
        return self


class PeerCredentialV1(PeerModel):
    claims: PeerCredentialClaimsV1
    signature: str = Field(min_length=88, max_length=88)
    _signature = field_validator("signature")(
        InstallationProofV1.canonical_signature.__func__
    )


class PeerEnrollmentResultV1(PeerModel):
    peer_version: Literal[1] = 1
    binding_id: str = Field(pattern=PEER_ID_PATTERN)
    state: Literal["pending", "active"]
    generation: StrictInt = Field(ge=1)
    credential: PeerCredentialV1 | None = None

    @model_validator(mode="after")
    def active_has_credential(self):
        if (self.state == "active") != (self.credential is not None):
            raise ValueError("Active peers require a credential")
        if self.credential and (
            self.credential.claims.binding_id != self.binding_id
            or self.credential.claims.generation != self.generation
        ):
            raise ValueError("Enrollment credential does not match its binding")
        return self


class PeerOutboundStatusV1(PeerModel):
    link_id: str = Field(pattern=PEER_ID_PATTERN)
    state: Literal["new", "pending", "active", "revoked"]
    consent_revision: StrictInt = Field(ge=1)
    consent: ProjectionConsentV1
    origin: str
    receiver_identity: InstallationIdentityV1
    target_module_id: str = Field(pattern=MODULE_ID_PATTERN, max_length=160)
    remote_binding_id: str | None = Field(default=None, pattern=PEER_ID_PATTERN)
    credential_expires_at: AwareDatetime | None = None
    _origin = field_validator("origin")(
        InstallationProofRequestV1.canonical_origin.__func__
    )


class PeerRequestV1(PeerModel):
    peer_version: Literal[1] = 1
    credential: PeerCredentialV1
    method: Literal["POST"] = "POST"
    path: str = Field(
        pattern=r"^/api/v1/installation-peers/v1/[a-z0-9_./-]+$", max_length=255
    )
    nonce: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    created_at: AwareDatetime
    expires_at: AwareDatetime
    payload: dict
    signature: str = Field(min_length=88, max_length=88)
    _signature = field_validator("signature")(
        InstallationProofV1.canonical_signature.__func__
    )
    _nonce = field_validator("nonce")(
        InstallationProofRequestV1.canonical_challenge.__func__
    )

    @model_validator(mode="after")
    def bounded_request(self):
        if not 0 < (self.expires_at - self.created_at).total_seconds() <= 120:
            raise ValueError("Peer request lifetime is invalid")
        if len(canonical_json(self.model_dump(mode="json"))) > PEER_MAX_BYTES:
            raise ValueError("Peer request is too large")
        return self


class PeerReportV1(PeerModel):
    report_id: str = Field(pattern=r"^report_[0-9a-f]{32}$")
    projection: InstallationProjectionV1


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def credential_bytes(claims: PeerCredentialClaimsV1) -> bytes:
    return PEER_CREDENTIAL_DOMAIN + canonical_json(claims.model_dump(mode="json"))


def enrollment_start_bytes(start: PeerEnrollmentStartV1) -> bytes:
    return PEER_START_DOMAIN + canonical_json(
        start.model_dump(mode="json", exclude={"signature"})
    )


def request_bytes(request: PeerRequestV1) -> bytes:
    return PEER_REQUEST_DOMAIN + canonical_json(
        request.model_dump(mode="json", exclude={"signature"})
    )


def verify_signature(
    identity: InstallationIdentityV1, signature: str, message: bytes
) -> None:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(
            base64.b64decode(identity.public_key)
        ).verify(base64.b64decode(signature, validate=True), message)
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("Peer signature is invalid") from exc


def verify_peer_credential(
    credential: PeerCredentialV1,
    *,
    issuer: InstallationIdentityV1,
    subject: InstallationIdentityV1,
    origin: str,
    module_id: str,
    now: datetime,
) -> None:
    claims = credential.claims
    if (
        claims.issuer != issuer
        or claims.subject != subject
        or claims.origin != origin
        or claims.target_module_id != module_id
        or claims.expires_at <= now
        or claims.issued_at > now + timedelta(seconds=30)
    ):
        raise ValueError("Peer credential binding or expiry is invalid")
    verify_signature(issuer, credential.signature, credential_bytes(claims))
