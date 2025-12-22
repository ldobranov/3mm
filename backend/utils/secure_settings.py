from __future__ import annotations

import os
from typing import Optional


class SecureSettingsError(RuntimeError):
    pass


def _get_master_key() -> str:
    """Master key for encrypting secrets stored in DB.

    Must be a Fernet key (urlsafe base64-encoded 32-byte key), example:
      export AI_SETTINGS_MASTER_KEY='...'
    """

    # Correct env var name:
    key = os.getenv("AI_SETTINGS_MASTER_KEY")

    # Simpler fallback: allow plaintext mode if the master key is not configured.
    # This keeps the app usable in dev environments.
    return key or ""


def encrypt_secret(plaintext: Optional[str]) -> Optional[str]:
    if plaintext is None:
        return None
    if plaintext == "":
        return ""

    master_key = _get_master_key()
    if not master_key:
        # Plaintext mode
        return plaintext

    try:
        from cryptography.fernet import Fernet
    except Exception as e:  # pragma: no cover
        raise SecureSettingsError(f"cryptography is required for encryption: {e}")

    f = Fernet(master_key.encode("utf-8"))
    token = f.encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(ciphertext: Optional[str]) -> Optional[str]:
    if ciphertext is None:
        return None
    if ciphertext == "":
        return ""

    master_key = _get_master_key()
    if not master_key:
        # Plaintext mode
        return ciphertext

    try:
        from cryptography.fernet import Fernet
    except Exception as e:  # pragma: no cover
        raise SecureSettingsError(f"cryptography is required for decryption: {e}")

    f = Fernet(master_key.encode("utf-8"))
    plaintext = f.decrypt(ciphertext.encode("utf-8"))
    return plaintext.decode("utf-8")
