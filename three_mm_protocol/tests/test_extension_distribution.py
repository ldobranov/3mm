import base64
import hashlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from three_mm_protocol.extension_distribution import (
    ExtensionArtifactSignatureV1,
    ExtensionArtifactV1,
    ExtensionPublisherKeyV1,
    canonical_extension_artifact_signature,
    verify_extension_artifact_bytes,
    verify_extension_artifact_signature,
)


def signed_artifact(package: bytes = b"immutable-cxp"):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    key = ExtensionPublisherKeyV1(
        publisher_id="3mm",
        key_id=hashlib.sha256(public).hexdigest(),
        public_key=base64.b64encode(public).decode("ascii"),
    )
    artifact = ExtensionArtifactV1(
        module_id="org.3mm.demo",
        version="1.2.3",
        publisher_id="3mm",
        sha256=hashlib.sha256(package).hexdigest(),
        size_bytes=len(package),
    )
    signature = private.sign(
        canonical_extension_artifact_signature(artifact, key.key_id)
    )
    signed = ExtensionArtifactSignatureV1(
        key_id=key.key_id,
        artifact=artifact,
        signature=base64.b64encode(signature).decode("ascii"),
    )
    return key, signed


def test_detached_signature_authenticates_exact_artifact_bytes():
    package = b"immutable-cxp"
    key, signed = signed_artifact(package)

    verify_extension_artifact_bytes(signed.artifact, package)
    verify_extension_artifact_signature(key, signed)


def test_artifact_bytes_reject_digest_or_size_mismatch():
    _, signed = signed_artifact()

    with pytest.raises(ValueError, match="size"):
        verify_extension_artifact_bytes(signed.artifact, b"x")
    same_size_tamper = b"IMMUTABLE-CXP"
    assert len(same_size_tamper) == signed.artifact.size_bytes
    with pytest.raises(ValueError, match="SHA-256"):
        verify_extension_artifact_bytes(signed.artifact, same_size_tamper)


def test_signature_rejects_metadata_tampering():
    key, signed = signed_artifact()
    changed = signed.model_copy(
        update={
            "artifact": signed.artifact.model_copy(
                update={"version": "1.2.4"}
            )
        }
    )

    with pytest.raises(ValueError, match="signature"):
        verify_extension_artifact_signature(key, changed)


def test_publisher_key_fingerprint_and_binding_are_strict():
    key, signed = signed_artifact()
    raw = base64.b64decode(key.public_key)

    with pytest.raises(ValidationError, match="fingerprint"):
        ExtensionPublisherKeyV1(
            publisher_id="3mm",
            key_id="0" * 64,
            public_key=base64.b64encode(raw).decode("ascii"),
        )

    other_publisher = key.model_copy(update={"publisher_id": "vendor"})
    with pytest.raises(ValueError, match="publisher"):
        verify_extension_artifact_signature(other_publisher, signed)
