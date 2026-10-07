"""Safe validation of immutable module v2 ZIP packages."""
import hashlib, io, json, stat, zipfile, zlib
from dataclasses import dataclass
from pathlib import Path
from pydantic import ValidationError
from backend.version import core_version as actual_core_version
from backend.services.theme_assets import validate_theme_assets
from three_mm_protocol.theme_extension_v2 import ThemeExtensionV2
from three_mm_protocol import (
    EXTENSION_API_VERSION,
    ApplicationExtensionV1,
    CompiledUiExtensionV1,
    ModuleManifestV2,
    RuntimeExtensionV1,
    ThemeExtensionV1,
    module_compatibility_issues,
)

MAX_PACKAGE_BYTES = 10 * 1024 * 1024
MAX_EXPANDED_BYTES = 40 * 1024 * 1024
MAX_FILES = 256
MAX_THEME_DEFINITION_BYTES = 64 * 1024
ALLOWED_PERMISSIONS = {
    "capabilities.invoke",
    "data.read",
    "data.write",
    "events.consume",
    "events.publish",
    "network.outbound",
    "process.spawn",
    "secrets.use",
    "hardware.inventory",
    "hardware.gpio",
    "installation.identity.read",
    "installation.identity.prove",
    "installation.peers.enroll",
    "installation.peers.receive",
    "installation.peers.report",
    "installation.status.read",
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
    theme_extension: ThemeExtensionV1 | ThemeExtensionV2 | None = None


def _read_theme_extension(
    archive: zipfile.ZipFile,
    manifest: ModuleManifestV2,
    package_files: set[str],
) -> ThemeExtensionV1 | ThemeExtensionV2:
    if (
        manifest.runtimes != ("ui",)
        or manifest.entrypoints != {"ui": "theme-extension.json"}
    ):
        raise ModulePackageError("theme extensions require only the declarative UI entrypoint")
    if manifest.permissions or manifest.registrations:
        raise ModulePackageError("theme extensions cannot declare permissions or registrations")
    if manifest.capabilities.provides or manifest.capabilities.consumes:
        raise ModulePackageError("theme extensions cannot provide or consume device capabilities")
    if (
        manifest.dependencies or manifest.conflicts or manifest.configuration_schema
        or manifest.configuration_defaults
    ):
        raise ModulePackageError("theme extensions cannot declare dependencies or configuration")
    if manifest.compatibility.architectures != ("any",):
        raise ModulePackageError("theme extensions must be architecture-independent")
    if (
        manifest.health_check.type != "json_file"
        or manifest.health_check.path != "theme-extension.json"
    ):
        raise ModulePackageError("theme extension health check must reference its definition")
    try:
        if archive.getinfo("theme-extension.json").file_size > MAX_THEME_DEFINITION_BYTES:
            raise ModulePackageError("theme definition exceeds its size limit")
        definition = json.loads(archive.read("theme-extension.json"))
        model = ThemeExtensionV2 if isinstance(definition, dict) and definition.get("theme_extension_version") == 2 else ThemeExtensionV1
        theme = model.model_validate(definition)
        if isinstance(theme, ThemeExtensionV2):
            validate_theme_assets(archive, theme)
        elif package_files != {"manifest.json", "theme-extension.json"}:
            raise ModulePackageError("theme extension contains forbidden files")
    except (KeyError, ValueError, zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError) as exc:
        raise ModulePackageError(f"invalid theme-extension.json: {exc}") from exc
    if theme.module_id != manifest.module_id or theme.version != manifest.version:
        raise ModulePackageError("theme extension identity must match manifest v2")
    return theme


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

def validate_module_package(
    package: bytes,
    *,
    architecture: str | None = None,
    protocol_version: str = "1.0",
    extension_api_version: str = EXTENSION_API_VERSION,
    core_version: str | None = None,
) -> ValidatedModulePackage:
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
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ModulePackageError("module package manifest cannot be read") from exc
    try:
        manifest = ModuleManifestV2.model_validate(json.loads(raw_manifest))
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
        raise ModulePackageError(f"invalid manifest v2: {exc}") from exc
    unsupported = sorted(set(manifest.permissions) - ALLOWED_PERMISSIONS)
    if unsupported:
        raise ModulePackageError(f"unsupported permissions: {', '.join(unsupported)}")
    runtime_version = None
    if "core" in manifest.runtimes:
        try:
            runtime_version = core_version if core_version is not None else actual_core_version()
        except (TypeError, ValueError) as exc:
            raise ModulePackageError("Core runtime version is unavailable or invalid") from exc
    compatibility_issues = module_compatibility_issues(
        manifest,
        runtime="core",
        runtime_version=runtime_version,
        architecture=architecture,
        protocol_version=protocol_version,
        extension_api_version=extension_api_version,
    )
    if "protocol" in compatibility_issues:
        raise ModulePackageError("incompatible protocol version")
    if "extension_api" in compatibility_issues:
        raise ModulePackageError("incompatible Extension API version")
    if "runtime_version_invalid" in compatibility_issues:
        raise ModulePackageError("Core runtime version is unavailable or invalid")
    if "runtime_version" in compatibility_issues:
        raise ModulePackageError("incompatible Core runtime version")
    if "architecture" in compatibility_issues:
        raise ModulePackageError("incompatible CPU architecture")
    package_files = {
        item.filename.replace("\\", "/") for item in infos if not item.is_dir()
    }
    runtime_extension = None
    compiled_ui = None
    application_extension = None
    theme_extension = None
    if (
        manifest.entrypoints.get("ui") == "theme-extension.json"
        or "theme-extension.json" in package_files
    ):
        theme_extension = _read_theme_extension(archive, manifest, package_files)
    elif manifest.entrypoints.get("ui") == "runtime-extension.json":
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
        if {item.capability_id for item in application_extension.command_bindings} - consumed_capabilities:
            raise ModulePackageError('Application command capabilities must be declared as consumed')
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
        referenced_config.update(item.target_device_config_key for item in application_extension.command_bindings)
        referenced_config.update(item.sensor_device_config_key for item in application_extension.command_bindings if item.sensor_device_config_key)
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
        expected_permissions.update(application_extension.platform_permissions)
        if application_extension.command_bindings:
            expected_permissions.add('capabilities.invoke')
        if application_extension.event_subscriptions:
            expected_permissions.add("events.consume")
        if emitted_events:
            expected_permissions.add("events.publish")
        if application_extension.connectors:
            expected_permissions.add("network.outbound")
        if {"installation.peers.enroll", "installation.peers.report"} & set(application_extension.platform_permissions):
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
    if any(item.startswith("installation.") for item in manifest.permissions) and application_extension is None:
        raise ModulePackageError("installation identity permissions require an application extension")
    return ValidatedModulePackage(
        manifest=manifest,
        sha256=hashlib.sha256(package).hexdigest(),
        size_bytes=len(package),
        runtime_extension=runtime_extension,
        compiled_ui=compiled_ui,
        application_extension=application_extension,
        theme_extension=theme_extension,
    )
