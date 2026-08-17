import io, json, zipfile
from pathlib import Path
import pytest
from backend.services.module_packages import ModulePackageError, validate_module_package

def manifest(**changes):
    value = {"manifest_version": 2, "module_id": "org.3mm.demo", "name": "Demo", "version": "1.0.0", "runtimes": ["agent"], "entrypoints": {}, "compatibility": {"protocol": "1.0", "architectures": ["aarch64"]}, "capabilities": {"provides": ["demo.ready"], "consumes": []}, "permissions": ["data.write"], "health_check": {"type": "file_exists", "path": "health/ready"}, "registrations": [{"kind": "capability", "registration_id": "demo.ready"}]}
    value.update(changes); return value

def package(value=None, extra_name="payload.txt"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(value or manifest()))
        archive.writestr(extra_name, "payload")
    return output.getvalue()

def test_valid_package_has_stable_integrity_and_contract():
    validated = validate_module_package(package(), architecture="aarch64")
    assert validated.manifest.module_id == "org.3mm.demo" and len(validated.sha256) == 64

def test_incompatible_package_is_rejected_before_install():
    with pytest.raises(ModulePackageError, match="architecture"):
        validate_module_package(package(), architecture="x86_64")
    with pytest.raises(ModulePackageError, match="Core runtime"):
        validate_module_package(package(manifest(runtimes=["core"], compatibility={"protocol":"1.0","architectures":["any"],"core":">=9.0.0"})))

def test_package_rejects_undeclared_permission_and_traversal():
    with pytest.raises(ModulePackageError, match="unsupported permissions"):
        validate_module_package(package(manifest(permissions=["root.full"])))
    with pytest.raises(ModulePackageError, match="unsafe path"):
        validate_module_package(package(extra_name="../escape"))

def runtime_manifest(**changes):
    value = manifest(
        module_id="org.3mm.contacts",
        runtimes=["ui"],
        entrypoints={"ui": "runtime-extension.json"},
        compatibility={"protocol": "1.0", "architectures": ["any"]},
        permissions=["data.read", "data.write"],
        registrations=[],
        health_check={"type": "json_file", "path": "runtime-extension.json"},
    )
    value.update(changes)
    return value

def runtime_definition(**changes):
    value = {
        "runtime_extension_version": 1,
        "module_id": "org.3mm.contacts",
        "version": "1.0.0",
        "name": {"en": "Contacts"},
        "description": {"en": "Manage contacts"},
        "entities": [{"entity_id": "contact", "label": {"en": "Contact"}, "fields": [{"field_id": "name", "label": {"en": "Name"}, "kind": "text"}]}],
        "pages": [{"page_id": "contacts", "path": "/contacts", "title": {"en": "Contacts"}, "entity_id": "contact", "view": "table", "actions": ["create", "read"]}],
        "navigation": [],
        "permissions": ["runtime.data.read", "runtime.data.write"],
    }
    value.update(changes)
    return value

def runtime_package(*, definition=None, manifest_value=None, extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest_value or runtime_manifest()))
        archive.writestr("runtime-extension.json", json.dumps(definition or runtime_definition()))
        if extra: archive.writestr(extra, "forbidden")
    return output.getvalue()

def test_runtime_package_embeds_a_strict_declarative_definition():
    validated = validate_module_package(runtime_package())
    assert validated.runtime_extension is not None
    assert validated.runtime_extension.pages[0].path == "/contacts"

def test_runtime_package_rejects_executable_files_and_identity_mismatch():
    with pytest.raises(ModulePackageError, match="forbidden files"):
        validate_module_package(runtime_package(extra="frontend/Contacts.vue"))
    with pytest.raises(ModulePackageError, match="identity"):
        validate_module_package(runtime_package(definition=runtime_definition(version="2.0.0")))

def test_runtime_package_rejects_legacy_manifest_registrations():
    with pytest.raises(ModulePackageError, match="navigation"):
        validate_module_package(runtime_package(manifest_value=runtime_manifest(
            registrations=[{"kind": "navigation", "registration_id": "org.3mm.contacts.navigation", "metadata": {"path": "/contacts", "label": "Contacts"}}]
        )))

def test_reference_contacts_source_builds_as_a_valid_runtime_package():
    root = Path(__file__).parents[2] / "modules" / "runtime-contacts"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.write(root / "manifest.json", "manifest.json")
        archive.write(root / "runtime-extension.json", "runtime-extension.json")
    validated = validate_module_package(output.getvalue())
    assert validated.runtime_extension is not None
    assert validated.runtime_extension.module_id == "org.3mm.contacts"
