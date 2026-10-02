"""Installation identity and bounded, receiver-bound possession proof v1.

No enrollment, ownership, credential or replay policy is implied by a proof.
Cryptography is imported only by verification; Agent schema imports stay light.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from three_mm_protocol.module_manifest import SEMVER_PATTERN


INSTALLATION_ID_PATTERN = r"^inst_[0-9a-f]{32}$"
KEY_ID_PATTERN = r"^[0-9a-f]{64}$"
PROOF_DOMAIN = b"3mm.installation.identity.proof.v1\n"
PROOF_MAX_LIFETIME_SECONDS = 120
PROOF_CLOCK_SKEW_SECONDS = 30


class IdentityContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("*", mode="before")
    @classmethod
    def reject_boolean_versions(cls, value):
        if isinstance(value, bool):
            raise ValueError("Boolean values are not identity contract fields")
        return value


class InstallationIdentityV1(IdentityContract):
    identity_version: Literal[1] = 1
    installation_id: str = Field(pattern=INSTALLATION_ID_PATTERN)
    algorithm: Literal["ed25519"] = "ed25519"
    key_id: str = Field(pattern=KEY_ID_PATTERN)
    public_key: str = Field(min_length=44, max_length=44)
    key_generation: Literal[1] = 1
    created_at: AwareDatetime

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value):
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_key_binding(self):
        raw = base64.b64decode(self.public_key, validate=True)
        if (
            len(raw) != 32
            or base64.b64encode(raw).decode("ascii") != self.public_key
            or hashlib.sha256(raw).hexdigest() != self.key_id
        ):
            raise ValueError("Installation public key binding is invalid")
        return self


class InstallationIdentityResultV1(IdentityContract):
    identity: InstallationIdentityV1
    core_version: str = Field(pattern=SEMVER_PATTERN)
    protocol_version: Literal["1.0"] = "1.0"
    sdk_version: Literal["1.1", "1.2", "1.3"] = "1.3"


class InstallationProofRequestV1(IdentityContract):
    proof_version: Literal[1] = 1
    purpose: Literal["identity.possession"] = "identity.possession"
    challenge: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    receiver_installation_id: str = Field(pattern=INSTALLATION_ID_PATTERN)
    receiver_key_id: str = Field(pattern=KEY_ID_PATTERN)
    receiver_key_generation: Literal[1] = 1
    audience: str = Field(min_length=9, max_length=255)
    resource: str = Field(pattern=r"^[a-z][a-z0-9._:/-]{0,159}$")
    created_at: AwareDatetime
    expires_at: AwareDatetime

    @field_validator("created_at", "expires_at")
    @classmethod
    def utc_timestamps(cls, value):
        return value.astimezone(UTC)

    @field_validator("challenge")
    @classmethod
    def canonical_challenge(cls, value):
        raw = base64.urlsafe_b64decode(value + "=")
        if (
            len(raw) != 32
            or base64.urlsafe_b64encode(raw).decode().rstrip("=") != value
        ):
            raise ValueError("Proof challenge is not canonical")
        return value

    @field_validator("audience")
    @classmethod
    def canonical_origin(cls, value):
        parsed = urlsplit(value)
        host = parsed.hostname
        if (
            parsed.scheme != "https"
            or not host
            or not value.isascii()
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Proof audience must be a canonical HTTPS origin")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if len(host) > 253 or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.split(".")
            ):
                raise ValueError("Proof audience hostname is invalid")
            canonical_host = host
        else:
            canonical_host = (
                f"[{address.compressed}]" if address.version == 6 else str(address)
            )
        port = parsed.port
        if port is not None and (port == 443 or not 1 <= port <= 65535):
            raise ValueError("Proof audience port is not canonical")
        canonical = (
            "https://" + canonical_host + (f":{port}" if port is not None else "")
        )
        if value != canonical:
            raise ValueError("Proof audience must be a canonical HTTPS origin")
        return value

    @model_validator(mode="after")
    def bounded_lifetime(self):
        lifetime = (self.expires_at - self.created_at).total_seconds()
        if not 0 < lifetime <= PROOF_MAX_LIFETIME_SECONDS:
            raise ValueError("Installation proof lifetime is invalid")
        return self


class InstallationProofV1(IdentityContract):
    proof_version: Literal[1] = 1
    identity: InstallationIdentityV1
    request: InstallationProofRequestV1
    signature: str = Field(min_length=88, max_length=88)

    @field_validator("signature")
    @classmethod
    def canonical_signature(cls, value):
        raw = base64.b64decode(value, validate=True)
        if len(raw) != 64 or base64.b64encode(raw).decode("ascii") != value:
            raise ValueError("Installation proof signature is invalid")
        return value


def canonical_installation_proof(
    identity: InstallationIdentityV1,
    request: InstallationProofRequestV1,
) -> bytes:
    return PROOF_DOMAIN + json.dumps(
        {
            "identity": identity.model_dump(mode="json"),
            "request": request.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def validate_proof_time(request: InstallationProofRequestV1, now: datetime) -> None:
    if now.utcoffset() is None:
        raise ValueError("Proof verification clock requires a timezone")
    if (
        request.created_at > now + timedelta(seconds=PROOF_CLOCK_SKEW_SECONDS)
        or request.expires_at <= now
    ):
        raise ValueError("Installation proof has expired or is not yet valid")


def verify_installation_proof(
    proof: InstallationProofV1 | dict,
    *,
    expected_identity: InstallationIdentityV1 | dict,
    expected_request: InstallationProofRequestV1 | dict,
    now: datetime | None = None,
) -> InstallationIdentityV1:
    """Verify possession against independent expectations, not embedded trust.

    The receiver is responsible for one-time challenge consumption (G2).
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    proof = InstallationProofV1.model_validate(proof)
    identity = InstallationIdentityV1.model_validate(expected_identity)
    request = InstallationProofRequestV1.model_validate(expected_request)
    if proof.identity != identity or proof.request != request:
        raise ValueError(
            "Installation proof does not match the expected identity/challenge"
        )
    validate_proof_time(request, now or datetime.now(UTC))
    try:
        Ed25519PublicKey.from_public_bytes(
            base64.b64decode(identity.public_key)
        ).verify(
            base64.b64decode(proof.signature),
            canonical_installation_proof(identity, request),
        )
    except InvalidSignature as exc:
        raise ValueError("Installation proof signature is invalid") from exc
    return identity
