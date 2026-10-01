"""Explicit root-pinned Hub approval, independently verified on a minimal Node."""
from __future__ import annotations

import base64
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from three_mm_protocol.node_updates import (
    DEVICE_PATTERN, NodeUpdateApprovalKey, NodeUpdateAuthorization, canonical_node_update_authorization,
)
from three_mm_runtime.node_update_helper import NodeUpdateError, read_small, trusted_path

TRUST_FILE = Path("/etc/3mm/node-update-trust.json")
OPENSSL = Path("/usr/bin/openssl")
ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")


class NodeUpdateTrust(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    device_id: str = Field(pattern=DEVICE_PATTERN)
    hub_key: NodeUpdateApprovalKey


def read_node_update_trust(path=TRUST_FILE, *, enforce_permissions=True):
    path = Path(path)
    try:
        trusted_path(path, permissions=enforce_permissions)
        if enforce_permissions and path.stat().st_mode & 0o077:
            raise NodeUpdateError("unsafe_trust", "Hub approval trust file must be private to root")
        return NodeUpdateTrust.model_validate_json(read_small(path, 4096))
    except FileNotFoundError as exc:
        raise NodeUpdateError("hub_trust_missing", "The Hub approval key is not pinned on this Node") from exc
    except (ValidationError, ValueError) as exc:
        raise NodeUpdateError("invalid_trust", "Pinned Hub approval key is invalid") from exc


def read_approval_key(path=TRUST_FILE, *, enforce_permissions=True):
    return read_node_update_trust(path, enforce_permissions=enforce_permissions).hub_key


def verify_node_update_authorization(authorization, *, state_root, trust_file=TRUST_FILE,
                                     enforce_permissions=True, runner=subprocess.run):
    """Verify fixed canonical bytes; never use a key or executable from the caller."""
    if not isinstance(authorization, NodeUpdateAuthorization):
        raise NodeUpdateError("authorization_required", "A signed Hub approval is required")
    trust = read_node_update_trust(trust_file, enforce_permissions=enforce_permissions)
    key = trust.hub_key
    if authorization.request.device_id != trust.device_id:
        raise NodeUpdateError("identity_mismatch", "Hub approval targets another root-pinned Node identity")
    if authorization.key_id != key.key_id:
        raise NodeUpdateError("untrusted_hub", "Approval came from an untrusted Hub key")
    # Verify the executable and resolved binary before invoking root subprocesses.
    try:
        executable = OPENSSL.resolve(strict=True)
    except FileNotFoundError as exc:
        raise NodeUpdateError("approval_verifier_unavailable", "OpenSSL is unavailable") from exc
    trusted_path(executable, permissions=enforce_permissions)
    root = Path(state_root).absolute()
    trusted_path(root, directory=True, permissions=enforce_permissions)
    with tempfile.TemporaryDirectory(prefix=".approval-", dir=root) as temporary:
        directory = Path(temporary)
        os.chmod(directory, 0o700)
        values = {
            "key.der": ED25519_SPKI_PREFIX + base64.b64decode(key.public_key, validate=True),
            "message": canonical_node_update_authorization(authorization.request, authorization.key_id),
            "signature": base64.b64decode(authorization.signature, validate=True),
        }
        for name, value in values.items():
            descriptor = os.open(directory / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as saved:
                saved.write(value)
        try:
            result = runner([str(OPENSSL), "pkeyutl", "-verify", "-pubin", "-keyform", "DER",
                "-inkey", str(directory / "key.der"), "-rawin", "-in", str(directory / "message"),
                "-sigfile", str(directory / "signature")], check=False, timeout=5,
                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "OPENSSL_CONF": "/dev/null"},
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NodeUpdateError("approval_verifier_unavailable", "Hub approval verification is unavailable") from exc
        if result.returncode:
            raise NodeUpdateError("invalid_approval", "Hub approval signature is invalid")


def pin_approval_key(key, expected_key_id, *, device_id, trust_file=TRUST_FILE, enforce_permissions=True):
    """Explicit trust installation: repeatable matching pin, never silent replacement."""
    if key.key_id != expected_key_id:
        raise NodeUpdateError("fingerprint_mismatch", "Hub fingerprint differs from the explicitly approved fingerprint")
    trust = NodeUpdateTrust(device_id=device_id, hub_key=key)
    path = Path(trust_file).absolute()
    trusted_path(path.parent, directory=True, permissions=enforce_permissions)
    if path.exists() or path.is_symlink():
        existing = read_node_update_trust(path, enforce_permissions=enforce_permissions)
        if existing != trust:
            raise NodeUpdateError("hub_trust_conflict", "A different Hub approval key is already pinned")
        return False
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as saved:
        saved.write(trust.model_dump_json().encode("ascii") + b"\n")
        saved.flush()
        os.fsync(saved.fileno())
    if os.name == "posix":
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return True
