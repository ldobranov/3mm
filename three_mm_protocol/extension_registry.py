"""Extension Registry Protocol v1 shared by 3mm registries and Core clients."""
from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from pydantic import Field, model_validator

from three_mm_protocol.extension_distribution import (
    ExtensionArtifactSignatureV1,
    SHA256_PATTERN,
)
from three_mm_protocol.module_manifest import (
    MODULE_ID_PATTERN,
    SEMVER_PATTERN,
    ModuleManifestV2,
    ModulePublisher,
    StrictModel,
)

REGISTRY_PROTOCOL_VERSION = 1
REGISTRY_API_PREFIX = "/v1/extensions"
RegistryChannel = Literal["stable", "beta", "dev"]


class ExtensionRegistryExtensionV1(StrictModel):
    registry_version: Literal[1] = 1
    module_id: str = Field(pattern=MODULE_ID_PATTERN, max_length=160)
    name: str = Field(min_length=1, max_length=120)
    publisher: ModulePublisher
    description: str = Field(default="", max_length=1000)


class ExtensionRegistryVersionSummaryV1(StrictModel):
    version: str = Field(pattern=SEMVER_PATTERN, max_length=64)
    channel: RegistryChannel = "stable"
    publisher_id: str = Field(min_length=1, max_length=120)
    key_id: str = Field(pattern=SHA256_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0)


class ExtensionRegistryVersionsV1(StrictModel):
    registry_version: Literal[1] = 1
    module_id: str = Field(pattern=MODULE_ID_PATTERN, max_length=160)
    versions: tuple[ExtensionRegistryVersionSummaryV1, ...] = Field(
        default=(), max_length=512
    )

    @model_validator(mode="after")
    def unique_versions(self):
        versions = [item.version for item in self.versions]
        if len(versions) != len(set(versions)):
            raise ValueError("Registry version list contains duplicate versions")
        return self


class ExtensionRegistryVersionV1(StrictModel):
    """Installable Registry metadata bound to one signed immutable artifact."""

    registry_version: Literal[1] = 1
    channel: RegistryChannel = "stable"
    manifest: ModuleManifestV2
    distribution: ExtensionArtifactSignatureV1

    @model_validator(mode="after")
    def consistent_identity(self):
        publisher = self.manifest.publisher
        artifact = self.distribution.artifact
        if publisher is None:
            raise ValueError("Registry packages require manifest publisher identity")
        if artifact.module_id != self.manifest.module_id:
            raise ValueError("Registry artifact module identity does not match manifest")
        if artifact.version != self.manifest.version:
            raise ValueError("Registry artifact version does not match manifest")
        if artifact.publisher_id != publisher.id:
            raise ValueError("Registry artifact publisher does not match manifest")
        return self


def registry_extension_path(module_id: str) -> str:
    return f"{REGISTRY_API_PREFIX}/{quote(module_id, safe='')}"


def registry_versions_path(module_id: str) -> str:
    return f"{registry_extension_path(module_id)}/versions"


def registry_version_path(module_id: str, version: str) -> str:
    return f"{registry_versions_path(module_id)}/{quote(version, safe='')}"


def registry_manifest_path(module_id: str, version: str) -> str:
    return f"{registry_version_path(module_id, version)}/manifest"


def registry_package_path(module_id: str, version: str) -> str:
    return f"{registry_version_path(module_id, version)}/package"
