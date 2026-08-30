"""Safe validation of immutable module v2 ZIP packages."""
import hashlib, io, json, stat, zipfile
from dataclasses import dataclass
from pathlib import Path
from pydantic import ValidationError
from three_mm_protocol import (
    ApplicationExtensionV1,
    CompiledUiExtensionV1,
    ModuleManifestV2,
    RuntimeExtensionV1,
    meets_minimum_version,
)

MAX_PACKAGE_BYTES = 10 * 1024 * 1024
MAX_EXPANDED_BYTES = 40 * 1024 * 1024
MAX_FILES = 256
ALLOWED_PERMISSIONS = {
    "data.read",
    "data.write",
    "events.consume",
    "events.publish",
    "network.outbound",
    "process.spawn",
    "secrets.use",
    "hardware.inventory",
    "hardware.gpio",
}

class ModulePackageError(ValueError): pass

@dataclass(frozen=True, slots=True)
class ValidatedModulePackage:
    manifest: ModuleManifestV2
    sha256: str
    size_bytes: int
    runtime_extension: RuntimeExtensionV1 | None = None
    compiled_ui: CompiledUiExtensionV1 | None = None
    application_extension: ApplicationExtensionV1 | None = None


def _read_compiled_ui(
    archive: zipfile.ZipFile,
    manifest: ModuleManifestV2,
    package_files: set[str],
) -> tuple[CompiledUiExtensionV1, set[str]]:
    try:
        compiled_ui = CompiledUiExtensionV1.model_validate_json(
            archive.read("compiled-ui.json")
        )
    except (KeyError, ValidationError) as exc:
        raise ModulePackageError(f"invalid compiled-ui.json: {exc}") from exc
    if compiled_ui.module_id != manifest.module_id or compiled_ui.version != manifest.version:
        raise ModulePackageError("compiled UI identity must match manifest v2")

    source_files = {
        path for path in package_files if path.startswith("source/frontend/")
    }
    forbidden = sorted(
        path
        for path in source_files
        if Path(path).suffix.lower() not in {".vue", ".ts", ".js", ".css", ".json"}
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
    return compiled_ui, source_files

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
    seen_paths: set[str] = set()
    for item in infos:
        normalized = item.filename.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            raise ModulePackageError("module package contains an unsafe path")
        if normalized in seen_paths:
            raise ModulePackageError("module package contains duplicate paths")
        seen_paths.add(normalized)
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
    package_files = {
        item.filename.replace("\\", "/") for item in infos if not item.is_dir()
    }
    runtime_extension = None
    compiled_ui = None
    application_extension = None
    if manifest.entrypoints.get("ui") == "runtime-extension.json":
        if set(manifest.runtimes) != {"ui"}:
            raise ModulePackageError("runtime extensions may only target the UI runtime")
        if manifest.registrations:
            raise ModulePackageError(
                "runtime extension navigation must be declared only in runtime-extension.json"
            )
        allowed_files = {"manifest.json", "runtime-extension.json"}
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
    elif manifest.entrypoints.get("core") == "application-extension.json":
        if set(manifest.runtimes) not in ({"core"}, {"core", "ui"}):
            raise ModulePackageError(
                "application extensions may target only Core and optional UI runtimes"
            )
        if manifest.registrations:
            raise ModulePackageError(
                "application extension registrations belong in application-extension.json"
            )
        try:
            application_extension = ApplicationExtensionV1.model_validate_json(
                archive.read("application-extension.json")
            )
        except (KeyError, ValidationError) as exc:
            raise ModulePackageError(
                f"invalid application-extension.json: {exc}"
            ) from exc
        if (
            application_extension.module_id != manifest.module_id
            or application_extension.version != manifest.version
        ):
            raise ModulePackageError(
                "application extension identity must match manifest v2"
            )

        service_artifact = application_extension.service.artifact
        try:
            service_payload = archive.read(service_artifact)
        except KeyError as exc:
            raise ModulePackageError(
                "application extension service artifact is missing"
            ) from exc
        if hashlib.sha256(service_payload).hexdigest() != (
            application_extension.service.artifact_sha256
        ):
            raise ModulePackageError(
                "application extension service artifact checksum is invalid"
            )

        consumed_capabilities = set(manifest.capabilities.consumes)
        missing_capabilities = sorted(
            {
                item.capability_id
                for item in application_extension.event_subscriptions
            }
            - consumed_capabilities
        )
        if missing_capabilities:
            raise ModulePackageError(
                "application event capabilities must be declared as consumed: "
                + ", ".join(missing_capabilities)
            )
        emitted_events = {
            event_type
            for operation in application_extension.operations
            for event_type in operation.emitted_events
        }
        missing_provided = sorted(
            emitted_events - set(manifest.capabilities.provides)
        )
        if missing_provided:
            raise ModulePackageError(
                "application emitted events must be declared as provided: "
                + ", ".join(missing_provided)
            )

        configuration = manifest.configuration_schema
        properties = configuration.get("properties")
        if (
            configuration.get("type") != "object"
            or configuration.get("additionalProperties") is not False
            or not isinstance(properties, dict)
        ):
            raise ModulePackageError(
                "application configuration must be a strict object schema"
            )
        referenced_config = {
            item.device_scope_config_key
            for item in application_extension.event_subscriptions
        }
        referenced_config.update(
            item.destination_config_key
            for item in application_extension.connectors
        )
        referenced_config.update(
            item.credential_ref_config_key
            for item in application_extension.connectors
            if item.credential_ref_config_key is not None
        )
        missing_config = sorted(referenced_config - set(properties))
        if missing_config:
            raise ModulePackageError(
                "application configuration references undeclared keys: "
                + ", ".join(missing_config)
            )
        invalid_config = sorted(
            key
            for key in referenced_config
            if not isinstance(properties[key], dict)
            or properties[key].get("type") != "string"
        )
        if invalid_config:
            raise ModulePackageError(
                "application configuration references must be string fields: "
                + ", ".join(invalid_config)
            )
        secret_config = {
            item.credential_ref_config_key
            for item in application_extension.connectors
            if item.credential_ref_config_key is not None
        }
        unsafe_secret_fields = sorted(
            key
            for key in secret_config
            if not isinstance(properties[key], dict)
            or properties[key].get("x-3mm-secret-reference") is not True
        )
        if unsafe_secret_fields:
            raise ModulePackageError(
                "connector credentials must use secret-reference configuration: "
                + ", ".join(unsafe_secret_fields)
            )
        unknown_defaults = sorted(
            set(manifest.configuration_defaults) - set(properties)
        )
        if unknown_defaults:
            raise ModulePackageError(
                "application configuration defaults contain undeclared keys"
            )
        if secret_config & set(manifest.configuration_defaults):
            raise ModulePackageError(
                "application secret references cannot have manifest defaults"
            )

        expected_permissions = {"data.read", "data.write", "process.spawn"}
        if application_extension.event_subscriptions:
            expected_permissions.add("events.consume")
        if emitted_events:
            expected_permissions.add("events.publish")
        if application_extension.connectors:
            expected_permissions.add("network.outbound")
        if any(
            item.credential_ref_config_key is not None
            for item in application_extension.connectors
        ):
            expected_permissions.add("secrets.use")
        if set(manifest.permissions) != expected_permissions:
            raise ModulePackageError(
                "application extension permissions must match manifest v2"
            )

        allowed_files = {
            "manifest.json",
            "application-extension.json",
            service_artifact,
        }
        if "ui" in manifest.runtimes:
            if manifest.entrypoints.get("ui") != "compiled-ui.json":
                raise ModulePackageError(
                    "application UI runtime requires compiled-ui.json"
                )
            compiled_ui, source_files = _read_compiled_ui(
                archive,
                manifest,
                package_files,
            )
            allowed_files.add("compiled-ui.json")
            allowed_files.update(source_files)
            compiled_routes = {
                item.entrypoint_id
                for item in compiled_ui.entrypoints
                if item.kind == "route"
            }
            declared_routes = {
                item.entrypoint_id for item in application_extension.routes
            }
            missing_routes = sorted(
                declared_routes - compiled_routes
            )
            if missing_routes:
                raise ModulePackageError(
                    "application routes require compiled route entrypoints: "
                    + ", ".join(missing_routes)
                )
            undeclared_routes = sorted(compiled_routes - declared_routes)
            if undeclared_routes:
                raise ModulePackageError(
                    "compiled application routes must declare access policy: "
                    + ", ".join(undeclared_routes)
                )
            if any(
                item.kind == "route" and item.requires_role is not None
                for item in compiled_ui.entrypoints
            ):
                raise ModulePackageError(
                    "application route access belongs in application-extension.json"
                )
        elif application_extension.routes:
            raise ModulePackageError("application routes require the UI runtime")

        unexpected = sorted(package_files - allowed_files)
        if unexpected:
            raise ModulePackageError(
                "application extension contains forbidden files: "
                + ", ".join(unexpected)
            )
    elif manifest.entrypoints.get("ui") == "compiled-ui.json":
        if set(manifest.runtimes) != {"ui"}:
            raise ModulePackageError("compiled UI source packages may only target the UI runtime")
        compiled_ui, source_files = _read_compiled_ui(
            archive,
            manifest,
            package_files,
        )
        allowed_metadata = {"manifest.json", "compiled-ui.json"}
        forbidden = sorted(package_files - allowed_metadata - source_files)
        if forbidden:
            raise ModulePackageError(
                f"compiled UI source package contains forbidden files: {', '.join(forbidden)}"
            )
    return ValidatedModulePackage(
        manifest=manifest,
        sha256=hashlib.sha256(package).hexdigest(),
        size_bytes=len(package),
        runtime_extension=runtime_extension,
        compiled_ui=compiled_ui,
        application_extension=application_extension,
    )
