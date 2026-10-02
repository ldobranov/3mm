"""Peer v2: proof-bound opaque application intent and exact consent review.

Intent issuance, expiry, ownership and organization policy belong to the
receiving application. Core authenticates the reference, not its meaning.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator
from three_mm_protocol.installation_identity import (
    InstallationIdentityV1,
    InstallationProofRequestV1,
)
from three_mm_protocol.module_manifest import MODULE_ID_PATTERN

from three_mm_protocol.installation_peer import (
    PeerModel,
    ProjectionConsentV1,
    PeerEnrollmentStartV1,
    PeerEnrollmentChallengeV1,
    PeerEnrollmentCompleteV1,
    PeerCredentialClaimsV1,
    PeerCredentialV1,
    PeerEnrollmentResultV1,
    PeerOutboundStatusV1,
    PeerRequestV1,
    canonical_json,
)

PEER_V2_PREFIX = "/api/v1/installation-peers/v2"
APPLICATION_INTENT_PATTERN = r"^[A-Za-z0-9_-]{1,256}$"


def normalized_consent(value) -> ProjectionConsentV1:
    consent = ProjectionConsentV1.model_validate(value)
    return consent.model_copy(
        update={
            "summary_fields": tuple(sorted(consent.summary_fields)),
            "node_ids": tuple(sorted(consent.node_ids)),
            "node_fields": tuple(sorted(consent.node_fields)),
        }
    )


def metadata_digest(intent: str, consent: ProjectionConsentV1, revision: int) -> str:
    return hashlib.sha256(
        canonical_json(
            {
                "metadata_version": 2,
                "application_intent": intent,
                "consent_revision": revision,
                "consent": consent.model_dump(mode="json"),
            }
        )
    ).hexdigest()


class PeerEnrollmentMetadataV2(PeerModel):
    metadata_version: Literal[2] = 2
    application_intent: str = Field(pattern=APPLICATION_INTENT_PATTERN, max_length=256)
    consent_revision: StrictInt = Field(ge=1)
    consent: ProjectionConsentV1
    metadata_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("metadata_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Metadata version must be an integer")
        return value

    @model_validator(mode="after")
    def exact_hash(self):
        if self.consent != normalized_consent(self.consent):
            raise ValueError("Consent metadata must be normalized")
        if self.metadata_hash != metadata_digest(
            self.application_intent, self.consent, self.consent_revision
        ):
            raise ValueError("Enrollment metadata hash does not match")
        return self


class PeerOutboundConsentRequestV2(PeerModel):
    origin: str = Field(max_length=255)
    receiver_identity: InstallationIdentityV1
    target_module_id: str = Field(pattern=MODULE_ID_PATTERN, max_length=160)
    consent: ProjectionConsentV1
    application_intent: str = Field(pattern=APPLICATION_INTENT_PATTERN, max_length=256)
    _origin = field_validator("origin")(
        InstallationProofRequestV1.canonical_origin.__func__
    )


class PeerApprovalReviewV2(PeerModel):
    expected_generation: StrictInt = Field(ge=1)
    expected_metadata_revision: StrictInt = Field(ge=1)
    expected_metadata_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PeerInboundStatusV2(PeerModel):
    peer_version: Literal[2] = 2
    binding_id: str = Field(pattern=r"^peer_[0-9a-f]{32}$")
    sender_identity: InstallationIdentityV1
    state: Literal["challenged", "pending", "active", "revoked", "renewable"]
    generation: StrictInt = Field(ge=1)
    approval_expires_at: AwareDatetime
    verified_metadata: PeerEnrollmentMetadataV2 | None = None

    @model_validator(mode="after")
    def completed_only(self):
        if (self.state in ("pending", "active")) != (
            self.verified_metadata is not None
        ):
            raise ValueError("Only completed enrollment may expose verified metadata")
        return self


def enrollment_metadata(intent, consent, revision=1) -> PeerEnrollmentMetadataV2:
    consent = normalized_consent(consent)
    return PeerEnrollmentMetadataV2(
        application_intent=intent,
        consent=consent,
        consent_revision=revision,
        metadata_hash=metadata_digest(intent, consent, revision),
    )


class PeerEnrollmentStartV2(PeerEnrollmentStartV1):
    peer_version: Literal[2] = 2
    enrollment_metadata: PeerEnrollmentMetadataV2


class PeerEnrollmentChallengeV2(PeerEnrollmentChallengeV1):
    peer_version: Literal[2] = 2
    enrollment_metadata: PeerEnrollmentMetadataV2


class PeerEnrollmentCompleteV2(PeerEnrollmentCompleteV1):
    peer_version: Literal[2] = 2
    metadata_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PeerCredentialClaimsV2(PeerCredentialClaimsV1):
    credential_version: Literal[2] = 2
    enrollment_metadata: PeerEnrollmentMetadataV2


class PeerCredentialV2(PeerCredentialV1):
    claims: PeerCredentialClaimsV2


class PeerEnrollmentResultV2(PeerEnrollmentResultV1):
    peer_version: Literal[2] = 2
    enrollment_metadata: PeerEnrollmentMetadataV2
    credential: PeerCredentialV2 | None = None

    @model_validator(mode="after")
    def exact_credential_metadata(self):
        if (
            self.credential
            and self.credential.claims.enrollment_metadata != self.enrollment_metadata
        ):
            raise ValueError("Credential metadata does not match the receipt")
        return self


class PeerOutboundStatusV2(PeerOutboundStatusV1):
    peer_version: Literal[2] = 2
    enrollment_metadata: PeerEnrollmentMetadataV2

    @model_validator(mode="after")
    def exact_local_consent(self):
        # Revocation/restore increments the local fence but retains the receipt.
        if self.state != "revoked" and (
            self.consent_revision != self.enrollment_metadata.consent_revision
            or self.consent != self.enrollment_metadata.consent
        ):
            raise ValueError("Local consent differs from the enrollment metadata")
        return self


class PeerRequestV2(PeerRequestV1):
    peer_version: Literal[2] = 2
    credential: PeerCredentialV2
    path: str = Field(
        pattern=r"^/api/v1/installation-peers/v2/[a-z0-9_./-]+$", max_length=255
    )


class PeerCapabilitiesV2(PeerModel):
    peer_versions: tuple[Literal[1, 2], ...] = (1, 2)
    approval_binding_version: Literal[2] = 2
    minimum_sdk_version: Literal["1.3"] = "1.3"

    @field_validator("approval_binding_version", mode="before")
    @classmethod
    def integer_binding_version(cls, value):
        if type(value) is not int:
            raise ValueError("Approval binding version must be an integer")
        return value

    @field_validator("peer_versions", mode="before")
    @classmethod
    def integer_peer_versions(cls, value):
        if not isinstance(value, (tuple, list)) or any(
            type(item) is not int for item in value
        ):
            raise ValueError("Peer versions must be integers")
        return value


V2_MODELS = {
    PeerEnrollmentStartV1: PeerEnrollmentStartV2,
    PeerEnrollmentChallengeV1: PeerEnrollmentChallengeV2,
    PeerEnrollmentCompleteV1: PeerEnrollmentCompleteV2,
    PeerCredentialClaimsV1: PeerCredentialClaimsV2,
    PeerCredentialV1: PeerCredentialV2,
    PeerEnrollmentResultV1: PeerEnrollmentResultV2,
    PeerOutboundStatusV1: PeerOutboundStatusV2,
    PeerRequestV1: PeerRequestV2,
}


def peer_model(model, version):
    if type(version) is not int or version not in (1, 2):
        raise ValueError("Unsupported installation peer version")
    return V2_MODELS[model] if version == 2 else model


def parse_peer(model, value, *, version=None):
    if isinstance(value, PeerModel):
        value = value.model_dump(mode="json")
    if not isinstance(value, dict):
        raise ValueError("Installation peer value must be an object")
    if model is PeerCredentialV1:
        claims = value.get("claims")
        if not isinstance(claims, dict):
            raise ValueError("Installation peer credential claims must be an object")
        actual = claims.get("credential_version", 1)
    elif model is PeerCredentialClaimsV1:
        actual = value.get("credential_version", 1)
    else:
        actual = value.get("peer_version", 1)
    if version is not None and (type(actual) is not int or actual != version):
        raise ValueError("Installation peer wire version does not match")
    return peer_model(model, actual).model_validate(value)
