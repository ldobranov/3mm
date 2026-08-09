import io, json, zipfile
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
