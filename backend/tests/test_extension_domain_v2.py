import hashlib
import io
import json
import zipfile

import pytest
from pydantic import ValidationError

from agent.module_runtime import AgentModuleRuntime, ModuleLifecycleError
from backend.services.module_packages import ModulePackageError, validate_module_package
from three_mm_protocol import EXTENSION_API_VERSION, ModuleManifestV2


def manifest(**changes):
    value = {
        "manifest_version": 2,
        "module_id": "org.3mm.extension-domain-test",
        "name": "Extension Domain Test",
        "version": "1.0.0",
        "runtimes": ["agent"],
        "entrypoints": {},
        "compatibility": {
            "protocol": "1.0",
            "extension_api": EXTENSION_API_VERSION,
            "architectures": ["aarch64"],
        },
        "capabilities": {"provides": [], "consumes": []},
        "permissions": [],
        "dependencies": {},
        "conflicts": [],
        "configuration_schema": {},
        "configuration_defaults": {},
        "health_check": {"type": "file_exists", "path": "health/ready"},
        "registrations": [],
    }
    value.update(changes)
    return value


def package(value):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("manifest.json", json.dumps(value))
        archive.writestr("health/ready", "ok")
    return out.getvalue()


def test_existing_manifest_v2_defaults_to_current_extension_api():
    value = manifest()
    value["compatibility"].pop("extension_api")

    parsed = ModuleManifestV2.model_validate(value)

    assert parsed.compatibility.extension_api == EXTENSION_API_VERSION
    assert parsed.publisher is None


def test_manifest_v2_accepts_stable_publisher_identity():
    parsed = ModuleManifestV2.model_validate(
        manifest(publisher={"id": "3mm", "name": "3mm"})
    )

    assert parsed.publisher is not None
    assert parsed.publisher.id == "3mm"


def test_manifest_v2_rejects_invalid_publisher_identity():
    with pytest.raises(ValidationError):
        ModuleManifestV2.model_validate(
            manifest(publisher={"id": "Invalid Publisher", "name": "Invalid"})
        )


def test_core_package_validation_rejects_unsupported_extension_api():
    value = manifest()
    value["compatibility"]["extension_api"] = "2.0"

    with pytest.raises(ModulePackageError, match="Extension API"):
        validate_module_package(package(value))


def test_agent_rejects_unsupported_extension_api(tmp_path):
    value = manifest()
    value["compatibility"]["extension_api"] = "2.0"
    blob = package(value)
    runtime = AgentModuleRuntime(tmp_path, architecture="aarch64")

    with pytest.raises(ModuleLifecycleError, match="Extension API"):
        runtime.install(blob, expected_sha256=hashlib.sha256(blob).hexdigest())
