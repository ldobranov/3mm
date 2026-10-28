import copy
import json

import pytest
from pydantic import ValidationError

from three_mm_protocol import (
    ApplicationExtensionV1, ApplicationQueryContractV1,
    ApplicationQueryCompatibilityV1, assess_application_query,
)
from three_mm_protocol.application_extension import parse_application_extension
from three_mm_protocol.tests.test_application_extension import definition


def query_contract():
    return {
        'contract_id': 'example.directory.lookup', 'contract_version': '1.0',
        'input_schema': {'type': 'object', 'properties': {
            'reference': {'type': 'string', 'minLength': 1, 'maxLength': 96}},
            'required': ['reference'], 'additionalProperties': False},
        'output_schema': {'type': 'object', 'properties': {
            'found': {'type': 'boolean'},
            'label': {'type': 'string', 'maxLength': 160}},
            'required': ['found'], 'additionalProperties': False},
        'timeout_seconds': 5, 'max_response_bytes': 4096,
    }


def applications():
    provider = definition(module_id='org.example.directory')
    consumer = definition(module_id='org.example.dashboard')
    consumer.update(operations=consumer['operations'][:1], permissions=[], routes=[],
        event_subscriptions=[], connectors=[], jobs=[], storage={
            'schema_revision': '0001', 'migration_entrypoint': 'example.migrations:get_migrations',
            'classifications': ['private'], 'contains_personal_data': False})
    provider['service']['sdk_version'] = consumer['service']['sdk_version'] = '1.3'
    contract = query_contract()
    provider['operations'].append({
        'operation_id': 'lookup_entity', 'kind': 'query', 'audiences': ['internal'],
        'idempotency': 'forbidden', 'timeout_seconds': 5,
        'input_schema': copy.deepcopy(contract['input_schema']),
        'output_schema': copy.deepcopy(contract['output_schema']),
    })
    provider['query_exports'] = [{
        'export_id': 'lookup', 'handler_operation_id': 'lookup_entity',
        'contract': copy.deepcopy(contract),
    }]
    consumer['query_dependencies'] = [{'binding_id': 'directory', 'contract': contract,
        'provider_instance_config_key': 'DIRECTORY_INSTANCE', 'provider_export_config_key': 'DIRECTORY_EXPORT'}]
    return consumer, provider


def test_exact_read_only_declarations_round_trip_without_grant_or_execution():
    consumer, provider = applications()
    originals = copy.deepcopy((consumer, provider))
    result = assess_application_query(consumer, provider,
                                     binding_id='directory', export_id='lookup')
    assert result.compatible and result.reason is None
    assert result.basis == 'declarations_only' and not result.invocation_supported
    assert (result.permission_approval, result.instance_binding, result.runtime_readiness) == (
        'not_evaluated', 'not_evaluated', 'not_evaluated')
    assert result.contract_digest == ApplicationQueryContractV1(**query_contract()).digest()
    assert ApplicationQueryCompatibilityV1.model_validate_json(result.model_dump_json()) == result
    for value in (consumer, provider):
        parsed = parse_application_extension(json.dumps(value))
        assert parse_application_extension(parsed.model_dump_json()) == parsed
    assert originals == (consumer, provider)


@pytest.mark.parametrize('field,value,reason', [
    ('contract_id', 'example.directory.details', 'contract_id_mismatch'),
    ('contract_version', '1.1', 'contract_version_mismatch'),
    ('timeout_seconds', 4, 'limits_mismatch'),
    ('max_response_bytes', 4095, 'limits_mismatch'),
])
def test_consumer_requires_exact_version_identity_and_limits(field, value, reason):
    consumer, provider = applications()
    consumer['query_dependencies'][0]['contract'][field] = value
    result = assess_application_query(consumer, provider,
                                     binding_id='directory', export_id='lookup')
    assert not result.compatible and result.reason == reason


@pytest.mark.parametrize('side', ['input_schema', 'output_schema'])
def test_narrower_schema_is_not_inferred_compatible(side):
    consumer, provider = applications()
    schema = consumer['query_dependencies'][0]['contract'][side]
    field = 'reference' if side == 'input_schema' else 'label'
    schema['properties'][field]['maxLength'] -= 1
    assert assess_application_query(consumer, provider,
        binding_id='directory', export_id='lookup').reason == 'schema_mismatch'


def test_numeric_schema_identity_is_typed_not_python_equality():
    consumer, provider = applications()
    field = {'type': 'number', 'minimum': 0, 'maximum': 1}
    provider['operations'][-1]['output_schema']['properties']['score'] = copy.deepcopy(field)
    provider['query_exports'][0]['contract']['output_schema']['properties']['score'] = copy.deepcopy(field)
    field['maximum'] = 1.0
    consumer['query_dependencies'][0]['contract']['output_schema']['properties']['score'] = field
    assert assess_application_query(consumer, provider,
        binding_id='directory', export_id='lookup').reason == 'schema_mismatch'


def test_digest_ignores_object_key_order_but_not_interface_or_bounds():
    value = query_contract()
    reordered = dict(reversed(list(value.items())))
    assert ApplicationQueryContractV1(**value).digest() == ApplicationQueryContractV1(**reordered).digest()
    reordered['contract_version'] = '2.0'
    assert ApplicationQueryContractV1(**value).digest() != ApplicationQueryContractV1(**reordered).digest()


@pytest.mark.parametrize('binding,export,reason', [
    ('missing', 'lookup', 'dependency_not_declared'),
    ('directory', 'missing', 'export_not_declared'),
])
def test_no_fallback_to_another_export_or_dependency(binding, export, reason):
    consumer, provider = applications()
    assert assess_application_query(consumer, provider,
        binding_id=binding, export_id=export).reason == reason


def test_self_composition_is_not_a_shortcut_to_private_operations():
    consumer, provider = applications()
    consumer['module_id'] = provider['module_id']
    assert assess_application_query(consumer, provider,
        binding_id='directory', export_id='lookup').reason == 'same_application'


@pytest.mark.parametrize('field,value', [
    ('contract_id', '*'), ('contract_version', '>=1.0'), ('contract_version', 1.0),
    ('kind', 'command'), ('kind', 'task'), ('timeout_seconds', True),
    ('timeout_seconds', 1.5), ('timeout_seconds', 6), ('timeout_seconds', 0),
    ('max_response_bytes', True), ('max_response_bytes', 16385),
    ('max_response_bytes', 0), ('automatic_retry', True), ('delegated_actor', {}),
])
def test_query_profile_refuses_mutation_wildcards_unbounded_or_coerced_limits(field, value):
    contract = query_contract()
    contract[field] = value
    with pytest.raises(ValidationError):
        ApplicationQueryContractV1(**contract)


@pytest.mark.parametrize('fault', [
    'array', 'reference', 'unbounded_string', 'open_object', 'deep',
    'nonfinite', 'too_many_fields', 'huge_schema', 'wrong_root',
])
def test_composition_reuses_the_bounded_non_executable_schema_dialect(fault):
    contract = query_contract()
    schema = contract['input_schema']
    if fault == 'array': schema['properties']['reference'] = {'type': 'array', 'items': {}}
    if fault == 'reference': schema['$ref'] = 'https://schemas.example/remote'
    if fault == 'unbounded_string': del schema['properties']['reference']['maxLength']
    if fault == 'open_object': schema['additionalProperties'] = True
    if fault == 'deep':
        for _ in range(6):
            schema = {'type': 'object', 'properties': {'child': schema}, 'additionalProperties': False}
        contract['input_schema'] = schema
    if fault == 'nonfinite': schema['properties']['reference'] = {'type': 'number', 'minimum': 0, 'maximum': float('inf')}
    if fault == 'too_many_fields': schema['properties'].update({str(i): {'type': 'boolean'} for i in range(33)})
    if fault == 'huge_schema': schema['properties']['reference']['enum'] = ['x' * 96 + str(i) for i in range(100)]
    if fault == 'wrong_root': contract['input_schema'] = {'type': 'boolean'}
    with pytest.raises(ValueError):
        ApplicationQueryContractV1(**contract)


@pytest.mark.parametrize('fault', [
    'missing_handler', 'health_handler', 'command', 'human_audience',
    'human_permission', 'events', 'schema', 'timeout', 'duplicate_export',
    'duplicate_handler', 'duplicate_dependency', 'old_sdk',
])
def test_exports_only_name_dedicated_matching_internal_queries(fault):
    consumer, provider = applications()
    export = provider['query_exports'][0]
    handler = provider['operations'][-1]
    value = provider
    if fault == 'missing_handler': export['handler_operation_id'] = 'missing'
    if fault == 'health_handler': export['handler_operation_id'] = 'health'
    if fault == 'command': handler.update(kind='command', idempotency='required')
    if fault == 'human_audience': handler.update(audiences=['administrator'])
    if fault == 'human_permission': handler['required_permission'] = 'records_manage'
    if fault == 'events': handler['emitted_events'] = ['example.query.read']
    if fault == 'schema': handler['output_schema']['properties']['extra'] = {'type': 'boolean'}
    if fault == 'timeout': handler['timeout_seconds'] = 6
    if fault == 'duplicate_export': provider['query_exports'] *= 2
    if fault == 'duplicate_handler':
        provider['query_exports'].append({**copy.deepcopy(export), 'export_id': 'second'})
    if fault == 'duplicate_dependency':
        consumer['query_dependencies'] *= 2
        value = consumer
    if fault == 'old_sdk': provider['service']['sdk_version'] = '1.2'
    with pytest.raises(ValueError):
        ApplicationExtensionV1.model_validate(value)


def test_assessment_revalidates_mutated_or_unchecked_descriptor_models():
    consumer, provider = (ApplicationExtensionV1.model_validate(v) for v in applications())
    provider.query_exports[0].contract.output_schema['additionalProperties'] = True
    with pytest.raises(ValueError):
        assess_application_query(consumer, provider, binding_id='directory', export_id='lookup')


def test_digest_revalidates_mutable_schema_before_identity_is_used():
    contract = ApplicationQueryContractV1(**query_contract())
    contract.output_schema['additionalProperties'] = True
    with pytest.raises(ValueError): contract.digest()


def test_empty_composition_does_not_change_unrelated_canonical_declarations():
    original = ApplicationExtensionV1.model_validate(definition())
    assert 'query_exports' not in original.model_dump()
    assert 'query_dependencies' not in original.model_dump()
    explicit_empty = definition(query_exports=[], query_dependencies=[])
    assert original.model_dump_json() == ApplicationExtensionV1.model_validate(explicit_empty).model_dump_json()


@pytest.mark.parametrize('fault', ['missing_instance_key', 'same_key', 'chain', 'connector', 'command_binding'])
def test_query_dependency_requires_explicit_distinct_selection_and_one_hop_profile(fault):
    consumer, provider = applications()
    dependency = consumer['query_dependencies'][0]
    if fault == 'missing_instance_key': del dependency['provider_instance_config_key']
    if fault == 'same_key': dependency['provider_export_config_key'] = dependency['provider_instance_config_key']
    if fault == 'chain': consumer['query_exports'] = provider['query_exports']
    if fault == 'connector': consumer['connectors'] = provider['connectors']
    if fault == 'command_binding':
        consumer['command_bindings'] = [{'binding_id': 'write', 'target_device_config_key': 'DEVICE',
            'capability_id': 'example.control', 'action': 'set', 'arguments_schema': {
                'type': 'object', 'properties': {}, 'additionalProperties': False}}]
    with pytest.raises(ValueError): ApplicationExtensionV1.model_validate(consumer)


@pytest.mark.parametrize('changes', [
    {'assessment_version': True}, {'invocation_supported': 0},
    {'invocation_supported': True}, {'permission_approval': 'approved'},
    {'compatible': True, 'reason': 'schema_mismatch'},
])
def test_assessment_never_masquerades_as_runtime_or_permission_approval(changes):
    consumer, provider = applications()
    value = assess_application_query(consumer, provider,
        binding_id='directory', export_id='lookup').model_dump(mode='python')
    value.update(changes)
    with pytest.raises(ValidationError): ApplicationQueryCompatibilityV1(**value)
