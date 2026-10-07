import base64
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from three_mm_protocol import (
    ExtensionArtifactSignatureV1,
    ExtensionArtifactV1,
    ExtensionRegistryVersionSummaryV1,
    ExtensionRegistryVersionV1,
    ExtensionRegistryVersionsV1,
    ModuleManifestV2,
    canonical_extension_artifact_signature,
    registry_package_path,
)


def manifest():
    return ModuleManifestV2.model_validate({
        "manifest_version": 2,
        "module_id": "org.3mm.registry-test",
        "name": "Registry Test",
        "version": "1.2.3",
        "publisher": {"id": "3mm", "name": "3mm"},
        "runtimes": ["agent"],
        "entrypoints": {},
        "compatibility": {"protocol": "1.0", "architectures": ["any"]},
        "capabilities": {"provides": [], "consumes": []},
        "permissions": [],
        "dependencies": {},
        "conflicts": [],
        "configuration_schema": {},
        "configuration_defaults": {},
        "health_check": {"type": "file_exists", "path": "health/ready"},
        "registrations": [],
    })


def distribution(value):
    private = Ed25519PrivateKey.generate()
    key_id = "1" * 64
    package = b"registry-test"
    artifact = ExtensionArtifactV1(
        module_id=value.module_id,
        version=value.version,
        publisher_id=value.publisher.id,
        sha256=hashlib.sha256(package).hexdigest(),
        size_bytes=len(package),
    )
    return ExtensionArtifactSignatureV1(
        key_id=key_id,
        artifact=artifact,
        signature=base64.b64encode(
            private.sign(canonical_extension_artifact_signature(artifact, key_id))
        ).decode("ascii"),
    )


def test_registry_version_binds_manifest_and_distribution_identity():
    value = manifest()
    version = ExtensionRegistryVersionV1(
        manifest=value,
        distribution=distribution(value),
    )

    assert version.manifest.module_id == version.distribution.artifact.module_id
    assert registry_package_path(value.module_id, value.version).endswith(
        "/org.3mm.registry-test/versions/1.2.3/package"
    )


def test_registry_version_rejects_manifest_distribution_mismatch():
    value = manifest()
    signed = distribution(value)
    changed = signed.model_copy(
        update={"artifact": signed.artifact.model_copy(update={"version": "1.2.4"})}
    )

    with pytest.raises(ValidationError, match="version"):
        ExtensionRegistryVersionV1(manifest=value, distribution=changed)


def test_registry_version_list_rejects_duplicate_versions():
    item = ExtensionRegistryVersionSummaryV1(
        version="1.0.0",
        publisher_id="3mm",
        key_id="1" * 64,
        sha256="2" * 64,
        size_bytes=123,
    )
    with pytest.raises(ValidationError, match="duplicate"):
        ExtensionRegistryVersionsV1(
            module_id="org.3mm.registry-test",
            versions=(item, item),
        )
