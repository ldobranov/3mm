import hashlib, io, json, zipfile
from pathlib import Path
import pytest
from fastapi import HTTPException
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


def test_package_rejects_duplicate_archive_paths():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest()))
        archive.writestr("manifest.json", json.dumps(manifest()))

    with pytest.raises(ModulePackageError, match="duplicate paths"):
        validate_module_package(output.getvalue())

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

def compiled_ui_manifest(**changes):
    value = manifest(
        module_id="org.3mm.clock",
        runtimes=["ui"],
        entrypoints={"ui": "compiled-ui.json"},
        compatibility={"protocol": "1.0", "architectures": ["any"]},
        permissions=[],
        registrations=[{
            "kind": "widget",
            "registration_id": "org.3mm.clock.widget",
            "metadata": {"entrypoint_id": "clock"},
        }],
        health_check={"type": "json_file", "path": "compiled-ui.json"},
    )
    value.update(changes)
    return value

def compiled_ui_definition(**changes):
    value = {
        "compiled_ui_version": 1,
        "module_id": "org.3mm.clock",
        "version": "1.0.0",
        "entrypoints": [{
            "entrypoint_id": "clock",
            "kind": "widget",
            "source": "source/frontend/ClockWidget.vue",
            "label": {"en": "Digital Clock"},
        }],
    }
    value.update(changes)
    return value

def compiled_ui_package(*, definition=None, manifest_value=None, extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest_value or compiled_ui_manifest()))
        archive.writestr("compiled-ui.json", json.dumps(definition or compiled_ui_definition()))
        archive.writestr("source/frontend/ClockWidget.vue", "<template><time>12:34:56</time></template>")
        if extra:
            archive.writestr(extra, "forbidden")
    return output.getvalue()

def test_compiled_ui_package_declares_generic_widget_source():
    validated = validate_module_package(compiled_ui_package())
    assert validated.compiled_ui is not None
    assert validated.compiled_ui.entrypoints[0].entrypoint_id == "clock"

def test_compiled_ui_package_rejects_backend_code_and_missing_sources():
    with pytest.raises(ModulePackageError, match="forbidden files"):
        validate_module_package(compiled_ui_package(extra="source/backend/clock.py"))
    broken = compiled_ui_definition()
    broken["entrypoints"][0]["source"] = "source/frontend/Missing.vue"
    with pytest.raises(ModulePackageError, match="sources are missing"):
        validate_module_package(compiled_ui_package(definition=broken))

def test_reference_clock_source_builds_as_a_valid_compiled_ui_package():
    root = Path(__file__).parents[2] / "modules" / "compiled-clock"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path in root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    validated = validate_module_package(output.getvalue())
    assert validated.compiled_ui is not None
    assert validated.compiled_ui.module_id == "org.3mm.clock"


APPLICATION_WHEEL = b"reviewed application wheel fixture"


def application_manifest(**changes):
    value = manifest(
        module_id="org.3mm.workflow-reference",
        runtimes=["core", "ui"],
        entrypoints={
            "core": "application-extension.json",
            "ui": "compiled-ui.json",
        },
        compatibility={"protocol": "1.0", "architectures": ["any"]},
        capabilities={
            "provides": ["workflow.record.approved"],
            "consumes": ["identifier.scan.v1"],
        },
        permissions=[
            "data.read",
            "data.write",
            "events.consume",
            "events.publish",
            "network.outbound",
            "process.spawn",
            "secrets.use",
        ],
        configuration_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "READER_DEVICE_ID": {"type": "string"},
                "BUSINESS_API_URL": {"type": "string", "format": "uri"},
                "BUSINESS_API_CREDENTIAL": {
                    "type": "string",
                    "x-3mm-secret-reference": True,
                },
            },
        },
        configuration_defaults={},
        registrations=[],
        health_check={"type": "json_file", "path": "application-extension.json"},
    )
    value.update(changes)
    return value


def application_definition(**changes):
    value = {
        "application_extension_version": 1,
        "module_id": "org.3mm.workflow-reference",
        "version": "1.0.0",
        "service": {
            "artifact": "service/workflow_reference-1.0.0-py3-none-any.whl",
            "artifact_sha256": hashlib.sha256(APPLICATION_WHEEL).hexdigest(),
            "entrypoint": "workflow_reference.service:create_service",
            "health_operation_id": "health",
        },
        "permissions": [
            {
                "permission_id": "records_manage",
                "label": {"en": "Manage records"},
                "description": {"en": "Approve workflow records"},
            }
        ],
        "operations": [
            {
                "operation_id": "health",
                "kind": "query",
                "audiences": ["internal"],
                "idempotency": "forbidden",
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["ok", "ready"]}
                    },
                    "required": ["status"],
                    "additionalProperties": False,
                },
            },
            {
                "operation_id": "register",
                "kind": "command",
                "audiences": ["kiosk"],
                "idempotency": "required",
            },
            {
                "operation_id": "approve",
                "kind": "command",
                "audiences": ["operator", "administrator"],
                "required_permission": "records_manage",
                "idempotency": "required",
                "emitted_events": ["workflow.record.approved"],
            },
            {
                "operation_id": "process_scan",
                "kind": "command",
                "audiences": ["internal"],
                "idempotency": "required",
            },
            {
                "operation_id": "sync_job",
                "kind": "job",
                "audiences": ["internal"],
                "idempotency": "required",
            },
        ],
        "routes": [
            {
                "route_id": "registration",
                "entrypoint_id": "registration",
                "audience": "kiosk",
                "layout": "kiosk",
            },
            {
                "route_id": "operations",
                "entrypoint_id": "operations",
                "audience": "operator",
                "required_permissions": ["records_manage"],
            },
        ],
        "event_subscriptions": [
            {
                "subscription_id": "identifier_scans",
                "event_type": "identifier.scan.v1",
                "capability_id": "identifier.scan.v1",
                "handler_operation_id": "process_scan",
                "device_scope_config_key": "READER_DEVICE_ID",
            }
        ],
        "connectors": [
            {
                "connector_id": "business_api",
                "destination_config_key": "BUSINESS_API_URL",
                "allowed_schemes": ["http", "https"],
                "authentication": "basic",
                "credential_ref_config_key": "BUSINESS_API_CREDENTIAL",
                "supports_mutations": True,
            }
        ],
        "jobs": [
            {
                "job_id": "sync",
                "handler_operation_id": "sync_job",
                "interval_seconds": 60,
            }
        ],
        "storage": {
            "schema_revision": "0001",
            "migration_entrypoint": "workflow_reference.migrations:get_migrations",
            "classifications": ["private"],
        },
    }
    value.update(changes)
    return value


def application_compiled_ui():
    return {
        "compiled_ui_version": 1,
        "module_id": "org.3mm.workflow-reference",
        "version": "1.0.0",
        "entrypoints": [
            {
                "entrypoint_id": "registration",
                "kind": "route",
                "source": "source/frontend/Registration.vue",
                "label": {"en": "Registration"},
                "route": "/workflow/register",
            },
            {
                "entrypoint_id": "operations",
                "kind": "route",
                "source": "source/frontend/Operations.vue",
                "label": {"en": "Operations"},
                "route": "/workflow/operations",
            },
        ],
    }


def application_package(*, definition=None, manifest_value=None, extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest_value or application_manifest()),
        )
        archive.writestr(
            "application-extension.json",
            json.dumps(definition or application_definition()),
        )
        archive.writestr("compiled-ui.json", json.dumps(application_compiled_ui()))
        archive.writestr(
            "service/workflow_reference-1.0.0-py3-none-any.whl",
            APPLICATION_WHEEL,
        )
        archive.writestr("source/frontend/Registration.vue", "<template />")
        archive.writestr("source/frontend/Operations.vue", "<template />")
        if extra:
            archive.writestr(extra, "forbidden")
    return output.getvalue()


def test_application_package_binds_service_ui_events_and_permissions():
    validated = validate_module_package(application_package())

    assert validated.application_extension is not None
    assert validated.compiled_ui is not None
    assert validated.application_extension.service.health_operation_id == "health"
    assert validated.application_extension.routes[0].entrypoint_id == "registration"


def test_application_compiled_routes_cannot_bypass_server_access_policy():
    compiled = application_compiled_ui()
    compiled["entrypoints"].append(
        {
            "entrypoint_id": "undeclared",
            "kind": "route",
            "source": "source/frontend/Undeclared.vue",
            "label": {"en": "Undeclared"},
            "route": "/workflow/undeclared",
        }
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(application_manifest()))
        archive.writestr("application-extension.json", json.dumps(application_definition()))
        archive.writestr("compiled-ui.json", json.dumps(compiled))
        archive.writestr("service/workflow_reference-1.0.0-py3-none-any.whl", APPLICATION_WHEEL)
        archive.writestr("source/frontend/Registration.vue", "<template />")
        archive.writestr("source/frontend/Operations.vue", "<template />")
        archive.writestr("source/frontend/Undeclared.vue", "<template />")
    with pytest.raises(ModulePackageError, match="declare access policy"):
        validate_module_package(output.getvalue())

    compiled = application_compiled_ui()
    compiled["entrypoints"][0]["requires_role"] = "admin"
    with pytest.raises(ModulePackageError, match="access belongs"):
        application_package_blob = io.BytesIO()
        with zipfile.ZipFile(application_package_blob, "w") as archive:
            archive.writestr("manifest.json", json.dumps(application_manifest()))
            archive.writestr("application-extension.json", json.dumps(application_definition()))
            archive.writestr("compiled-ui.json", json.dumps(compiled))
            archive.writestr("service/workflow_reference-1.0.0-py3-none-any.whl", APPLICATION_WHEEL)
            archive.writestr("source/frontend/Registration.vue", "<template />")
            archive.writestr("source/frontend/Operations.vue", "<template />")
        validate_module_package(application_package_blob.getvalue())


def test_application_package_rejects_identity_artifact_and_permission_mismatch():
    with pytest.raises(ModulePackageError, match="identity"):
        validate_module_package(
            application_package(
                definition=application_definition(version="2.0.0")
            )
        )

    broken = application_definition()
    broken["service"]["artifact_sha256"] = "0" * 64
    with pytest.raises(ModulePackageError, match="checksum"):
        validate_module_package(application_package(definition=broken))

    manifest_value = application_manifest(
        permissions=["data.read", "data.write", "process.spawn"]
    )
    with pytest.raises(ModulePackageError, match="permissions must match"):
        validate_module_package(
            application_package(manifest_value=manifest_value)
        )


def test_application_package_rejects_missing_capabilities_routes_and_extra_files():
    manifest_value = application_manifest(
        capabilities={"provides": ["workflow.record.approved"], "consumes": []}
    )
    with pytest.raises(ModulePackageError, match="declared as consumed"):
        validate_module_package(
            application_package(manifest_value=manifest_value)
        )

    broken = application_definition()
    broken["routes"][0]["entrypoint_id"] = "missing"
    with pytest.raises(ModulePackageError, match="compiled route entrypoints"):
        validate_module_package(application_package(definition=broken))

    with pytest.raises(ModulePackageError, match="forbidden files"):
        validate_module_package(application_package(extra="source/backend/service.py"))


def test_application_package_requires_declared_secret_safe_configuration():
    manifest_value = application_manifest(
        configuration_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        }
    )
    with pytest.raises(ModulePackageError, match="undeclared keys"):
        validate_module_package(
            application_package(manifest_value=manifest_value)
        )

    manifest_value = application_manifest()
    manifest_value["configuration_schema"]["properties"][
        "BUSINESS_API_URL"
    ] = {"type": "integer"}
    with pytest.raises(ModulePackageError, match="must be string fields"):
        validate_module_package(
            application_package(manifest_value=manifest_value)
        )

    manifest_value = application_manifest()
    manifest_value["configuration_schema"]["properties"][
        "BUSINESS_API_CREDENTIAL"
    ].pop("x-3mm-secret-reference")
    with pytest.raises(ModulePackageError, match="secret-reference"):
        validate_module_package(
            application_package(manifest_value=manifest_value)
        )

    manifest_value = application_manifest(
        configuration_defaults={"BUSINESS_API_CREDENTIAL": "secret-id"}
    )
    with pytest.raises(ModulePackageError, match="cannot have manifest defaults"):
        validate_module_package(
            application_package(manifest_value=manifest_value)
        )


@pytest.mark.asyncio
async def test_application_package_upload_is_staged_without_automatic_activation(monkeypatch, tmp_path):
    from backend.routes import modules

    class Upload:
        async def read(self, _limit):
            return application_package()

    class DB:
        def __init__(self):
            self.record = None

        def add(self, record):
            self.record = record

        def commit(self):
            pass

    settings = type("Settings", (), {"backend": type("Backend", (), {"uploads_dir": tmp_path})()})()
    monkeypatch.setattr(modules, "get_settings", lambda: settings)
    monkeypatch.setattr(modules, "compile_ui_package", lambda *_args: None)
    monkeypatch.setattr(
        modules,
        "ModulePackage",
        lambda **values: type("PackageRecord", (), values)(),
    )
    db = DB()

    result = await modules.upload_package(Upload(), object(), db)

    assert result.module_id == "org.3mm.workflow-reference"
    assert db.record is result
    assert not hasattr(result, "enabled")
