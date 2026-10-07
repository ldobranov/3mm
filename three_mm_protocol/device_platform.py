"""Installation authority and lifecycle contracts, independent of transport/hardware.

Possession proof does not grant enrollment. Trust is pinned at explicit pairing;
every management response is bound to a fresh, caller-owned challenge.
"""

import base64
import json
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from three_mm_protocol.installation_identity import InstallationIdentityV1
from three_mm_protocol.node_security import MODULE_COMMAND_BYTES, validate_node_json

# Legacy beta.40 wire-domain token. Keep until a versioned authority-contract migration; this is not product branding.
DOMAIN = b"conerax.device.authority.v1\n"
DEVICE = r"^dev_[0-9a-f]{32}$"
CREDENTIAL = r"^cred_[0-9a-f]{32}$"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DeviceLifecycle(StrEnum):
    UNPROVISIONED = "unprovisioned"
    PROVISIONING = "provisioning"
    ENROLLMENT_PENDING = "enrollment_pending"
    ACTIVE = "active"
    DEGRADED = "degraded"
    REVOKED = "revoked"
    RECOVERY = "recovery"
    UNOWNED = "unowned"


class AuthorityChallengeV1(Contract):
    schema_version: Literal[1] = 1
    device_id: str = Field(pattern=DEVICE)
    credential_id: str = Field(pattern=CREDENTIAL)
    nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation: Literal[
        "identity", "command", "desired_state", "execution_permit", "platform"
    ]
    command_id: str | None = Field(default=None, pattern=r"^cmd_[0-9a-f]{32}$")
    created_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def bounded(self):
        if not 0 < (self.expires_at - self.created_at).total_seconds() <= 120:
            raise ValueError("Authority challenge lifetime must be 1..120 seconds")
        if (self.operation == "execution_permit") != (self.command_id is not None):
            raise ValueError("Only an execution permit binds a command ID")
        return self


def challenge(device_id, credential_id, operation, *, command_id=None):
    now = datetime.now(UTC)
    return AuthorityChallengeV1(
        device_id=device_id,
        credential_id=credential_id,
        operation=operation,
        command_id=command_id,
        nonce=secrets.token_hex(32),
        created_at=now,
        expires_at=now + timedelta(seconds=60),
    )


def validate_challenge_time(request, *, now=None):
    now = now or datetime.now(UTC)
    if (
        now.utcoffset() is None
        or request.created_at > now + timedelta(seconds=30)
        or request.expires_at <= now
    ):
        raise ValueError("Authority challenge is expired or from the future")


class AuthorityProofV1(Contract):
    schema_version: Literal[1] = 1
    identity: InstallationIdentityV1
    request: AuthorityChallengeV1
    payload: dict = Field(default_factory=dict)
    signature: str = Field(min_length=88, max_length=88)

    @model_validator(mode="after")
    def bounded(self):
        raw = base64.b64decode(self.signature, validate=True)
        if len(raw) != 64 or base64.b64encode(raw).decode("ascii") != self.signature:
            raise ValueError("Invalid authority signature encoding")
        # Preserve the existing bounded module-package command exception.
        command = self.payload.get("command")
        if (
            self.request.operation == "command"
            and command is not None
            and not isinstance(command, dict)
        ):
            raise ValueError("Invalid authority command payload")
        limit = (
            MODULE_COMMAND_BYTES
            if self.request.operation == "command"
            and isinstance(command, dict)
            and command.get("command_type") == "module.install"
            else 65536
        )
        validate_node_json(self.payload, max_bytes=limit)
        return self


def canonical_authority(identity, request, payload):
    return DOMAIN + json.dumps(
        {
            "identity": identity.model_dump(mode="json"),
            "request": request.model_dump(mode="json"),
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def verify_authority(proof, request, expected_identity, *, verifier=None, now=None):
    proof = AuthorityProofV1.model_validate(proof)
    validate_challenge_time(request, now=now)
    if proof.request != request or proof.identity != expected_identity:
        raise ValueError("Authority identity/challenge mismatch")
    if verifier is None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        def verifier(key, signature, message):
            Ed25519PublicKey.from_public_bytes(key).verify(signature, message)

    verifier(
        base64.b64decode(expected_identity.public_key, validate=True),
        base64.b64decode(proof.signature, validate=True),
        canonical_authority(proof.identity, request, proof.payload),
    )
    return proof.payload


class DevicePlatformSnapshotV1(Contract):
    schema_version: Literal[1] = 1
    device_id: str = Field(pattern=DEVICE)
    installation: InstallationIdentityV1
    authority_status: Literal["bound", "released"]
    lifecycle: DeviceLifecycle
    revision: int = Field(ge=0, le=2147483647, strict=True)
    connectivity: Literal["online", "offline"]
    last_seen_at: AwareDatetime | None = None
    reason: str | None = Field(default=None, max_length=120)


class LifecycleReportV1(Contract):
    device_id: str = Field(pattern=DEVICE)
    lifecycle: Literal["active", "degraded", "recovery"]
    expected_revision: int = Field(ge=0, le=2147483646, strict=True)
    reason: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9._-]{0,119}$")


class ResetPolicyV1(Contract):
    kind: Literal["network", "authority", "factory"]
    preserve_identity: bool
    preserve_authority: bool
    preserve_execution_evidence: bool
    rotate_credentials: bool


RESET_POLICIES = {
    "network": ResetPolicyV1(
        kind="network",
        preserve_identity=True,
        preserve_authority=True,
        preserve_execution_evidence=True,
        rotate_credentials=False,
    ),
    "authority": ResetPolicyV1(
        kind="authority",
        preserve_identity=True,
        preserve_authority=False,
        preserve_execution_evidence=True,
        rotate_credentials=True,
    ),
    # Explicit full reset uses the existing Linux policy: regenerate identity.
    "factory": ResetPolicyV1(
        kind="factory",
        preserve_identity=False,
        preserve_authority=False,
        preserve_execution_evidence=False,
        rotate_credentials=True,
    ),
}
