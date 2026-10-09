import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from three_mm_protocol import ApplicationExtensionV1, DeviceEventV1
from three_mm_protocol.application_event_publication import (
    ApplicationEventProducerV1,
    ApplicationEventPublicationReceiptV1,
    ApplicationEventPublicationsV1,
    ApplicationEventPublishRequestV1,
    PlatformEventV1,
    adapt_device_event,
    parse_application_publication_request,
    prepare_application_event,
    validate_application_publications,
)
from three_mm_protocol.node_security import (
    CORE_DEVICE_AUDIT_EVENTS,
    NODE_JSON_ITEMS,
    NODE_MESSAGE_BYTES,
)


NOW = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)


def strict_object(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": False,
    }


def application_data():
    return {
        "application_extension_version": 1,
        "module_id": "org.example.workflow",
        "version": "1.0.0",
        "service": {
            "artifact": "service/workflow-1.0.0-py3-none-any.whl",
            "artifact_sha256": "a" * 64,
            "entrypoint": "workflow.service:create_service",
            "sdk_version": "1.3",
            "health_operation_id": "health",
        },
        "operations": [
            {
                "operation_id": "health",
                "kind": "query",
                "audiences": ["internal"],
                "idempotency": "forbidden",
                "output_schema": strict_object(
                    {"status": {"type": "string", "enum": ["ready"]}}
                ),
            },
            {
                "operation_id": "finalize",
                "kind": "command",
                "audiences": ["internal"],
                "idempotency": "required",
                "emitted_events": ["workflow.record.finalized"],
            },
        ],
        "storage": {
            "schema_revision": "0001",
            "migration_entrypoint": "workflow.migrations:get_migrations",
        },
    }


def contract_data():
    return {
        "publication_contract_version": 1,
        "module_id": "org.example.workflow",
        "version": "1.0.0",
        "service_artifact_sha256": "a" * 64,
        "publications": [
            {
                "publication_id": "record_finalized",
                "operation_id": "finalize",
                "event_type": "workflow.record.finalized",
                "max_payload_bytes": 1024,
                "payload_schema": strict_object(
                    {
                        "record_id": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 64,
                        },
                        "result": strict_object(
                            {
                                "accepted": {"type": "boolean"},
                                "count": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 100,
                                },
                            }
                        ),
                    }
                ),
            }
        ],
    }


def producer(**changes):
    return ApplicationEventProducerV1.model_validate(
        {
            "kind": "application",
            "core_installation_id": "inst_" + "a" * 32,
            "application_installation_id": "1",
            "incarnation": "b" * 32,
            "module_id": "org.example.workflow",
        }
        | changes
    )


def request_data():
    return {
        "publication_request_version": 1,
        "event_id": "evt_" + "c" * 32,
        "publication_id": "record_finalized",
        "payload": {"record_id": "record-1", "result": {"accepted": True, "count": 1}},
        "occurred_at": NOW.isoformat(),
    }


def prepare(data=None, owner=None, contract=None, application=None):
    return prepare_application_event(
        ApplicationEventPublishRequestV1.model_validate(data or request_data()),
        authenticated_producer=owner or producer(),
        contract=ApplicationEventPublicationsV1.model_validate(
            contract or contract_data()
        ),
        application=ApplicationExtensionV1.model_validate(
            application or application_data()
        ),
    )


def test_versioned_round_trip_and_no_implicit_sdk_or_descriptor_upgrade():
    from three_mm_application_sdk import SDK_VERSION, SUPPORTED_SDK_VERSIONS

    contract = ApplicationEventPublicationsV1.model_validate(contract_data())
    assert (
        ApplicationEventPublicationsV1.model_validate_json(contract.model_dump_json())
        == contract
    )
    event = prepare()
    assert PlatformEventV1.model_validate_json(event.model_dump_json()) == event
    assert event.producer == producer()
    assert event.event_type == "workflow.record.finalized"
    descriptor = ApplicationExtensionV1.model_validate(application_data()).model_dump()
    assert "publications" not in descriptor
    assert descriptor["operations"][1]["emitted_events"] == (
        "workflow.record.finalized",
    )
    assert SDK_VERSION == "1.3" and SUPPORTED_SDK_VERSIONS == (
        "1.0",
        "1.1",
        "1.2",
        "1.3",
    )


@pytest.mark.parametrize(
    "field",
    [
        "producer",
        "device_id",
        "module_id",
        "user_id",
        "authority_epoch",
        "operation_id",
        "event_type",
    ],
)
def test_request_cannot_claim_identity_type_authority_or_operation(field):
    with pytest.raises(ValidationError):
        ApplicationEventPublishRequestV1.model_validate(
            request_data() | {field: "foreign"}
        )


@pytest.mark.parametrize("version", [True, "1", 1.0, 0, 2])
def test_exact_versions_not_boolean_or_coerced(version):
    with pytest.raises(ValidationError):
        ApplicationEventPublishRequestV1.model_validate(
            request_data() | {"publication_request_version": version}
        )
    with pytest.raises(ValidationError):
        ApplicationEventPublicationsV1.model_validate(
            contract_data() | {"publication_contract_version": version}
        )


@pytest.mark.parametrize(
    "event_type",
    ["changed", "foreign.*", "core.custom.changed", *sorted(CORE_DEVICE_AUDIT_EVENTS)],
)
def test_invalid_or_core_owned_types_are_not_application_declarations(event_type):
    values = contract_data()
    values["publications"][0]["event_type"] = event_type
    with pytest.raises(ValidationError):
        ApplicationEventPublicationsV1.model_validate(values)


@pytest.mark.parametrize(
    "change",
    [
        "unknown_operation",
        "query",
        "undeclared_type",
        "wrong_module",
        "wrong_version",
        "wrong_artifact",
    ],
)
def test_declaration_binds_exact_application_artifact_and_emitting_operation(change):
    values = contract_data()
    declaration = values["publications"][0]
    if change == "unknown_operation":
        declaration["operation_id"] = "missing"
    elif change == "query":
        declaration["operation_id"] = "health"
    elif change == "undeclared_type":
        declaration["event_type"] = "workflow.other.changed"
    else:
        values[
            {
                "wrong_module": "module_id",
                "wrong_version": "version",
                "wrong_artifact": "service_artifact_sha256",
            }[change]
        ] = {
            "wrong_module": "org.example.foreign",
            "wrong_version": "1.0.1",
            "wrong_artifact": "b" * 64,
        }[
            change
        ]
    with pytest.raises(ValueError):
        prepare(contract=values)


def test_unknown_publication_and_foreign_authenticated_application_are_rejected():
    with pytest.raises(ValueError, match="not declared"):
        prepare(request_data() | {"publication_id": "missing"})
    with pytest.raises(ValueError, match="does not own"):
        prepare(owner=producer(module_id="org.example.foreign"))


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"record_id": "r", "result": {"accepted": True}},
        {"record_id": "r", "result": {"accepted": 1, "count": 1}},
        {"record_id": "r", "result": {"accepted": True, "count": True}},
        {"record_id": "r", "result": {"accepted": True, "count": 101}},
        {"record_id": "r", "result": {"accepted": True, "count": 1, "extra": None}},
        {"record_id": "x" * 65, "result": {"accepted": True, "count": 1}},
        {"record_id": "r", "result": {"accepted": True, "count": 1}, "extra": 1},
        {"record_id": "r", "result": {"accepted": True, "count": float("nan")}},
        {"record_id": "r", "result": {"accepted": True, "count": float("inf")}},
        {"record_id": "r", "result": (True, 1)},
        {1: "numeric key"},
        {"bad": b"bytes"},
        {"bad": "\ud800"},
    ],
)
def test_payload_is_closed_bounded_noncoercing_json(payload):
    with pytest.raises(ValueError):
        prepare(request_data() | {"payload": payload})


@pytest.mark.parametrize(
    "change",
    [
        "ref",
        "array",
        "open",
        "unbounded_string",
        "extra_keyword",
        "boolean_bound",
        "duplicate_id",
        "duplicate_binding",
        "too_many",
    ],
)
def test_declarations_use_existing_bounded_schema_profile_only(change):
    values = contract_data()
    declaration = values["publications"][0]
    schema = declaration["payload_schema"]
    if change == "ref":
        schema["$ref"] = "https://invalid.test/schema"
    elif change == "array":
        schema["properties"]["result"] = {"type": "array", "items": {"type": "boolean"}}
    elif change == "open":
        schema["properties"]["result"]["additionalProperties"] = True
    elif change == "unbounded_string":
        schema["properties"]["record_id"].pop("maxLength")
    elif change == "extra_keyword":
        schema["properties"]["record_id"]["format"] = "uri"
    elif change == "boolean_bound":
        declaration["max_payload_bytes"] = True
    elif change == "duplicate_id":
        values["publications"].append(deepcopy(declaration))
    elif change == "duplicate_binding":
        values["publications"].append(
            deepcopy(declaration) | {"publication_id": "another"}
        )
    elif change == "too_many":
        values["publications"] *= 33
    with pytest.raises(ValidationError):
        ApplicationEventPublicationsV1.model_validate(values)


def test_unicode_byte_bound_depth_and_container_limits_are_enforced():
    values = contract_data()
    values["publications"][0]["max_payload_bytes"] = 70
    # Valid 64-character scalar but too large as encoded UTF-8 with the envelope fields.
    with pytest.raises(ValueError, match="byte limit"):
        prepare(
            request_data()
            | {
                "payload": {
                    "record_id": "я" * 64,
                    "result": {"accepted": True, "count": 1},
                }
            },
            contract=values,
        )
    nested = {}
    for _ in range(17):
        nested = {"child": nested}
    for payload in (nested, {"items": [None] * 8192}):
        with pytest.raises(ValueError, match="structure limit"):
            prepare(request_data() | {"payload": payload})


@pytest.mark.parametrize("timestamp", ["2026-10-09T10:00:00", True, 1791540000])
def test_new_publications_require_explicit_aware_timestamps(timestamp):
    with pytest.raises(ValidationError):
        prepare(request_data() | {"occurred_at": timestamp})


def test_retry_content_identity_and_receipt_are_exact_not_authority():
    original = prepare()
    receipt = ApplicationEventPublicationReceiptV1(
        publication_receipt_version=1,
        event_id=original.event_id,
        publication_id=original.publication_id,
        producer=original.producer,
        content_sha256=original.content_digest(),
        committed_at=NOW,
    )
    reordered = request_data() | {
        "payload": {"result": {"count": 1, "accepted": True}, "record_id": "record-1"},
        "occurred_at": "2026-10-09T13:00:00+03:00",
    }
    assert receipt.matches(prepare(reordered))
    for changes in (
        {"event_id": "evt_" + "d" * 32},
        {"occurred_at": "2026-10-09T10:00:01Z"},
        {
            "payload": {
                "record_id": "record-2",
                "result": {"accepted": True, "count": 1},
            }
        },
    ):
        assert not receipt.matches(prepare(request_data() | changes))
    for changes in (
        {"application_installation_id": "2"},
        {"incarnation": "c" * 32},
        {"core_installation_id": "inst_" + "b" * 32},
    ):
        assert not receipt.matches(prepare(owner=producer(**changes)))
    # Stable historical content is not bound to a newly minted approval epoch.
    with pytest.raises(ValidationError):
        ApplicationEventPublicationReceiptV1.model_validate(
            receipt.model_dump() | {"authority_epoch": "d" * 32}
        )


def test_revalidation_catches_mutation_of_nested_model_dictionaries():
    contract = ApplicationEventPublicationsV1.model_validate(contract_data())
    contract.publications[0].payload_schema["additionalProperties"] = True
    with pytest.raises(ValueError):
        validate_application_publications(
            contract, ApplicationExtensionV1.model_validate(application_data())
        )
    event = prepare()
    event.payload["invalid"] = float("nan")
    with pytest.raises(ValueError):
        event.content_digest()


def test_legacy_device_view_preserves_wire_identity_type_and_naive_utc():
    legacy = DeviceEventV1(
        event_id="evt_" + "a" * 32,
        device_id="dev_" + "b" * 32,
        event_type="changed",  # Legacy type need not match application dotted names.
        payload={"channel": "gpio.output.1", "value": True},
        occurred_at=NOW.replace(tzinfo=None),
    )
    before = legacy.model_dump_json()
    adapted = adapt_device_event(legacy)
    assert adapted.event_id == legacy.event_id
    assert (
        adapted.producer.kind == "device"
        and adapted.producer.device_id == legacy.device_id
    )
    assert adapted.event_type == legacy.event_type and adapted.payload == legacy.payload
    assert adapted.occurred_at == NOW and adapted.publication_id is None
    assert legacy.model_dump_json() == before and legacy.occurred_at.tzinfo is None
    with pytest.raises(ValidationError):
        PlatformEventV1.model_validate(
            adapted.model_dump() | {"publication_id": "foreign"}
        )


def test_adapter_does_not_shrink_the_existing_device_wire_byte_budget():
    values = {
        "event_id": "evt_" + "a" * 32,
        "device_id": "dev_" + "b" * 32,
        "event_type": "changed",
        "payload": {"value": ""},
        "occurred_at": "2026-10-09T10:00:00Z",
    }
    overhead = len(json.dumps(values, separators=(",", ":")).encode())
    values["payload"]["value"] = "x" * (NODE_MESSAGE_BYTES - overhead)
    legacy = DeviceEventV1.model_validate(values)
    adapted = adapt_device_event(legacy)
    assert adapted.payload == legacy.payload
    assert len(adapted.model_dump_json().encode()) > NODE_MESSAGE_BYTES
    assert adapted.content_digest()


def test_adapter_does_not_shrink_legacy_item_budget_or_change_wire_values():
    legacy = DeviceEventV1(
        event_id="evt_" + "a" * 32,
        device_id="dev_" + "b" * 32,
        event_type="changed",
        payload={"items": [None] * (NODE_JSON_ITEMS - 13)},
        occurred_at=NOW,
    )
    assert adapt_device_event(legacy).payload == legacy.payload
    legacy_tuple = DeviceEventV1.model_validate(
        legacy.model_dump() | {"payload": {"values": (1, 2)}}
    )
    before = legacy_tuple.model_dump_json()
    assert adapt_device_event(legacy_tuple).payload == {"values": [1, 2]}
    assert legacy_tuple.payload == {"values": (1, 2)}
    assert legacy_tuple.model_dump_json() == before


@pytest.mark.parametrize(
    "raw",
    [
        '{"payload":{"count":1,"count":2}}',
        '{"publication_request_version":1,"publication_request_version":2}',
        '{"payload":{"value":NaN}}',
        '{"payload":{"value":1e999}}',
        '{"payload":{"value":"\\ud800"}}',
        b"\xff",
        "[" * 2000,
        " " * (NODE_MESSAGE_BYTES + 1),
        '"' + "я" * (NODE_MESSAGE_BYTES // 2) + '"',
    ],
    ids=[
        "nested-duplicate",
        "version-duplicate",
        "nan",
        "overflow",
        "surrogate",
        "invalid-utf8",
        "depth",
        "raw-size",
        "utf8-size",
    ],
)
def test_raw_ingress_rejects_duplicate_keys_and_malformed_unbounded_data(raw):
    with pytest.raises(ValueError):
        parse_application_publication_request(raw)


def test_bounded_request_parser_returns_only_a_validated_request():
    request = parse_application_publication_request(json.dumps(request_data()).encode())
    assert request == ApplicationEventPublishRequestV1.model_validate(request_data())
