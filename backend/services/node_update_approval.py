"""Stable Hub approval identity and device-bound, expiring Node OTA approvals."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import stat
import threading
from contextlib import contextmanager

from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.config import UpdateCatalogSettings
from three_mm_protocol.node_updates import (
    NodeUpdateApprovalKey,
    NodeUpdateApplyRequest,
    NodeUpdateAuthorization,
    canonical_node_update_authorization,
)


class NodeApprovalError(RuntimeError):
    pass


_KEY_LOCK = threading.RLock()


@contextmanager
def _key_guard(path: Path):
    with _KEY_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.parent.is_symlink():
            raise NodeApprovalError("Hub approval key directory is unsafe")
        descriptor = os.open(
            path.with_suffix(".lock"),
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600,
        )
        with os.fdopen(descriptor, "rb+") as guard:
            if os.name == "posix":
                import fcntl
                fcntl.flock(guard, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "posix":
                    fcntl.flock(guard, fcntl.LOCK_UN)


def approval_key_path(settings: UpdateCatalogSettings) -> Path:
    # Durable Core storage, not immutable releases or disposable OTA staging.
    return Path(settings.policy_file).parent / "node-update-approval-key.pem"


def _read_or_create_key(path: Path) -> Ed25519PrivateKey:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.parent.is_symlink():
            raise NodeApprovalError("Hub approval key directory is unsafe")
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            generated = Ed25519PrivateKey.generate().private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            with os.fdopen(descriptor, "wb") as destination:
                destination.write(generated)
                destination.flush()
                os.fsync(destination.fileno())
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 4096:
                raise NodeApprovalError("Hub approval key file is unsafe")
            if os.name == "posix" and (
                info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077
            ):
                raise NodeApprovalError("Hub approval key permissions are unsafe")
            data = source.read(4097)
        key = serialization.load_pem_private_key(data, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise NodeApprovalError("Hub approval key type is invalid")
        return key
    except NodeApprovalError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        # Never silently replace a malformed/lost identity: Nodes pin this key.
        raise NodeApprovalError("Hub approval identity could not be accessed") from exc


def _private_key(settings: UpdateCatalogSettings) -> Ed25519PrivateKey:
    path = approval_key_path(settings)
    try:
        with _key_guard(path):
            return _read_or_create_key(path)
    except OSError as exc:
        raise NodeApprovalError("Hub approval identity could not be accessed") from exc


def _public_identity(private: Ed25519PrivateKey) -> NodeUpdateApprovalKey:
    raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    return NodeUpdateApprovalKey(
        key_id=hashlib.sha256(raw).hexdigest(),
        public_key=base64.b64encode(raw).decode("ascii"),
    )


def public_approval_key(settings: UpdateCatalogSettings) -> NodeUpdateApprovalKey:
    return _public_identity(_private_key(settings))


def sign_node_update(
    settings: UpdateCatalogSettings, request: NodeUpdateApplyRequest,
) -> NodeUpdateAuthorization:
    private = _private_key(settings)
    identity = _public_identity(private)
    signature = private.sign(canonical_node_update_authorization(request, identity.key_id))
    return NodeUpdateAuthorization(
        key_id=identity.key_id, request=request,
        signature=base64.b64encode(signature).decode("ascii"),
    )


def verify_node_update(settings: UpdateCatalogSettings, authorization: NodeUpdateAuthorization) -> None:
    private = _private_key(settings)
    identity = _public_identity(private)
    if identity.key_id != authorization.key_id:
        raise NodeApprovalError("Node update approval belongs to another Hub identity")
    try:
        private.public_key().verify(
            base64.b64decode(authorization.signature, validate=True),
            canonical_node_update_authorization(authorization.request, authorization.key_id),
        )
    except InvalidSignature as exc:
        raise NodeApprovalError("Node update approval signature is invalid") from exc
