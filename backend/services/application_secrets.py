"""Fail-closed encrypted credentials scoped to one application installation."""

from __future__ import annotations

import json
import os
import secrets
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from backend.db.module import ApplicationSecretReference


class ApplicationSecretError(RuntimeError):
    pass


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
    installation_id: int,
    label: str,
    credential_kind: str,
    value: dict[str, str],
) -> ApplicationSecretReference:
    normalized = validate_credential(credential_kind, value)
    encrypted = _fernet().encrypt(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    reference = ApplicationSecretReference(
        secret_ref=f"secret_{secrets.token_hex(16)}",
        application_installation_id=installation_id,
        label=label.strip(),
        credential_kind=credential_kind,
        encrypted_value=encrypted,
    )
    db.add(reference)
    db.commit()
    db.refresh(reference)
    return reference


def rotate_secret_reference(
    db: Session,
    reference: ApplicationSecretReference,
    value: dict[str, str],
) -> None:
    normalized = validate_credential(reference.credential_kind, value)
    reference.encrypted_value = _fernet().encrypt(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    reference.version += 1
    reference.rotated_at = datetime.now(UTC)
    reference.revoked_at = None
    db.commit()


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
