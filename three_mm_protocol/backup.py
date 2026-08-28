"""Versioned backup manifest contract shared by 3mm services."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from three_mm_protocol.module_manifest import SEMVER_PATTERN


BACKUP_MANIFEST_VERSION: Literal[1] = 1


class StrictBackupModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BackupCompatibilityV1(StrictBackupModel):
    application_version: str = Field(pattern=SEMVER_PATTERN)
    protocol_version: str = Field(pattern=r"^\d+\.\d+$")
    database_revision: str = Field(pattern=r"^[0-9a-z_]{1,64}$")
    architecture: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")


class BackupProtectionV1(StrictBackupModel):
    mode: Literal["none", "device-bound"]
    export_policy: Literal["downloadable", "local-only"]
    secret_material_included: bool = False

    @model_validator(mode="after")
    def protect_secret_material(self):
        if self.secret_material_included and (
            self.mode != "device-bound" or self.export_policy != "local-only"
        ):
            raise ValueError(
                "secret-bearing backups must be device-bound and local-only"
            )
        return self


class BackupEntryV1(StrictBackupModel):
    area: Literal["core", "agent", "provisioning", "host-config"]
    path: str = Field(min_length=1, max_length=512)
    sensitivity: Literal["private", "secret"]
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def safe_canonical_path(self):
        if "\\" in self.path:
            raise ValueError("backup entry paths must use POSIX separators")
        candidate = PurePosixPath(self.path)
        if candidate.is_absolute() or self.path in {".", ".."}:
            raise ValueError("backup entry path must be relative")
        if any(part in {"", ".", ".."} for part in candidate.parts):
            raise ValueError("backup entry path must be canonical and contained")
        if candidate.as_posix() != self.path:
            raise ValueError("backup entry path must be canonical")
        return self


class BackupManifestV1(StrictBackupModel):
    manifest_version: Literal[1] = BACKUP_MANIFEST_VERSION
    backup_id: str = Field(pattern=r"^bkp_\d{8}T\d{6}Z_[0-9a-f]{8}$")
    created_at: AwareDatetime
    scope: Literal["standalone-full"] = "standalone-full"
    device_id: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    device_role: Literal["standalone"] = "standalone"
    compatibility: BackupCompatibilityV1
    protection: BackupProtectionV1
    entries: tuple[BackupEntryV1, ...] = Field(min_length=1)
    total_size_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_inventory(self):
        identities = [(entry.area, entry.path) for entry in self.entries]
        if len(identities) != len(set(identities)):
            raise ValueError("backup entry paths must be unique within each area")

        expected_size = sum(entry.size_bytes for entry in self.entries)
        if self.total_size_bytes != expected_size:
            raise ValueError("backup total size does not match its entries")

        contains_secrets = any(entry.sensitivity == "secret" for entry in self.entries)
        if self.protection.secret_material_included != contains_secrets:
            raise ValueError(
                "backup protection metadata does not match entry sensitivity"
            )
        return self
