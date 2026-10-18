"""Exact peer requests are not generic permissions, live consent or a signer."""

import json

import pytest
from pydantic import ValidationError

from three_mm_protocol import ApplicationExtensionV1, ApplicationPeerBindingV1
from three_mm_protocol.application_extension import parse_application_extension
from three_mm_protocol.extension_schemas import extension_schema_catalog
from three_mm_protocol.tests.test_application_extension import definition


def peer_request(**changes):
    return {
        "contract_version": 1,
        "binding_id": "primary",
        "direction": "outbound",
        "peer_id_config_key": "PEER_LINK",
        "operations": ["read", "enroll", "rotate", "report", "revoke"],
        **changes,
    }


def peer_application(*requests, sdk="1.3", permissions=None):
    value = definition(peer_bindings=list(requests))
    value["service"]["sdk_version"] = sdk
    value["platform_permissions"] = (
        permissions
        if permissions is not None
        else [
            "installation.peers.enroll",
            "installation.peers.receive",
            "installation.peers.report",
            "installation.status.read",
        ]
    )
    return value


@pytest.mark.parametrize(
    "direction,operations,required",
    [
        (
            "outbound",
            ["read", "enroll", "rotate", "revoke"],
            {"installation.peers.enroll"},
        ),
        (
            "outbound",
            ["report"],
            {
                "installation.peers.enroll",
                "installation.peers.report",
                "installation.status.read",
            },
        ),
        ("inbound", ["read", "approve", "revoke"], {"installation.peers.receive"}),
    ],
)
def test_exact_requests_roundtrip_without_authority_or_mutable_operations(
    direction, operations, required
):
    raw = peer_request(direction=direction, operations=operations)
    request = ApplicationPeerBindingV1.model_validate(raw)
    assert request.model_dump(mode="json") == raw
    assert request.required_platform_permissions() == required
    assert (
        ApplicationPeerBindingV1.model_validate_json(request.model_dump_json())
        == request
    )
    with pytest.raises(ValidationError, match="frozen"):
        request.direction = "outbound"
    assert isinstance(request.operations, tuple)


@pytest.mark.parametrize("field", tuple(peer_request()))
def test_every_field_is_explicit(field):
    raw = peer_request()
    del raw[field]
    with pytest.raises(ValidationError):
        ApplicationPeerBindingV1.model_validate(raw)


@pytest.mark.parametrize("version", [True, False, "1", 1.0, 0, 2, None])
def test_version_does_not_coerce_or_accept_unknown_contracts(version):
    with pytest.raises(ValidationError):
        ApplicationPeerBindingV1.model_validate(peer_request(contract_version=version))


@pytest.mark.parametrize(
    "field,values",
    [
        (
            "binding_id",
            ["", "*", "peer:*", "../peer", "a.b", "UPPER", "a" * 97, 1, None],
        ),
        (
            "peer_id_config_key",
            ["", "*", "PEER.*", "../PEER", "lower", "A", "A" * 65, 1, None],
        ),
        ("direction", ["*", "both", "inbound ", "", True, None]),
    ],
)
def test_closed_identifiers_and_direction(field, values):
    for value in values:
        with pytest.raises(ValidationError):
            ApplicationPeerBindingV1.model_validate(peer_request(**{field: value}))


@pytest.mark.parametrize(
    "direction,operations",
    [
        ("inbound", ["enroll"]),
        ("inbound", ["rotate"]),
        ("inbound", ["report"]),
        ("outbound", ["approve"]),
        ("outbound", ["read", "read"]),
        ("outbound", []),
        ("outbound", ["*"]),
        ("outbound", ["list"]),
        ("outbound", ["discover"]),
        ("outbound", ["create"]),
        ("outbound", ["prove"]),
        ("outbound", ["consent"]),
        ("outbound", ["read", "enroll", "rotate", "report", "approve", "revoke"]),
        ("outbound", "read"),
        ("outbound", [True]),
        ("outbound", None),
    ],
)
def test_operations_are_separate_directional_bounded_and_have_no_discovery_or_signing(
    direction, operations
):
    with pytest.raises(ValidationError):
        ApplicationPeerBindingV1.model_validate(
            peer_request(direction=direction, operations=operations)
        )


@pytest.mark.parametrize(
    "field",
    [
        "peer_id",
        "owner",
        "origin",
        "receiver_identity",
        "credential",
        "generation",
        "expires_at",
        "grant",
        "approved",
        "signature",
        "inbox",
        "proof_request",
    ],
)
def test_author_cannot_supply_resolved_authority_or_volatile_credentials(field):
    with pytest.raises(ValidationError, match="Extra inputs"):
        ApplicationPeerBindingV1.model_validate(peer_request(**{field: "forbidden"}))


@pytest.mark.parametrize("sdk", ["1.0", "1.1", "1.2", "1.3"])
def test_empty_addition_preserves_old_sdk_and_nonempty_requires_13(sdk):
    legacy = definition()
    legacy["service"]["sdk_version"] = sdk
    absent = parse_application_extension(json.dumps(legacy))
    assert absent.peer_bindings == ()
    assert (
        parse_application_extension(json.dumps({**legacy, "peer_bindings": []}))
        == absent
    )
    raw = peer_application(peer_request(), sdk=sdk)
    if sdk == "1.3":
        assert parse_application_extension(json.dumps(raw)).peer_bindings
    else:
        with pytest.raises(ValidationError, match="require SDK 1.3"):
            parse_application_extension(json.dumps(raw))


@pytest.mark.parametrize(
    "missing",
    [
        "installation.peers.enroll",
        "installation.peers.report",
        "installation.status.read",
    ],
)
def test_reporting_requires_all_existing_request_groups_but_not_generic_proof(missing):
    permissions = set(peer_request_model().required_platform_permissions())
    permissions.remove(missing)
    with pytest.raises(ValidationError, match="permission groups"):
        ApplicationExtensionV1.model_validate(
            peer_application(peer_request(), permissions=sorted(permissions))
        )


def peer_request_model():
    return ApplicationPeerBindingV1.model_validate(peer_request())


def test_receive_group_cannot_authorize_outbound_and_read_does_not_require_write_actions():
    for direction, permissions in [
        ("inbound", ["installation.peers.enroll"]),
        ("outbound", ["installation.peers.receive"]),
    ]:
        with pytest.raises(ValidationError, match="permission groups"):
            ApplicationExtensionV1.model_validate(
                peer_application(
                    peer_request(direction=direction, operations=["read"]),
                    permissions=permissions,
                )
            )
    raw = peer_application(
        peer_request(operations=["read"]), permissions=["installation.peers.enroll"]
    )
    assert ApplicationExtensionV1.model_validate(raw).peer_bindings[0].operations == (
        "read",
    )


def test_complete_declaration_set_has_explicit_bound_and_no_split_or_ambiguous_ids():
    requests = [
        peer_request(binding_id=f"item_{n}", peer_id_config_key=f"PEER_{n}")
        for n in range(32)
    ]
    assert (
        len(
            ApplicationExtensionV1.model_validate(
                peer_application(*requests)
            ).peer_bindings
        )
        == 32
    )
    with pytest.raises(ValidationError, match="at most 32"):
        ApplicationExtensionV1.model_validate(
            peer_application(
                *requests,
                peer_request(binding_id="overflow", peer_id_config_key="PEER_EXTRA"),
            )
        )
    with pytest.raises(ValidationError, match="peer binding IDs must be unique"):
        ApplicationExtensionV1.model_validate(
            peer_application(
                peer_request(), peer_request(peer_id_config_key="OTHER_PEER")
            )
        )
    with pytest.raises(ValidationError, match="unique per direction"):
        ApplicationExtensionV1.model_validate(
            peer_application(
                peer_request(operations=["read"]),
                peer_request(binding_id="split", operations=["enroll"]),
            )
        )


@pytest.mark.parametrize("field", ["binding_id", "operations", "peer_bindings"])
def test_raw_parser_refuses_duplicate_keys_and_hidden_opt_in(field):
    raw = json.dumps(peer_application(peer_request()))
    if field == "binding_id":
        raw = raw.replace(
            '"binding_id": "primary"', '"binding_id": "hidden", "binding_id": "primary"'
        )
    elif field == "operations":
        raw = raw.replace(
            '"operations": ["read",',
            '"operations": ["approve"], "operations": ["read",',
        )
    else:
        raw = raw[:-1] + ', "peer_bindings": []}'
    with pytest.raises(ValueError, match="duplicate JSON keys"):
        parse_application_extension(raw)


def test_catalog_advertises_only_exact_outbound_read_and_explicitly_denies_fallback():
    entry = extension_schema_catalog()["contracts"]["application-extension.v1"]
    schema = entry["schema"]
    request = schema["$defs"]["ApplicationPeerBindingV1"]
    assert request["additionalProperties"] is False
    assert set(request["required"]) == set(peer_request())
    assert schema["properties"]["peer_bindings"]["maxItems"] == 32
    support = entry["declaration_support"]["peer_bindings"]
    assert support["runtime_authority"] == "reviewed_native_scoped_outbound_read"
    assert support["runtime_directions"] == ["outbound"]
    assert support["runtime_operations"] == ["read"]
    assert support["sdk_method"] == "read_installation_peer"
    assert support["relational_combination"] == "unsupported"
    assert support["compatibility_fallback"] == "blocked"
    assert support["existing_peer_only"] is True
    assert support["inbox_discovery_or_generic_signing"] is False
