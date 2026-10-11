"""Detached Ed25519 signing/verification for release manifests (M15).

Additive primitive for signed releases and trusted private repositories. It
signs the exact canonical manifest bytes and verifies them against a trusted
public key. It does not change the live installer, the update catalog or any
existing unsigned path; callers opt in explicitly.

Fail-closed rules:
- the signature is over the exact manifest bytes, so any change invalidates it;
- verification requires an explicitly supplied trusted public key;
- malformed keys, signatures or oversized inputs are rejected, never coerced.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

MAX_MANIFEST_BYTES = 1024 * 1024
SIGNATURE_SUFFIX = ".sig"


class ReleaseSigningError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ReleaseSignature:
    key_id: str
    signature: str


def canonical_manifest_bytes(manifest: dict) -> bytes:
    """The exact bytes a signature covers; identical to the published file."""
    if not isinstance(manifest, dict):
        raise ReleaseSigningError("Release manifest must be an object")
    return (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _public_key_id(public: Ed25519PublicKey) -> str:
    raw = public.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return hashlib.sha256(raw).hexdigest()


def load_private_key(path: Path) -> Ed25519PrivateKey:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ReleaseSigningError("Release signing key is unavailable") from exc
    try:
        key = serialization.load_pem_private_key(data, password=None)
    except (ValueError, TypeError) as exc:
        raise ReleaseSigningError("Release signing key is invalid") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise ReleaseSigningError("Release signing key must be Ed25519")
    return key


def load_public_key(path: Path) -> Ed25519PublicKey:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ReleaseSigningError("Trusted release key is unavailable") from exc
    try:
        key = serialization.load_pem_public_key(data)
    except (ValueError, TypeError) as exc:
        raise ReleaseSigningError("Trusted release key is invalid") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise ReleaseSigningError("Trusted release key must be Ed25519")
    return key


def sign_manifest(manifest: dict, private_key: Ed25519PrivateKey) -> ReleaseSignature:
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ReleaseSigningError("Release signing key must be Ed25519")
    body = canonical_manifest_bytes(manifest)
    if len(body) > MAX_MANIFEST_BYTES:
        raise ReleaseSigningError("Release manifest is too large to sign")
    signature = private_key.sign(body)
    return ReleaseSignature(
        key_id=_public_key_id(private_key.public_key()),
        signature=base64.b64encode(signature).decode("ascii"),
    )


def verify_manifest(
    manifest: dict,
    signature: ReleaseSignature,
    trusted_key: Ed25519PublicKey,
) -> None:
    """Raise unless the signature matches the exact manifest and trusted key."""
    if not isinstance(trusted_key, Ed25519PublicKey):
        raise ReleaseSigningError("Trusted release key must be Ed25519")
    if not isinstance(signature, ReleaseSignature):
        raise ReleaseSigningError("Release signature is invalid")
    if signature.key_id != _public_key_id(trusted_key):
        raise ReleaseSigningError("Release signature was made by an untrusted key")
    body = canonical_manifest_bytes(manifest)
    if len(body) > MAX_MANIFEST_BYTES:
        raise ReleaseSigningError("Release manifest is too large to verify")
    try:
        raw = base64.b64decode(signature.signature, validate=True)
    except (ValueError, TypeError) as exc:
        raise ReleaseSigningError("Release signature encoding is invalid") from exc
    try:
        trusted_key.verify(raw, body)
    except InvalidSignature as exc:
        raise ReleaseSigningError(
            "Release signature does not match the manifest"
        ) from exc
