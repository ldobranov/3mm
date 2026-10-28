"""Composition descriptors use the actual manifest-v2 ZIP validation boundary."""
import copy

import pytest

from backend.services.module_packages import ModulePackageError, validate_module_package
from backend.tests.test_module_packages import application_definition, application_package, application_manifest
from three_mm_protocol.tests.test_application_composition import query_contract


def provider_definition():
    value = application_definition()
    value['service']['sdk_version'] = '1.3'
    contract = query_contract()
    value['operations'].append({
        'operation_id': 'lookup', 'kind': 'query', 'audiences': ['internal'],
        'idempotency': 'forbidden', 'timeout_seconds': contract['timeout_seconds'],
        'input_schema': copy.deepcopy(contract['input_schema']),
        'output_schema': copy.deepcopy(contract['output_schema']),
    })
    value['query_exports'] = [{'export_id': 'directory', 'handler_operation_id': 'lookup',
                               'contract': contract}]
    return value


def test_provider_and_consumer_declarations_survive_verified_package_parsing():
    provider = provider_definition()
    parsed = validate_module_package(application_package(definition=provider))
    assert parsed.application_extension.query_exports[0].contract.contract_version == '1.0'
    consumer = application_definition()
    consumer['service']['sdk_version'] = '1.3'
    consumer.update(event_subscriptions=[], connectors=[])
    consumer['operations'][2]['emitted_events'] = []
    consumer['query_dependencies'] = [{'binding_id': 'directory', 'contract': query_contract(),
        'provider_instance_config_key': 'DIRECTORY_INSTANCE', 'provider_export_config_key': 'DIRECTORY_EXPORT'}]
    manifest = application_manifest(permissions=['data.read', 'data.write', 'process.spawn'],
        capabilities={'provides': [], 'consumes': []}, configuration_schema={
            'type': 'object', 'additionalProperties': False, 'properties': {
                'DIRECTORY_INSTANCE': {'type': 'string'}, 'DIRECTORY_EXPORT': {'type': 'string'}}})
    parsed = validate_module_package(application_package(definition=consumer, manifest_value=manifest))
    assert parsed.application_extension.query_dependencies[0].binding_id == 'directory'


@pytest.mark.parametrize('fault', ['command', 'schema', 'token', 'url', 'old_sdk'])
def test_package_upload_cannot_smuggle_an_executable_or_credential_binding(fault):
    value = provider_definition()
    if fault == 'command': value['query_exports'][0]['handler_operation_id'] = 'approve'
    if fault == 'schema': value['query_exports'][0]['contract']['output_schema']['additionalProperties'] = True
    if fault == 'token': value['query_exports'][0]['admin_token'] = 'never-an-authority'
    if fault == 'url': value['query_exports'][0]['destination_url'] = 'https://provider.example/private'
    if fault == 'old_sdk': value['service']['sdk_version'] = '1.0'
    with pytest.raises(ModulePackageError, match='invalid application-extension'):
        validate_module_package(application_package(definition=value))
