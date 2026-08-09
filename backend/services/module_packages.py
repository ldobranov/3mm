"""Safe validation of immutable module v2 ZIP packages."""
import hashlib, io, json, stat, zipfile
from dataclasses import dataclass
from pydantic import ValidationError
from three_mm_protocol import ModuleManifestV2, meets_minimum_version

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
    return ValidatedModulePackage(manifest, hashlib.sha256(package).hexdigest(), len(package))
