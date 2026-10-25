"""One paired credential/binding store for Agent and optional platform components.

The read-only mode validates existing ownership/permissions and never repairs or
changes credential files, allowing components to mount Agent state read-only.
"""
import json
import os
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, ValidationError

class DeviceCredential(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    credential_id: str = Field(pattern=r"^cred_[0-9a-f]{32}$")
    credential_secret: str = Field(min_length=32, repr=False)
    hub_endpoint: str | None = None
    api_endpoint: str | None = None


class DeviceCredentialStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "core-credential.json"
        self.binding_path = data_dir / "core-binding.json"

    def load(self, *, read_only: bool = False) -> DeviceCredential | None:
        if self.path.is_symlink() or self.binding_path.is_symlink():
            raise RuntimeError("Credential files cannot be symbolic links")
        if not self.path.exists():
            return None
        try:
            if read_only:
                for path in (self.path, self.binding_path, self.path.parent):
                    if not path.exists():
                        continue
                    info = path.lstat()
                    if path.is_symlink() or info.st_uid != os.geteuid() or info.st_mode & (0o022 if path.is_dir() else 0o077):
                        raise ValueError("Credential/binding storage is untrusted")
            else:
                os.chmod(self.path, 0o600)
            if self.path.stat().st_size > 8192:
                raise ValueError("Credential exceeds bounds")
            credential = DeviceCredential.model_validate_json(
                self.path.read_text(encoding="utf-8")
            )
            if self.binding_path.exists():
                if self.binding_path.stat().st_size > 8192:
                    raise ValueError("Credential binding exceeds bounds")
                binding = json.loads(self.binding_path.read_text(encoding="utf-8"))
                if (not isinstance(binding, dict)
                        or binding.get("credential_id") != credential.credential_id
                        or binding.get("device_id") != credential.device_id):
                    raise ValueError("Hub binding does not match the credential")
                credential = DeviceCredential.model_validate({
                    **credential.model_dump(),
                    "hub_endpoint": binding["hub_endpoint"], "api_endpoint": binding["api_endpoint"],
                })
            return credential
        except (OSError, ValueError, KeyError, ValidationError) as exc:
            raise RuntimeError(f"Cannot load Core credential from {self.path}") from exc

    def save(self, credential: DeviceCredential) -> None:
        if self.path.is_symlink() or self.binding_path.is_symlink():
            raise RuntimeError("Credential files cannot be symbolic links")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        if credential.hub_endpoint is not None:
            # Keep the legacy secret-file schema readable by rollback releases.
            binding = self.binding_path.with_suffix(".tmp")
            if binding.is_symlink():
                raise RuntimeError("Credential temporary file cannot be a symbolic link")
            binding.write_text(json.dumps({
                "device_id": credential.device_id, "credential_id": credential.credential_id,
                "hub_endpoint": credential.hub_endpoint, "api_endpoint": credential.api_endpoint,
            }) + "\n", encoding="utf-8")
            os.chmod(binding, 0o600)
            os.replace(binding, self.binding_path)
        temporary = self.path.with_suffix(".tmp")
        if temporary.is_symlink():
            raise RuntimeError("Credential temporary file cannot be a symbolic link")
        temporary.write_text(credential.model_dump_json(indent=2, exclude={"hub_endpoint", "api_endpoint"}) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)
