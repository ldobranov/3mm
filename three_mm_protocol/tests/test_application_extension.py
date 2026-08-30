import pytest
from pydantic import ValidationError

from three_mm_protocol import ApplicationExtensionV1


def definition(**changes):
    value = {
        "application_extension_version": 1,
        "module_id": "org.3mm.workflow-reference",
        "version": "1.0.0",
        "service": {
            "artifact": "service/workflow_reference-1.0.0-py3-none-any.whl",
            "artifact_sha256": "a" * 64,
            "entrypoint": "workflow_reference.service:create_service",
            "health_operation_id": "health",
        },
        "permissions": [
            {
                "permission_id": "records_manage",
                "label": {"en": "Manage records"},
                "description": {"en": "Approve and update workflow records"},
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
            {
                "operation_id": "retention_job",
                "kind": "job",
                "audiences": ["internal"],
                "idempotency": "required",
            },
            {
                "operation_id": "export_data",
                "kind": "command",
                "audiences": ["administrator"],
                "idempotency": "required",
            },
            {
                "operation_id": "erase_data",
                "kind": "command",
                "audiences": ["administrator"],
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
            },
            {
                "job_id": "retention",
                "handler_operation_id": "retention_job",
                "interval_seconds": 86400,
            },
        ],
        "storage": {
            "schema_revision": "0001",
            "migration_entrypoint": "workflow_reference.migrations:get_migrations",
            "classifications": ["private", "secret"],
            "contains_personal_data": True,
            "retention_operation_id": "retention_job",
            "export_operation_id": "export_data",
            "erasure_operation_id": "erase_data",
        },
    }
    value.update(changes)
    return value


def test_valid_application_extension_contract_covers_business_service_boundaries():
    application = ApplicationExtensionV1.model_validate(definition())

    assert application.service.sdk_version == "1.0"
    assert application.routes[0].audience == "kiosk"
    assert application.event_subscriptions[0].capability_id == "identifier.scan.v1"
    assert application.connectors[0].credential_ref_config_key == "BUSINESS_API_CREDENTIAL"
    assert application.storage.contains_personal_data is True


def test_unknown_or_executable_top_level_fields_are_rejected():
    value = definition(script="arbitrary code")

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ApplicationExtensionV1.model_validate(value)


def test_mutating_operations_require_idempotency():
    value = definition()
    value["operations"][1]["idempotency"] = "forbidden"

    with pytest.raises(ValidationError, match="require idempotency"):
        ApplicationExtensionV1.model_validate(value)


def test_operation_schemas_are_strict_objects():
    value = definition()
    value["operations"][0]["output_schema"] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }

    with pytest.raises(ValidationError, match="forbid additional properties"):
        ApplicationExtensionV1.model_validate(value)


def test_operator_operations_and_routes_require_known_permissions():
    value = definition()
    value["operations"][2]["required_permission"] = "missing"

    with pytest.raises(ValidationError, match="unknown permission"):
        ApplicationExtensionV1.model_validate(value)

    value = definition()
    value["routes"][1]["required_permissions"] = ["missing"]
    with pytest.raises(ValidationError, match="unknown permission"):
        ApplicationExtensionV1.model_validate(value)


def test_kiosk_layout_and_internal_handlers_fail_closed():
    value = definition()
    value["routes"][0]["audience"] = "public"
    with pytest.raises(ValidationError, match="kiosk layout"):
        ApplicationExtensionV1.model_validate(value)

    value = definition()
    value["event_subscriptions"][0]["handler_operation_id"] = "approve"
    with pytest.raises(ValidationError, match="internal command"):
        ApplicationExtensionV1.model_validate(value)


def test_personal_data_requires_retention_export_and_erasure_operations():
    value = definition()
    value["storage"].pop("erasure_operation_id")

    with pytest.raises(ValidationError, match="personal data requires"):
        ApplicationExtensionV1.model_validate(value)


def test_connector_credentials_match_authentication_mode():
    value = definition()
    value["connectors"][0]["authentication"] = "none"

    with pytest.raises(ValidationError, match="credentials are required exactly"):
        ApplicationExtensionV1.model_validate(value)


@pytest.mark.parametrize(
    "artifact",
    ["../service.whl", "/service/service.whl", "service/service.py"],
)
def test_service_artifact_is_a_safe_wheel_path(artifact):
    value = definition()
    value["service"]["artifact"] = artifact

    with pytest.raises(ValidationError, match="safe wheel"):
        ApplicationExtensionV1.model_validate(value)
