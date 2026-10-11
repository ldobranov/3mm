"""Detached release-manifest signing/verification (M15)."""

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from deployment.release_signing import (
    ReleaseSignature,
    ReleaseSigningError,
    canonical_manifest_bytes,
    load_private_key,
    load_public_key,
    sign_manifest,
    verify_manifest,
)


def manifest():
    return {
        "schema_version": 1,
        "version": "0.3.0-beta.46",
        "release_id": "v0.3.0-beta.46",
        "commit": "a" * 40,
        "channel": "beta",
        "artifacts": [],
        "dependencies": {"apt_packages": []},
    }


def write_keypair(tmp_path):
    private = Ed25519PrivateKey.generate()
    private_path = tmp_path / "release.key"
    public_path = tmp_path / "release.pub"
    private_path.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_path, public_path


def test_sign_and_verify_roundtrip(tmp_path):
    private_path, public_path = write_keypair(tmp_path)
    private = load_private_key(private_path)
    public = load_public_key(public_path)
    signature = sign_manifest(manifest(), private)
    assert len(signature.key_id) == 64
    verify_manifest(manifest(), signature, public)  # does not raise


def test_tampered_manifest_fails_verification(tmp_path):
    private_path, public_path = write_keypair(tmp_path)
    signature = sign_manifest(manifest(), load_private_key(private_path))
    tampered = manifest()
    tampered["version"] = "9.9.9"
    with pytest.raises(ReleaseSigningError, match="does not match"):
        verify_manifest(tampered, signature, load_public_key(public_path))


def test_untrusted_key_is_rejected(tmp_path):
    private_path, _ = write_keypair(tmp_path)
    signature = sign_manifest(manifest(), load_private_key(private_path))
    other = Ed25519PrivateKey.generate()
    with pytest.raises(ReleaseSigningError, match="untrusted key"):
        verify_manifest(manifest(), signature, other.public_key())


def test_malformed_signature_encoding_is_rejected(tmp_path):
    private_path, public_path = write_keypair(tmp_path)
    signature = sign_manifest(manifest(), load_private_key(private_path))
    broken = ReleaseSignature(key_id=signature.key_id, signature="not base64!!")
    with pytest.raises(ReleaseSigningError, match="encoding is invalid"):
        verify_manifest(manifest(), broken, load_public_key(public_path))


def test_canonical_bytes_are_stable_and_sorted():
    first = canonical_manifest_bytes({"b": 1, "a": 2})
    second = canonical_manifest_bytes({"a": 2, "b": 1})
    assert first == second
    assert first.endswith(b"\n")


def test_non_ed25519_key_is_rejected(tmp_path):
    from cryptography.hazmat.primitives.asymmetric import rsa

    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path / "rsa.key"
    path.write_bytes(
        rsa_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    with pytest.raises(ReleaseSigningError, match="must be Ed25519"):
        load_private_key(path)
