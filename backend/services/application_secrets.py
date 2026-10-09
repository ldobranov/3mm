"""Fail-closed encrypted credentials scoped to one application installation."""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.module import ApplicationSecretReference
from backend.services.authority_metadata import ApplicationAuthoritySnapshot, AuthorityMutation


class ApplicationSecretError(RuntimeError):
    pass


@dataclass(frozen=True)
class SecretAuthoritySnapshot:
    application: ApplicationAuthoritySnapshot
    id: int
    secret_ref: str
    credential_kind: str
    version: int
    revoked_at: datetime | None


def read_secret_authority(
    db: Session, application: ApplicationAuthoritySnapshot, secret_ref: str
) -> SecretAuthoritySnapshot | None:
    """Preflight identity only; never read ciphertext or decrypt for revision checks."""
    with db.no_autoflush:
        row = db.execute(
            select(
                ApplicationSecretReference.id,
                ApplicationSecretReference.secret_ref,
                ApplicationSecretReference.credential_kind,
                ApplicationSecretReference.version,
                ApplicationSecretReference.revoked_at,
            ).where(
                ApplicationSecretReference.application_installation_id == application.installation_id,
                ApplicationSecretReference.secret_ref == secret_ref,
            )
        ).one_or_none()
    return None if row is None else SecretAuthoritySnapshot(application, *row)


def _current_reference(db, expected, authority):
    authority.require_session(db)
    authority.lock_application(expected.application)
    reference = db.scalar(
        select(ApplicationSecretReference).where(
            ApplicationSecretReference.id == expected.id,
            ApplicationSecretReference.application_installation_id == expected.application.installation_id,
        ).execution_options(populate_existing=True)
    )
    if reference is None or (
        reference.secret_ref, reference.credential_kind, reference.version, reference.revoked_at
    ) != (expected.secret_ref, expected.credential_kind, expected.version, expected.revoked_at):
        authority.reject()
    return reference


def _fernet() -> Fernet:
    key = os.getenv("AI_SETTINGS_MASTER_KEY", "").strip()
    if not key:
        raise ApplicationSecretError("Application secret encryption key is unavailable")
    try:
        return Fernet(key.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ApplicationSecretError("Application secret encryption key is invalid") from exc


def validate_credential(kind: str, value: dict[str, str]) -> dict[str, str]:
    allowed = {
        "basic": {"username", "password"},
        "bearer": {"token"},
        "api_key": {"value", "header"},
    }
    if kind not in allowed or set(value) != allowed[kind]:
        raise ApplicationSecretError("Credential fields do not match its authentication kind")
    normalized = {key: item.strip() for key, item in value.items()}
    if any(not item or len(item) > 4096 for item in normalized.values()):
        raise ApplicationSecretError("Credential values are empty or too large")
    if kind == "api_key":
        header = normalized["header"]
        if not header.lower().startswith("x-") or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
            for character in header
        ):
            raise ApplicationSecretError("API key header must be a safe X-* header")
    return normalized


def create_secret_reference(
    db: Session,
    *,
    application: ApplicationAuthoritySnapshot,
    label: str,
    credential_kind: str,
    value: dict[str, str],
    authority: AuthorityMutation,
) -> ApplicationSecretReference:
    """Create an unused credential inside the caller's guarded/audited transaction."""
    authority.require_session(db)
    authority.lock_application(application)
    normalized = validate_credential(credential_kind, value)
    encrypted = _fernet().encrypt(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    reference = ApplicationSecretReference(
        secret_ref=f"secret_{secrets.token_hex(16)}",
        application_installation_id=application.installation_id,
        label=label.strip(),
        credential_kind=credential_kind,
        encrypted_value=encrypted,
    )
    db.add(reference)
    db.flush()
    return reference


def rotate_secret_reference(
    db: Session,
    expected: SecretAuthoritySnapshot,
    value: dict[str, str],
    *,
    authority: AuthorityMutation,
) -> ApplicationSecretReference:
    reference = _current_reference(db, expected, authority)
    normalized = validate_credential(reference.credential_kind, value)
    reference.encrypted_value = _fernet().encrypt(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    reference.version += 1
    reference.rotated_at = datetime.now(UTC)
    reference.revoked_at = None
    authority.advance_application_epoch(expected.application)
    db.flush()
    return reference


def revoke_secret_reference(
    db: Session, expected: SecretAuthoritySnapshot, *, authority: AuthorityMutation
) -> ApplicationSecretReference:
    reference = _current_reference(db, expected, authority)
    if reference.revoked_at is None:
        reference.revoked_at = datetime.now(UTC)
        authority.advance_application_epoch(expected.application)
        db.flush()
    return reference


def decrypt_secret_reference(reference: ApplicationSecretReference) -> dict[str, str]:
    if reference.revoked_at is not None:
        raise ApplicationSecretError("Application credential is revoked")
    try:
        value = json.loads(
            _fernet().decrypt(reference.encrypted_value.encode("ascii")).decode("utf-8")
        )
    except (InvalidToken, UnicodeError, ValueError, TypeError) as exc:
        raise ApplicationSecretError("Application credential cannot be decrypted") from exc
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise ApplicationSecretError("Application credential is invalid")
    return validate_credential(reference.credential_kind, value)
