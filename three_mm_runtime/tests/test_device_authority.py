"""Reset/pin semantics independent of Core roles and hardware modules."""

import base64
import hashlib
import json
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agent.identity import AgentIdentityStore
from three_mm_protocol.device_platform import (
    AuthorityProofV1,
    RESET_POLICIES,
    challenge,
    canonical_authority,
)
from three_mm_protocol.installation_identity import InstallationIdentityV1
from three_mm_protocol.device_authority import DeviceAuthorityStore
from three_mm_runtime.device_authority_reset import reset_authority


def proof(request, *, installation_id="inst_" + "a" * 32, key=None):
    key = key or Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    identity = InstallationIdentityV1(
        installation_id=installation_id,
        key_id=hashlib.sha256(raw).hexdigest(),
        public_key=base64.b64encode(raw).decode(),
        created_at=datetime.now(UTC),
    )
    return AuthorityProofV1(
        identity=identity,
        request=request,
        payload={},
        signature=base64.b64encode(
            key.sign(canonical_authority(identity, request, {}))
        ).decode(),
    )


def test_reset_retain_identity_modules_journal_but_rotate_authority_and_quarantine_outbox(
    tmp_path,
):
    identity = AgentIdentityStore(tmp_path).load_or_create()
    old_id = "cred_" + "b" * 32
    request = challenge(identity.device_id, old_id, "identity")
    store = DeviceAuthorityStore(tmp_path, identity.device_id, old_id)
    old_proof = proof(request)
    store.verify(old_proof, request, bootstrap=True)
    for name in (
        "core-credential.json",
        "core-binding.json",
        "hub-enrollment.json",
        "outbox.json",
        "reconciliation-state.json",
    ):
        (tmp_path / name).write_text(
            "retained-old-authority-evidence", encoding="utf-8"
        )
    journal = tmp_path / "physical-commands.sqlite3"
    journal.write_bytes(b"do-not-replay")
    modules = tmp_path / "modules"
    modules.mkdir()
    (modules / "active.json").write_text("retained", encoding="utf-8")
    with pytest.raises(ValueError, match="Stop"):
        reset_authority(tmp_path, identity.device_id, agent_stopped=False)
    with pytest.raises(ValueError, match="confirmation"):
        reset_authority(tmp_path, "dev_" + "f" * 32, agent_stopped=True)
    quarantine = reset_authority(tmp_path, identity.device_id, agent_stopped=True)
    assert quarantine.is_relative_to(tmp_path.resolve())
    assert (quarantine / "outbox.json").read_text() == "retained-old-authority-evidence"
    assert not (tmp_path / "core-credential.json").exists()
    assert AgentIdentityStore(tmp_path).load_or_create() == identity
    assert journal.read_bytes() == b"do-not-replay"
    assert (modules / "active.json").read_text() == "retained"
    with pytest.raises(ValueError, match="reset/rotation"):
        store.verify(
            old_proof, request
        )  # A publisher holding old secrets cannot continue.
    new_id = "cred_" + "c" * 32
    rebound = DeviceAuthorityStore(tmp_path, identity.device_id, new_id)
    request_b = challenge(identity.device_id, new_id, "identity")
    proof_b = proof(request_b, installation_id="inst_" + "d" * 32)
    rebound.verify(proof_b, request_b, bootstrap=True)
    with pytest.raises(ValueError, match="mismatch"):
        rebound.verify(old_proof, challenge(identity.device_id, new_id, "identity"))


def test_interrupted_reset_and_invalid_pin_fail_closed(tmp_path, monkeypatch):
    identity = AgentIdentityStore(tmp_path).load_or_create()
    (tmp_path / "core-credential.json").write_text("retained", encoding="utf-8")
    import three_mm_runtime.device_authority_reset as module

    monkeypatch.setattr(
        module.os,
        "replace",
        lambda *a: (_ for _ in ()).throw(OSError("simulated disk failure")),
    )
    with pytest.raises(OSError):
        reset_authority(tmp_path, identity.device_id, agent_stopped=True)
    assert (tmp_path / "authority-reset.json").exists()
    with pytest.raises(ValueError, match="incomplete"):
        DeviceAuthorityStore(tmp_path, identity.device_id, "cred_" + "b" * 32)
    assert (tmp_path / "core-credential.json").read_text() == "retained"


def test_reset_policies_are_distinct_and_not_revocation():
    network, authority, factory = (
        RESET_POLICIES[key] for key in ("network", "authority", "factory")
    )
    assert (
        network.preserve_authority
        and network.preserve_identity
        and not network.rotate_credentials
    )
    assert (
        authority.preserve_identity
        and authority.preserve_execution_evidence
        and authority.rotate_credentials
    )
    assert not authority.preserve_authority
    assert not factory.preserve_identity and not factory.preserve_execution_evidence
    assert "revoked" not in RESET_POLICIES


def test_legacy_unpinned_publisher_cannot_continue_after_local_reset(tmp_path):
    identity = AgentIdentityStore(tmp_path).load_or_create()
    store = DeviceAuthorityStore(tmp_path, identity.device_id, "cred_" + "b" * 32)
    assert store.check_current() is None
    reset_authority(tmp_path, identity.device_id, agent_stopped=True)
    with pytest.raises(ValueError, match="reset/rotation"):
        store.check_current()


def test_minimal_node_openssl_verifies_real_ed25519_without_cryptography(monkeypatch):
    import builtins
    import os
    import subprocess
    from pathlib import Path
    from three_mm_protocol.device_authority import verify_ed25519

    executable = (
        Path("/usr/bin/openssl")
        if os.name == "posix"
        else Path("C:/Program Files/Git/usr/bin/openssl.exe")
    )
    if not executable.is_file():
        pytest.skip(
            "OpenSSL is required to exercise minimal Node signature verification"
        )
    request = challenge("dev_" + "a" * 32, "cred_" + "b" * 32, "identity")
    signed = proof(request)
    key = base64.b64decode(signed.identity.public_key)
    signature = base64.b64decode(signed.signature)
    message = canonical_authority(signed.identity, request, {})
    original_import, original_run = builtins.__import__, subprocess.run

    def without_crypto(name, *args, **kwargs):
        if name.startswith("cryptography"):
            raise ImportError("Minimal Node dependency profile")
        return original_import(name, *args, **kwargs)

    def run(args, **kwargs):
        # Only adapt the executable/config path on Windows, not signed bytes.
        assert args[0] == "/usr/bin/openssl"
        args[0] = str(executable)
        if os.name == "nt":
            kwargs["env"]["OPENSSL_CONF"] = "NUL"
        return original_run(args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_crypto)
    monkeypatch.setattr(subprocess, "run", run)
    verify_ed25519(key, signature, message)
    with pytest.raises(ValueError, match="signature"):
        verify_ed25519(key, signature, message + b"tampered")
