import base64
import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from three_mm_protocol.installation_identity import (
    InstallationIdentityV1,
    InstallationProofRequestV1,
    InstallationProofV1,
    canonical_installation_proof,
    verify_installation_proof,
)

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)


def identity_and_key():
    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return (
        InstallationIdentityV1(
            installation_id="inst_" + "a" * 32,
            key_id=hashlib.sha256(raw).hexdigest(),
            public_key=base64.b64encode(raw).decode(),
            created_at=NOW,
        ),
        key,
    )


def proof_request(**changes):
    return InstallationProofRequestV1.model_validate(
        {
            "challenge": base64.urlsafe_b64encode(b"test-challenge".ljust(32, b"x"))
            .decode()
            .rstrip("="),
            "receiver_installation_id": "inst_" + "b" * 32,
            "receiver_key_id": "c" * 64,
            "audience": "https://manager.example.test",
            "resource": "enrollment",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=90),
            **changes,
        }
    )


def test_public_identity_rejects_mismatched_keys_unknown_fields_and_booleans():
    identity, _ = identity_and_key()
    for changes in (
        {"key_id": "0" * 64},
        {"private_key": "not-allowed"},
        {"identity_version": True},
        {"key_generation": 2},
    ):
        with pytest.raises(ValidationError):
            InstallationIdentityV1.model_validate({**identity.model_dump(), **changes})


@pytest.mark.parametrize(
    "origin",
    [
        "http://manager.example.test",
        "https://user:pass@manager.example.test",
        "https://manager.example.test/",
        "https://MANAGER.example.test",
        "https://manager.example.test:443",
        "https://manager.example.test:0444",
        "https://manager.example.test?x=1",
        "https://manager.example.test#fragment",
        "https://manager..test",
        "https://[2001:0db8::1]",
        "https://manager.test:",
    ],
)
def test_noncanonical_or_insecure_origin_is_rejected(origin):
    with pytest.raises(ValidationError):
        proof_request(audience=origin)


@pytest.mark.parametrize(
    "changes",
    [
        {"expires_at": NOW},
        {"expires_at": NOW + timedelta(seconds=121)},
        {"created_at": NOW.replace(tzinfo=None)},
        {"challenge": "x" * 43},
        {"proof_version": True},
        {"purpose": "node.update"},
        {"payload": "arbitrary signing"},
    ],
)
def test_proof_input_is_bounded_and_domain_specific(changes):
    with pytest.raises(ValidationError):
        proof_request(**changes)


def test_canonical_signature_requires_independent_receiver_expectations_and_time():
    identity, key = identity_and_key()
    request = proof_request()
    signed = canonical_installation_proof(identity, request)
    assert signed.startswith(b"3mm.installation.identity.proof.v1\n")
    assert (
        canonical_installation_proof(
            identity,
            InstallationProofRequestV1.model_validate_json(request.model_dump_json()),
        )
        == signed
    )
    proof = InstallationProofV1(
        identity=identity,
        request=request,
        signature=base64.b64encode(key.sign(signed)).decode(),
    )
    assert (
        verify_installation_proof(
            proof, expected_identity=identity, expected_request=request, now=NOW
        )
        == identity
    )

    for changes in (
        {"audience": "https://other.example.test"},
        {"resource": "reporting"},
        {"receiver_installation_id": "inst_" + "d" * 32},
        {"receiver_key_id": "f" * 64},
        {"challenge": base64.urlsafe_b64encode(b"y" * 32).decode().rstrip("=")},
    ):
        with pytest.raises(ValueError, match="expected"):
            verify_installation_proof(
                proof,
                expected_identity=identity,
                expected_request=proof_request(**changes),
                now=NOW,
            )
    with pytest.raises(ValueError, match="expired"):
        verify_installation_proof(
            proof,
            expected_identity=identity,
            expected_request=request,
            now=request.expires_at,
        )
    with pytest.raises(ValueError, match="not yet"):
        verify_installation_proof(
            proof,
            expected_identity=identity,
            expected_request=request,
            now=NOW - timedelta(seconds=31),
        )
    with pytest.raises(ValueError, match="signature"):
        verify_installation_proof(
            {**proof.model_dump(), "signature": base64.b64encode(b"0" * 64).decode()},
            expected_identity=identity,
            expected_request=request,
            now=NOW,
        )
    different, _ = identity_and_key()
    with pytest.raises(ValueError, match="expected"):
        verify_installation_proof(
            proof, expected_identity=different, expected_request=request, now=NOW
        )
