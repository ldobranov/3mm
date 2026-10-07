"""Versioned distribution metadata for immutable 3mm extension artifacts.

A .cxp is the existing Module Manifest v2 ZIP artifact with a product-specific
filename. Distribution signatures are deliberately detached so the signature
does not change the bytes or SHA-256 identity of the package it authenticates.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from three_mm_protocol.module_manifest import (
    MODULE_ID_PATTERN,
    PUBLISHER_ID_PATTERN,
    SEMVER_PATTERN,
)

SHA256_PATTERN = r"^[0-9a-f]{64}$"
MAX_EXTENSION_PACKAGE_BYTES = 10 * 1024 * 1024
EXTENSION_ARTIFACT_SIGNATURE_DOMAIN = b"3mm.extension-artifact.v1\n"


class DistributionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _canonical_base64(value: str, length: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid distribution signature encoding") from exc
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("Invalid distribution signature length or encoding")
    return decoded


class ExtensionArtifactV1(DistributionModel):
    """Immutable package identity published by an Extension Registry."""

    distribution_version: Literal[1] = 1
    module_id: str = Field(pattern=MODULE_ID_PATTERN, max_length=160)
    version: str = Field(pattern=SEMVER_PATTERN, max_length=64)
    publisher_id: str = Field(pattern=PUBLISHER_ID_PATTERN, max_length=120)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0, le=MAX_EXTENSION_PACKAGE_BYTES)


class ExtensionPublisherKeyV1(DistributionModel):
    """Ed25519 publisher identity trusted independently from a Registry mirror."""

    key_version: Literal[1] = 1
    algorithm: Literal["ed25519"] = "ed25519"
    publisher_id: str = Field(pattern=PUBLISHER_ID_PATTERN, max_length=120)
    key_id: str = Field(pattern=SHA256_PATTERN)
    public_key: str = Field(min_length=44, max_length=44)

    @model_validator(mode="after")
    def fingerprint_matches_key(self):
        if hashlib.sha256(_canonical_base64(self.public_key, 32)).hexdigest() != self.key_id:
            raise ValueError("Publisher key fingerprint does not match")
        return self


class ExtensionArtifactSignatureV1(DistributionModel):
    """Detached publisher signature for one exact immutable artifact."""

    signature_version: Literal[1] = 1
    key_id: str = Field(pattern=SHA256_PATTERN)
    artifact: ExtensionArtifactV1
    signature: str = Field(min_length=88, max_length=88)

    @field_validator("signature")
    @classmethod
    def canonical_signature(cls, value):
        _canonical_base64(value, 64)
        return value


def canonical_extension_artifact_signature(
    artifact: ExtensionArtifactV1, key_id: str
) -> bytes:
    """Stable, domain-separated bytes signed by publishers and verified by Core."""

    return EXTENSION_ARTIFACT_SIGNATURE_DOMAIN + json.dumps(
        {
            "key_id": key_id,
            "artifact": artifact.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def verify_extension_artifact_bytes(
    artifact: ExtensionArtifactV1, package: bytes
) -> None:
    """Bind Registry metadata to the exact .cxp bytes before package parsing."""

    if len(package) != artifact.size_bytes:
        raise ValueError("Extension artifact size does not match Registry metadata")
    if hashlib.sha256(package).hexdigest() != artifact.sha256:
        raise ValueError("Extension artifact SHA-256 does not match Registry metadata")


def verify_extension_artifact_signature(
    trusted_key: ExtensionPublisherKeyV1,
    signed: ExtensionArtifactSignatureV1,
) -> None:
    """Verify publisher identity and detached Ed25519 signature."""

    if signed.key_id != trusted_key.key_id:
        raise ValueError("Extension artifact was signed by another publisher key")
    if signed.artifact.publisher_id != trusted_key.publisher_id:
        raise ValueError("Extension artifact publisher does not match trusted key")

    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(
            _canonical_base64(trusted_key.public_key, 32)
        ).verify(
            _canonical_base64(signed.signature, 64),
            canonical_extension_artifact_signature(signed.artifact, signed.key_id),
        )
    except InvalidSignature as exc:
        raise ValueError("Extension artifact signature is invalid") from exc
