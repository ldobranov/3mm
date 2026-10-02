from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from three_mm_protocol.installation_peer import (
    ProjectionConsentV1,
    ProjectionValueV1,
    InstallationProjectionV1,
)
from three_mm_application_sdk import OperationContext
from backend.services.application_access import (
    ApplicationPrincipal,
    can_access_application_operation,
)
from three_mm_protocol.application_extension import (
    ApplicationOperationV1,
    ApplicationExtensionV1,
)


@pytest.mark.parametrize(
    "value",
    [
        {"node_ids": ["dev_" + "a" * 32], "node_fields": []},
        {"node_ids": [], "node_fields": ["online"]},
        {"node_ids": ["dev_" + "a" * 32], "node_fields": ["online", "online"]},
        {"summary_fields": ["credentials"]},
        {"node_ids": ["*"]},
        {"consent_version": True},
        {"consent_version": 1.0},
        {"summary_fields": ["core_version"] * 4},
    ],
)
def test_projection_selection_is_explicit_strict_and_bounded(value):
    with pytest.raises(ValidationError):
        ProjectionConsentV1.model_validate(value)


def test_projection_model_has_no_arbitrary_fields_or_hidden_payload_slot():
    value = {
        "installation_id": "inst_" + "a" * 32,
        "consent_revision": 1,
        "generated_at": datetime.now(UTC),
        "summary": {},
        "nodes": [],
    }
    for changed in (
        {"credentials": "fixture"},
        {"summary": {"business": {"status": "unknown"}}},
        {"consent_revision": True},
    ):
        with pytest.raises(ValidationError):
            InstallationProjectionV1.model_validate({**value, **changed})
    with pytest.raises(ValidationError):
        ProjectionValueV1(status="known", value=1.0)
    with pytest.raises(ValidationError):
        ProjectionValueV1(status="unknown", value="looks valid")


def test_peer_machine_context_rejects_payload_escalation_and_human_mixing():
    machine = {
        "installation_id": "inst_" + "a" * 32,
        "key_id": "a" * 64,
        "binding_id": "peer_" + "a" * 32,
        "generation": 1,
        "scopes": ["installation.status.report"],
    }
    context = {
        "audience": "installation_peer",
        "correlation_id": "fixture",
        "idempotency_key": "fixture-report",
        "machine": machine,
    }
    assert (
        OperationContext.from_platform(context).machine.installation_id
        == machine["installation_id"]
    )
    for changed in (
        {"user_id": 1},
        {"audience": "administrator"},
        {"machine": None},
        {"machine": {**machine, "scopes": ["capabilities.invoke"]}},
        {"machine": {**machine, "generation": True}},
    ):
        with pytest.raises(ValueError):
            OperationContext.from_platform({**context, **changed})
    bootstrap = OperationContext.from_platform(
        {
            **context,
            "audience": "installation_bootstrap",
            "machine": {**machine, "scopes": []},
        }
    )
    assert bootstrap.machine.scopes == ()


def test_human_admin_and_anonymous_cannot_bypass_peer_audience():
    operation = ApplicationOperationV1(
        operation_id="report",
        kind="command",
        audiences=("installation_peer",),
        idempotency="required",
    )
    for principal in (
        ApplicationPrincipal(kind="anonymous"),
        ApplicationPrincipal(kind="user", user_id=1, is_admin=True),
        ApplicationPrincipal(kind="kiosk"),
        ApplicationPrincipal(kind="installation"),
    ):
        assert not can_access_application_operation(
            operation, principal, audience="installation_peer"
        )
    principal = ApplicationPrincipal(
        kind="installation",
        installation_id="inst_" + "a" * 32,
        peer_binding_id="peer_" + "a" * 32,
        peer_generation=1,
        machine_scopes=frozenset({"installation.status.report"}),
    )
    assert can_access_application_operation(
        operation, principal, audience="installation_peer"
    )


@pytest.mark.parametrize(
    "changed",
    [
        {"audiences": ["installation_peer", "administrator"]},
        {"kind": "query", "idempotency": "forbidden"},
        {"emitted_events": ["command.requested"]},
        {"required_permission": "admin"},
    ],
)
def test_peer_operations_cannot_gain_other_audiences_commands_or_events(changed):
    with pytest.raises(ValidationError):
        ApplicationOperationV1.model_validate(
            {
                "operation_id": "report",
                "kind": "command",
                "audiences": ["installation_peer"],
                "idempotency": "required",
                **changed,
            }
        )
