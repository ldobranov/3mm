"""Atomic, encrypted installation identity and narrow possession proofs."""

from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.installation_identity import CoreInstallationIdentity
from backend.version import core_version
from three_mm_protocol.installation_identity import (
    InstallationIdentityResultV1,
    InstallationIdentityV1,
    InstallationProofRequestV1,
    InstallationProofV1,
    canonical_installation_proof,
    validate_proof_time,
)


class InstallationIdentityError(RuntimeError):
    pass


def _cipher(key: str | None = None) -> Fernet:
    try:
        key = (
            os.environ.get("AI_SETTINGS_MASTER_KEY", "") if key is None else key
        ).strip()
        if not key:
            raise ValueError("missing")
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise InstallationIdentityError(
            "Installation identity encryption key is unavailable or invalid"
        ) from exc


def _public_key(key: Ed25519PrivateKey) -> tuple[str, str]:
    raw = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii"), hashlib.sha256(raw).hexdigest()


def _load_or_create(db: Session) -> tuple[InstallationIdentityV1, Ed25519PrivateKey]:
    cipher = _cipher()
    row = db.get(CoreInstallationIdentity, 1)
    if row is None:
        private = Ed25519PrivateKey.generate()
        raw = private.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        public, key_id = _public_key(private)
        row = CoreInstallationIdentity(
            singleton_id=1,
            installation_id=f"inst_{uuid.uuid4().hex}",
            identity_version=1,
            key_generation=1,
            key_id=key_id,
            public_key=public,
            encrypted_private_key=cipher.encrypt(raw).decode("ascii"),
            created_at=datetime.now(UTC),
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            # Another worker won. Reload its complete binding; do not overwrite.
            db.rollback()
            row = db.get(CoreInstallationIdentity, 1)
            if row is None:
                raise InstallationIdentityError(
                    "Installation identity creation conflicted"
                )
    return _decode_identity(row, cipher)


def _decode_identity(
    row, cipher: Fernet
) -> tuple[InstallationIdentityV1, Ed25519PrivateKey]:
    try:
        created = row.created_at
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        # SQLite loses timezone storage; this column is always written in UTC.
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        identity = InstallationIdentityV1(
            identity_version=row.identity_version,
            installation_id=row.installation_id,
            key_id=row.key_id,
            public_key=row.public_key,
            key_generation=row.key_generation,
            created_at=created,
        )
        private = Ed25519PrivateKey.from_private_bytes(
            cipher.decrypt(row.encrypted_private_key.encode("ascii"))
        )
        public, key_id = _public_key(private)
        if public != identity.public_key or key_id != identity.key_id:
            raise ValueError("key binding mismatch")
    except (ValueError, TypeError, AttributeError, InvalidToken, UnicodeError) as exc:
        raise InstallationIdentityError(
            "Stored installation identity is invalid or cannot be decrypted"
        ) from exc
    return identity, private


def validate_identity_backup(database: Path, host_config: Path) -> None:
    """Read-only preflight: an initialized identity needs its captured master key.

    Works on legacy databases without the new table/row. Does not use process
    environment, generate identities or reveal decrypted/private material.
    """
    try:
        connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        try:
            connection.row_factory = sqlite3.Row
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='core_installation_identity'"
            ).fetchone()
            if not exists:
                return
            rows = connection.execute(
                "SELECT singleton_id, installation_id, identity_version, key_generation, key_id, public_key, encrypted_private_key, created_at FROM core_installation_identity"
            ).fetchall()
        finally:
            connection.close()
        if not rows:
            return
        if len(rows) != 1 or rows[0]["singleton_id"] != 1:
            raise ValueError("invalid singleton")
        if host_config.is_symlink() or not host_config.is_file():
            raise ValueError("missing host configuration")
        with host_config.open("rb") as source:
            data = source.read(256 * 1024 + 1)
        if len(data) > 256 * 1024:
            raise ValueError("oversized host configuration")
        keys = []
        for line in data.decode("utf-8").splitlines():
            name, separator, value = line.strip().partition("=")
            if separator and name == "AI_SETTINGS_MASTER_KEY":
                # The generated systemd environment uses unquoted values;
                # matching enclosing quotes are also accepted for edited files.
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                keys.append(value)
        if len(keys) != 1:
            raise ValueError("missing or duplicate captured master key")
        _decode_identity(SimpleNamespace(**dict(rows[0])), _cipher(keys[0]))
    except (OSError, sqlite3.Error, ValueError, InstallationIdentityError) as exc:
        raise InstallationIdentityError(
            "Installation identity recovery material is missing or invalid"
        ) from exc


def installation_identity(db: Session) -> InstallationIdentityResultV1:
    version = core_version()  # Invalid runtime metadata must not create state.
    identity, _ = _load_or_create(db)
    return InstallationIdentityResultV1(identity=identity, core_version=version)


def prove_installation_identity(
    db: Session,
    request: InstallationProofRequestV1 | dict,
    *,
    now: datetime | None = None,
) -> InstallationProofV1:
    request = InstallationProofRequestV1.model_validate(request)
    validate_proof_time(request, now or datetime.now(UTC))
    identity, private = _load_or_create(db)
    validate_proof_time(request, now or datetime.now(UTC))
    signature = private.sign(canonical_installation_proof(identity, request))
    return InstallationProofV1(
        identity=identity,
        request=request,
        signature=base64.b64encode(signature).decode("ascii"),
    )
