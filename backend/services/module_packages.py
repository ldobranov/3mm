"""Safe validation of immutable module v2 ZIP packages."""
import hashlib, io, json, stat, zipfile
from dataclasses import dataclass
from pathlib import Path
from pydantic import ValidationError
from three_mm_protocol import (
    CompiledUiExtensionV1,
    ModuleManifestV2,
    RuntimeExtensionV1,
    meets_minimum_version,
)

MAX_PACKAGE_BYTES = 10 * 1024 * 1024
MAX_EXPANDED_BYTES = 40 * 1024 * 1024
MAX_FILES = 256
ALLOWED_PERMISSIONS = {"data.read", "data.write", "events.publish", "network.outbound", "process.spawn", "hardware.inventory", "hardware.gpio"}

class ModulePackageError(ValueError): pass

@dataclass(frozen=True, slots=True)
class ValidatedModulePackage:
    manifest: ModuleManifestV2
    sha256: str
    size_bytes: int
    runtime_extension: RuntimeExtensionV1 | None = None
    compiled_ui: CompiledUiExtensionV1 | None = None

def validate_module_package(package: bytes, *, architecture: str | None = None, protocol_version: str = "1.0", core_version: str = "0.1.0") -> ValidatedModulePackage:
    if not package or len(package) > MAX_PACKAGE_BYTES:
        raise ModulePackageError("module package size is outside the allowed range")
    try:
        archive = zipfile.ZipFile(io.BytesIO(package))
    except zipfile.BadZipFile as exc:
        raise ModulePackageError("module package is not a valid ZIP archive") from exc
    infos = archive.infolist()
    if len(infos) > MAX_FILES or sum(item.file_size for item in infos) > MAX_EXPANDED_BYTES:
        raise ModulePackageError("module package expands beyond its limits")
    for item in infos:
        normalized = item.filename.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            raise ModulePackageError("module package contains an unsafe path")
        if stat.S_ISLNK(item.external_attr >> 16):
            raise ModulePackageError("module package cannot contain symbolic links")
    try:
        raw_manifest = archive.read("manifest.json")
    except KeyError as exc:
        raise ModulePackageError("manifest.json is required at package root") from exc
    try:
        manifest = ModuleManifestV2.model_validate(json.loads(raw_manifest))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ModulePackageError(f"invalid manifest v2: {exc}") from exc
    unsupported = sorted(set(manifest.permissions) - ALLOWED_PERMISSIONS)
    if unsupported:
        raise ModulePackageError(f"unsupported permissions: {', '.join(unsupported)}")
    if manifest.compatibility.protocol != protocol_version:
        raise ModulePackageError("incompatible protocol version")
    if "core" in manifest.runtimes and not meets_minimum_version(core_version, manifest.compatibility.core):
        raise ModulePackageError("incompatible Core runtime version")
    if architecture and architecture not in manifest.compatibility.architectures and "any" not in manifest.compatibility.architectures:
        raise ModulePackageError("incompatible CPU architecture")
    runtime_extension = None
    compiled_ui = None
    if manifest.entrypoints.get("ui") == "runtime-extension.json":
        if set(manifest.runtimes) != {"ui"}:
            raise ModulePackageError("runtime extensions may only target the UI runtime")
        if manifest.registrations:
            raise ModulePackageError(
                "runtime extension navigation must be declared only in runtime-extension.json"
            )
        allowed_files = {"manifest.json", "runtime-extension.json"}
        package_files = {item.filename.replace("\\", "/") for item in infos if not item.is_dir()}
        unexpected = sorted(package_files - allowed_files)
        if unexpected:
            raise ModulePackageError(
                f"runtime extension contains forbidden files: {', '.join(unexpected)}"
            )
        try:
            runtime_extension = RuntimeExtensionV1.model_validate_json(
                archive.read("runtime-extension.json")
            )
        except (KeyError, ValidationError) as exc:
            raise ModulePackageError(f"invalid runtime-extension.json: {exc}") from exc
        if (
            runtime_extension.module_id != manifest.module_id
            or runtime_extension.version != manifest.version
        ):
            raise ModulePackageError("runtime extension identity must match manifest v2")
        expected_permissions = {"data.read"}
        if "runtime.data.write" in runtime_extension.permissions:
            expected_permissions.add("data.write")
        if set(manifest.permissions) != expected_permissions:
            raise ModulePackageError("runtime extension permissions must match manifest v2")
    elif manifest.entrypoints.get("ui") == "compiled-ui.json":
        if set(manifest.runtimes) != {"ui"}:
            raise ModulePackageError("compiled UI source packages may only target the UI runtime")
        try:
            compiled_ui = CompiledUiExtensionV1.model_validate_json(
                archive.read("compiled-ui.json")
            )
        except (KeyError, ValidationError) as exc:
            raise ModulePackageError(f"invalid compiled-ui.json: {exc}") from exc
        if compiled_ui.module_id != manifest.module_id or compiled_ui.version != manifest.version:
            raise ModulePackageError("compiled UI identity must match manifest v2")

        package_files = {item.filename.replace("\\", "/") for item in infos if not item.is_dir()}
        allowed_metadata = {"manifest.json", "compiled-ui.json"}
        source_files = package_files - allowed_metadata
        forbidden = sorted(
            path
            for path in source_files
            if not path.startswith("source/frontend/")
            or Path(path).suffix.lower() not in {".vue", ".ts", ".js", ".css", ".json"}
        )
        if forbidden:
            raise ModulePackageError(
                f"compiled UI source package contains forbidden files: {', '.join(forbidden)}"
            )
        missing_sources = sorted(
            item.source for item in compiled_ui.entrypoints if item.source not in package_files
        )
        if missing_sources:
            raise ModulePackageError(
                f"compiled UI entrypoint sources are missing: {', '.join(missing_sources)}"
            )
    return ValidatedModulePackage(
        manifest,
        hashlib.sha256(package).hexdigest(),
        len(package),
        runtime_extension,
        compiled_ui,
    )
