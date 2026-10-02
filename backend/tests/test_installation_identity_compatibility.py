import pytest
from fastapi import HTTPException

from backend.services import module_packages
from backend.services.application_extensions import (
    ApplicationGatewayError,
    load_application_definition,
)
from backend.services.module_packages import ModulePackageError, validate_module_package
from backend.tests.test_module_packages import (
    application_definition,
    application_manifest,
    application_package,
    manifest,
    package,
)


def identity_package(*, sdk_version="1.1", platform_permissions=None):
    definition = application_definition(
        platform_permissions=(
            platform_permissions
            if platform_permissions is not None
            else ["installation.identity.read", "installation.identity.prove"]
        )
    )
    definition["service"]["sdk_version"] = sdk_version
    manifest_value = application_manifest()
    manifest_value["permissions"] += definition["platform_permissions"]
    manifest_value["compatibility"]["core"] = ">=0.3.0"
    return application_package(definition=definition, manifest_value=manifest_value)


def test_actual_core_version_not_legacy_default_is_checked(monkeypatch):
    blob = identity_package()
    assert (
        validate_module_package(blob).application_extension.service.sdk_version == "1.1"
    )
    monkeypatch.setattr(module_packages, "actual_core_version", lambda: "0.2.0")
    with pytest.raises(ModulePackageError, match="incompatible Core runtime version"):
        validate_module_package(blob)
    # Explicit versions still support deterministic offline compatibility checks.
    assert (
        validate_module_package(
            blob, core_version="0.3.0-beta.30"
        ).application_extension
        is not None
    )


def test_legacy_sdk_is_preserved_and_new_permissions_are_explicit():
    assert (
        validate_module_package(
            application_package()
        ).application_extension.service.sdk_version
        == "1.0"
    )
    for sdk, scopes in (
        ("1.0", ["installation.identity.read"]),
        ("9.0", []),
        ("1.1", ["installation.identity.read"] * 2),
        ("1.1", ["installation.commands"]),
    ):
        with pytest.raises(ModulePackageError):
            validate_module_package(
                identity_package(sdk_version=sdk, platform_permissions=scopes)
            )
    with pytest.raises(ModulePackageError, match="require an application extension"):
        validate_module_package(
            package(manifest(permissions=["installation.identity.read"]))
        )


def test_identity_permissions_must_match_both_manifests():
    definition = application_definition(
        platform_permissions=["installation.identity.read"]
    )
    definition["service"]["sdk_version"] = "1.1"
    with pytest.raises(ModulePackageError, match="permissions must match"):
        validate_module_package(application_package(definition=definition))


@pytest.mark.asyncio
async def test_upload_and_reload_preserve_exact_compatibility_rejection(
    monkeypatch, tmp_path
):
    from backend.routes import modules

    blob = identity_package()
    monkeypatch.setattr(module_packages, "actual_core_version", lambda: "0.2.0")

    class Upload:
        async def read(self, _limit):
            return blob

    with pytest.raises(
        HTTPException, match="incompatible Core runtime version"
    ) as error:
        await modules.upload_package(Upload(), object(), None)
    assert error.value.status_code == 422
    path = tmp_path / "module.zip"
    path.write_bytes(blob)
    record = type("Package", (), {"file_path": str(path)})()
    with pytest.raises(
        HTTPException, match="incompatible Core runtime version"
    ) as error:
        modules._validated_compiled_package(record)
    assert error.value.status_code == 409
    with pytest.raises(
        ApplicationGatewayError, match="incompatible Core runtime version"
    ):
        load_application_definition(record)


def test_missing_runtime_version_fails_closed_without_fallback(monkeypatch, tmp_path):
    from backend import version

    monkeypatch.setattr(version, "VERSION_FILE", tmp_path / "missing-version")
    with pytest.raises(ModulePackageError, match="unavailable or invalid"):
        validate_module_package(identity_package())
    path = tmp_path / "invalid-version"
    path.write_text("not-a-version", encoding="utf-8")
    monkeypatch.setattr(version, "VERSION_FILE", path)
    with pytest.raises(ModulePackageError, match="unavailable or invalid"):
        validate_module_package(identity_package())
