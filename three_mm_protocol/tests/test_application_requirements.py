"""Transport declarations cannot turn feature support into resource authority."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from three_mm_protocol import ApplicationExtensionV1
from three_mm_protocol.application_requirements import assess_platform_requirements
from three_mm_protocol.tests.test_application_extension import definition
from three_mm_protocol.extension_schemas import extension_schema_catalog


def requirement(**changes):
    return {'requirement_id':'events', 'operations':['event.publish'], **changes}


def package(requirements):
    value = definition()
    value['service']['sdk_version'] = '1.3'
    value['platform_requirements'] = requirements
    return value


@pytest.mark.parametrize('required, status', [(True, 'blocked'), (False, 'degraded')])
@pytest.mark.parametrize('fault', ['version', 'operation'])
def test_unknown_transport_requirements_remain_inspectable_and_explained(required, status, fault):
    need = requirement(required=required)
    if fault == 'version': need['transport_contract_version'] = 2
    else: need['operations'] = ['future.not_implemented']
    value = ApplicationExtensionV1.model_validate(package([need]))
    report = assess_platform_requirements(value.platform_requirements,
        transport_contract_version=1, operations={'platform.discover', 'event.publish'})
    assert report.status == status and report.requirements[0].supported is False
    assert report.requirements[0].reason == ('transport_contract_mismatch' if fault == 'version' else 'operations_missing')
    assert report.permission_approval == report.resource_bindings == report.runtime_readiness == 'not_evaluated'


@pytest.mark.parametrize('fault', ['old_sdk', 'binding', 'required_type', 'duplicate', 'count',
    'operation_duplicate', 'contract_bool', 'zero_version', 'empty_operations', 'unknown_field'])
def test_invalid_declarations_do_not_enter_any_lifecycle(fault):
    value = package([requirement()])
    needs = value['platform_requirements']
    if fault == 'old_sdk': value['service']['sdk_version'] = '1.2'
    elif fault == 'binding': needs[0]['binding_id'] = 'output'
    elif fault == 'required_type': needs[0]['required'] = 1
    elif fault == 'duplicate': needs.append(deepcopy(needs[0]))
    elif fault == 'count': value['platform_requirements'] = [requirement(requirement_id='need_'+str(i)) for i in range(17)]
    elif fault == 'operation_duplicate': needs[0]['operations'].append('event.publish')
    elif fault == 'contract_bool': needs[0]['transport_contract_version'] = True
    elif fault == 'zero_version': needs[0]['transport_contract_version'] = 0
    elif fault == 'empty_operations': needs[0]['operations'] = []
    else: needs[0]['automatic_grant'] = True
    with pytest.raises(ValidationError): ApplicationExtensionV1.model_validate(value)


def test_catalog_and_structure_identify_the_bounded_transport_only_profile():
    entry = extension_schema_catalog()['contracts']['application-extension.v1']
    support = entry['declaration_support']['platform_requirements']
    assert support['basis'] == 'core_transport_contract'
    assert support['runtime_readiness'] == 'not_evaluated'
    schema = entry['schema']
    requirement_schema = schema['$defs']['ApplicationPlatformRequirementV1']
    assert requirement_schema['properties']['binding_id']['type'] == 'null'
    assert 'platform_requirements' in schema['properties']
