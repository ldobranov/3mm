"""Portable client helper for private authority pins and signature verification.

No Agent module runtime dependency. Bootstrap is TOFU after explicit enrollment;
an existing pin never falls back to unsigned management or another key.
"""

import os
import subprocess
import tempfile
import threading
from pathlib import Path

from pydantic import Field
from three_mm_protocol.device_platform import (
    Contract,
    DeviceLifecycle,
    DEVICE,
    CREDENTIAL,
    AuthorityProofV1,
    verify_authority,
)
from three_mm_protocol.installation_identity import InstallationIdentityV1


class AuthorityBinding(Contract):
    device_id: str = Field(pattern=DEVICE)
    credential_id: str = Field(pattern=CREDENTIAL)
    installation: InstallationIdentityV1 | None = None
    lifecycle: DeviceLifecycle = DeviceLifecycle.ENROLLMENT_PENDING
    generation: int = Field(default=1, ge=1, strict=True)


def sync_directory(path):
    if os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def verify_ed25519(key, signature, message):
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        # Already a reviewed Node dependency; no ARMv6 cryptography wheel needed.
        with tempfile.TemporaryDirectory(prefix="conerax-authority-") as temp:
            root = Path(temp)
            for name, data in {
                "key.der": bytes.fromhex("302a300506032b6570032100") + key,
                "signature": signature,
                "message": message,
            }.items():
                descriptor = os.open(
                    root / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                )
                with os.fdopen(descriptor, "wb") as target:
                    target.write(data)
            result = subprocess.run(
                [
                    "/usr/bin/openssl",
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-keyform",
                    "DER",
                    "-inkey",
                    str(root / "key.der"),
                    "-rawin",
                    "-in",
                    str(root / "message"),
                    "-sigfile",
                    str(root / "signature"),
                ],
                timeout=5,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={
                    "PATH": "/usr/bin:/bin",
                    "LC_ALL": "C",
                    "OPENSSL_CONF": "/dev/null",
                },
            )
            if result.returncode:
                raise ValueError("Authority signature is invalid")
    else:
        from cryptography.exceptions import InvalidSignature

        try:
            Ed25519PublicKey.from_public_bytes(key).verify(signature, message)
        except InvalidSignature as exc:
            raise ValueError("Authority signature is invalid") from exc


class DeviceAuthorityStore:
    def __init__(self, data_dir, device_id, credential_id):
        self.path = Path(data_dir) / "device-authority.json"
        self.device_id, self.credential_id = device_id, credential_id
        self.lock = threading.RLock()
        self.initial_history = self._history_token()
        self.initial = self.load()

    def _history_token(self):
        history = self.path.parent / "authority-recovery"
        if history.is_symlink() or (history.exists() and not history.is_dir()):
            raise ValueError("Invalid authority recovery history")
        return (
            tuple(sorted(path.name for path in history.iterdir()))
            if history.exists()
            else ()
        )

    def load(self):
        if (self.path.parent / "authority-reset.json").exists():
            raise ValueError(
                "Authority recovery is incomplete; local operator intervention required"
            )
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise ValueError("Authority storage cannot be a symbolic link")
        if not self.path.exists():
            return None
        if os.name == "posix" and (
            self.path.stat().st_mode & 0o077 or self.path.parent.stat().st_mode & 0o022
        ):
            raise ValueError("Authority storage permissions are unsafe")
        with self.path.open("rb") as source:
            data = source.read(8193)
        if len(data) > 8192:
            raise ValueError("Authority storage is oversized")
        value = AuthorityBinding.model_validate_json(data)
        if (
            value.device_id != self.device_id
            or value.credential_id != self.credential_id
        ):
            raise ValueError(
                "Authority credential binding changed; explicit recovery required"
            )
        return value

    def check_current(self):
        value = self.load()
        if (
            self._history_token() != self.initial_history
            or value != self.initial
            or (value is not None and value.lifecycle == DeviceLifecycle.UNOWNED)
        ):
            raise ValueError(
                "Authority reset/rotation detected; restart after explicit recovery"
            )
        return value

    def _write(self, binding):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as target:
                target.write(binding.model_dump_json() + "\n")
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path)
            sync_directory(self.path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def verify(self, proof, request, *, bootstrap=False):
        with self.lock:
            binding = self.check_current()
            proof = AuthorityProofV1.model_validate(proof)
            identity = binding.installation if binding else None
            if identity is None and not bootstrap:
                raise ValueError("No authority has been pinned")
            if (
                request.device_id != self.device_id
                or request.credential_id != self.credential_id
            ):
                raise ValueError("Authority challenge is for another credential")
            payload = verify_authority(
                proof, request, identity or proof.identity, verifier=verify_ed25519
            )
            if identity is None:
                binding = AuthorityBinding(
                    device_id=self.device_id,
                    credential_id=self.credential_id,
                    installation=proof.identity,
                    lifecycle=DeviceLifecycle.ACTIVE,
                    generation=binding.generation if binding else 1,
                )
                self._write(binding)
                self.initial = binding
            return payload

    def pin_local(self, installation, *, new_credential_id):
        """Trusted co-located bootstrap only, never callable through transport.

        The caller must compare installation with its local Core database. This
        preserves a pin across local credential repair without allowing key swaps.
        """
        with self.lock:
            binding = self.check_current()
            if binding is not None and binding.installation != installation:
                raise ValueError(
                    "Trusted local Core identity does not match the authority pin"
                )
            updated = AuthorityBinding(
                device_id=self.device_id,
                credential_id=new_credential_id,
                installation=installation,
                lifecycle=DeviceLifecycle.ACTIVE,
                generation=(
                    binding.generation + 1
                    if binding and binding.credential_id != new_credential_id
                    else binding.generation if binding else 1
                ),
            )
            if updated != binding:
                self._write(updated)
            # Old in-memory publishers must see rotation, not transparently adopt it.
