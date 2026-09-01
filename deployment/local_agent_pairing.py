"""Idempotent pairing for the Agent co-located with a Standalone Core."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Literal

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.core_client import DeviceCredential, DeviceCredentialStore
from agent.identity import AgentIdentity, AgentIdentityStore
from backend.db.audit_log import AuditLog
from backend.db.device import Device, DeviceCredential as StoredDeviceCredential
from backend.db.user import User
from backend.services.device_pairing import (
    approve_pairing_request,
    claim_pairing_code,
    complete_pairing_request,
    issue_pairing_code,
    issue_replacement_device_credential,
)
from three_mm_protocol import PROTOCOL_VERSION, AgentRole
from three_mm_provisioning import (
    FileProvisioningStore,
    ProvisioningState,
)

PAIRING_PRIVATE_KEY_NAME = "pairing-private-key.pem"
LOCAL_CORE_ROLES = frozenset({AgentRole.STANDALONE, AgentRole.HUB})


class LocalAgentPairingError(RuntimeError):
    """The trusted local bootstrap could not establish a consistent pairing."""


@dataclass(frozen=True, slots=True)
class LocalAgentPairingResult:
    status: Literal["paired", "already_paired", "repaired", "external_core"]
    device_id: str | None


def _load_or_create_public_key(agent_data_dir: Path) -> str:
    """Return a persistent Ed25519 public key without exposing its private half."""

    private_key_path = agent_data_dir / PAIRING_PRIVATE_KEY_NAME
    if private_key_path.exists():
        if private_key_path.is_symlink() or not private_key_path.is_file():
            raise LocalAgentPairingError("Local Agent pairing key is not a regular file")
        if os.name != "nt" and private_key_path.stat().st_mode & 0o077:
            raise LocalAgentPairingError("Local Agent pairing key permissions are unsafe")
        try:
            private_key = serialization.load_pem_private_key(
                private_key_path.read_bytes(),
                password=None,
            )
        except (OSError, ValueError) as exc:
            raise LocalAgentPairingError("Local Agent pairing key is invalid") from exc
        if not isinstance(private_key, Ed25519PrivateKey):
            raise LocalAgentPairingError("Local Agent pairing key is not Ed25519")
    else:
        agent_data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(agent_data_dir, 0o700)
        private_key = Ed25519PrivateKey.generate()
        encoded = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{PAIRING_PRIVATE_KEY_NAME}.",
            dir=agent_data_dir,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as target:
                os.chmod(temporary_path, 0o600)
                target.write(encoded)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary_path, private_key_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("ascii")


def _administrator(db: Session, email: str | None) -> User:
    statement = select(User).where(User.role == "admin")
    if email is not None:
        statement = statement.where(User.email == email.strip().lower())
    admin = db.scalar(statement.order_by(User.id).limit(1))
    if admin is None:
        raise LocalAgentPairingError("A Core administrator is required for local pairing")
    return admin


def _active_stored_credential(
    db: Session,
    *,
    device: Device,
    credential: DeviceCredential,
) -> StoredDeviceCredential | None:
    if credential.device_id != device.device_id or device.revoked_at is not None:
        return None
    return db.scalar(
        select(StoredDeviceCredential).where(
            StoredDeviceCredential.device_id == device.id,
            StoredDeviceCredential.credential_id == credential.credential_id,
            StoredDeviceCredential.revoked_at.is_(None),
        )
    )


def ensure_local_agent_pairing(
    db: Session,
    *,
    identity: AgentIdentity,
    credential_dir: Path,
    display_name: str,
    role: AgentRole,
    admin_email: str | None = None,
    public_key: str | None = None,
    public_key_factory: Callable[[], str] | None = None,
) -> LocalAgentPairingResult:
    """Pair or safely recover one trusted co-located Agent identity."""

    if role not in LOCAL_CORE_ROLES:
        return LocalAgentPairingResult("external_core", None)
    normalized_name = display_name.strip()
    if not normalized_name:
        raise LocalAgentPairingError("Local Agent display name is required")

    store = DeviceCredentialStore(credential_dir)
    local_credential = store.load()
    device = db.scalar(select(Device).where(Device.device_id == identity.device_id))
    if (
        local_credential is not None
        and device is not None
        and _active_stored_credential(
            db,
            device=device,
            credential=local_credential,
        )
        is not None
    ):
        return LocalAgentPairingResult("already_paired", identity.device_id)

    admin = _administrator(db, admin_email)
    if device is not None:
        if device.revoked_at is not None:
            raise LocalAgentPairingError("The local Agent identity is revoked in Core")
        revoked_at = datetime.now(UTC)
        active_credentials = tuple(
            db.scalars(
                select(StoredDeviceCredential).where(
                    StoredDeviceCredential.device_id == device.id,
                    StoredDeviceCredential.revoked_at.is_(None),
                )
            )
        )
        for stored in active_credentials:
            stored.revoked_at = revoked_at
        replacement = issue_replacement_device_credential(
            db,
            device_id=identity.device_id,
            now=revoked_at,
        )
        store.save(
            DeviceCredential(
                device_id=replacement.device_id,
                credential_id=replacement.credential_id,
                credential_secret=replacement.secret,
            )
        )
        db.add(
            AuditLog(
                user_id=admin.id,
                action="DEVICE_CREDENTIAL_REPLACED",
                entity_type="device",
                entity_id=device.id,
                entity_name=device.device_id,
                changes={
                    "source": "local-bootstrap-recovery",
                    "revoked_credential_ids": [
                        stored.credential_id for stored in active_credentials
                    ],
                },
            )
        )
        db.commit()
        return LocalAgentPairingResult("repaired", identity.device_id)

    resolved_public_key = (public_key or "").strip()
    if not resolved_public_key and public_key_factory is not None:
        resolved_public_key = public_key_factory().strip()
    if not resolved_public_key:
        raise LocalAgentPairingError("A local Agent public key is required")

    issued = issue_pairing_code(db, created_by_user_id=admin.id)
    claim_pairing_code(
        db,
        code=issued.code,
        requested_device_id=identity.device_id,
        public_key=resolved_public_key,
        requested_metadata={
            "display_name": normalized_name,
            "role": role.value,
            "protocol_version": PROTOCOL_VERSION,
        },
    )
    device = approve_pairing_request(
        db,
        request_id=issued.request_id,
        approved_by_user_id=admin.id,
    )
    issued_credential = complete_pairing_request(
        db,
        code=issued.code,
        requested_device_id=identity.device_id,
    )
    store.save(
        DeviceCredential(
            device_id=issued_credential.device_id,
            credential_id=issued_credential.credential_id,
            credential_secret=issued_credential.secret,
        )
    )
    db.add(
        AuditLog(
            user_id=admin.id,
            action="DEVICE_PAIRING_APPROVED",
            entity_type="device",
            entity_id=device.id,
            entity_name=device.device_id,
            changes={
                "pairing_request_id": issued.request_id,
                "source": "local-bootstrap",
            },
        )
    )
    db.commit()
    return LocalAgentPairingResult("paired", identity.device_id)


def ensure_automatic_local_agent_pairing(
    db: Session,
    *,
    agent_data_dir: Path,
    provisioning_data_dir: Path,
    admin_email: str | None = None,
) -> LocalAgentPairingResult:
    """Resolve trusted local pairing inputs from persisted first-boot state."""

    snapshot = FileProvisioningStore(provisioning_data_dir).load()
    if snapshot is None or snapshot.state is not ProvisioningState.PROVISIONED:
        raise LocalAgentPairingError("Provisioning must complete before local pairing")
    if snapshot.role not in LOCAL_CORE_ROLES:
        return LocalAgentPairingResult("external_core", None)
    if snapshot.device_name is None or snapshot.role is None:
        raise LocalAgentPairingError("Provisioning state is incomplete")

    identity = AgentIdentityStore(agent_data_dir).load_or_create()
    return ensure_local_agent_pairing(
        db,
        identity=identity,
        credential_dir=agent_data_dir,
        display_name=snapshot.device_name,
        role=snapshot.role,
        admin_email=admin_email,
        public_key_factory=lambda: _load_or_create_public_key(agent_data_dir),
    )
