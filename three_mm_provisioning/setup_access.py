"""Short-lived, console-issued setup capabilities. Only digests reach disk."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

from three_mm_provisioning.persistence import ProvisioningSnapshot
from three_mm_provisioning.setup_journal import atomic_json


def fingerprint(snapshot: ProvisioningSnapshot | None) -> str:
    # An interrupted initial attempt is still the same unconfigured device.
    value = snapshot.to_dict() if snapshot and snapshot.role else None
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class FileSetupAccessStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "setup-access.json"

    def issue(self, snapshot: ProvisioningSnapshot | None, *, ttl: int = 900) -> str:
        if not 1 <= ttl <= 1800:
            raise ValueError("Invalid access lifetime")
        token = secrets.token_urlsafe(32)
        atomic_json(self.path, {"digest": hashlib.sha256(token.encode()).hexdigest(),
                               "expires": time.time() + ttl, "binding": fingerprint(snapshot)})
        return token

    def valid(self, token: str, snapshot: ProvisioningSnapshot | None) -> bool:
        if not 20 <= len(token) <= 128:
            return False
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            return (time.time() < record["expires"]
                    and hmac.compare_digest(record["binding"], fingerprint(snapshot))
                    and hmac.compare_digest(record["digest"], hashlib.sha256(token.encode()).hexdigest()))
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def revoke(self) -> None:
        self.path.unlink(missing_ok=True)
