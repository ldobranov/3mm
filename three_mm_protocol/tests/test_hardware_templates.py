"""Data-only form instantiation; never import a hardware driver or open GPIO."""
import copy
import json

import pytest

from three_mm_protocol.character_display import CharacterDisplayProfileV1
from three_mm_protocol.character_display_package import manifest as display_manifest
from three_mm_protocol.hardware_profiles import hardware_profile
from three_mm_protocol.hardware_templates import (
    HardwareTemplateV1, describe_template, instantiate_template, validate_template,
)
from three_mm_protocol.module_manifest import ModuleManifestV2


def case():
    profile = CharacterDisplayProfileV1(driver='mock', columns=16)
    baseline = json.loads(json.dumps(display_manifest(profile)))
    template = {'hardware_template_version': 1, 'template_id': 'example.display',
        'name': 'An independently packaged display profile', 'help': 'No hardware is opened.',
        'required_features': ['module_hardware_profiles.v1'],
        'fields': [
            {'key': 'display_id', 'label': 'Display name', 'type': 'text', 'default': 'display.main',
                'maxlength': 64, 'pattern': '^[a-z][a-z0-9_.-]{0,63}$'},
            {'key': 'columns', 'label': 'Columns', 'type': 'number', 'default': 16, 'min': 1, 'max': 80},
            {'key': 'rows', 'label': 'Rows', 'type': 'select', 'default': 2,
                'options': [{'value': '2', 'label': 'Two'}, {'value': '4', 'label': 'Four'}]},
            {'key': 'backlight_active_high', 'label': 'Backlight active high', 'type': 'checkbox', 'default': True},
        ],
        'bindings': {
            'display_id': ['/configuration_defaults/display_id',
                '/registrations/0/contract/state_schema/properties/display_id/enum/0',
                '/registrations/0/contract/actions/write_frame/result_schema/properties/display_id/enum/0'],
            'columns': ['/configuration_defaults/columns', '/registrations/0/metadata/columns',
                '/registrations/0/contract/state_schema/properties/columns/enum/0',
                '/registrations/0/contract/actions/write_frame/result_schema/properties/columns/enum/0'],
            'rows': ['/configuration_defaults/rows', '/registrations/0/metadata/rows',
                '/registrations/0/contract/state_schema/properties/rows/enum/0',
                '/registrations/0/contract/actions/write_frame/result_schema/properties/rows/enum/0'],
            'backlight_active_high': ['/configuration_defaults/backlight_active_high',
                '/registrations/0/metadata/backlight_active_high'],
        }}
    configuration = {field['key']: field['default'] for field in template['fields']}
    return baseline, template, configuration


def test_generic_instantiation_binds_all_derived_digest_occurrences_and_preserves_authority():
    baseline, template, configuration = case()
    before = copy.deepcopy((baseline, template, configuration))
    configuration = {**configuration, 'columns': 20, 'rows': 4, 'display_id': 'front.panel', 'backlight_active_high': False}
    result = instantiate_template(baseline, template, configuration)
    parsed = ModuleManifestV2.model_validate(result)
    profile = hardware_profile(parsed)
    expected = CharacterDisplayProfileV1(driver='mock', columns=20, rows=4,
        display_id='front.panel', backlight_active_high=False)
    assert profile.configuration == expected.model_dump()
    assert result['module_id'] == 'org.3mm.character-display.' + expected.digest()
    assert parsed.registrations[0].contract == expected.contract()
    for key in ('permissions', 'entrypoints', 'compatibility', 'runtimes', 'capabilities', 'health_check'):
        assert result[key] == baseline[key]
    assert (baseline, template, before[2]) == before
    assert result == instantiate_template(baseline, template, configuration)
    assert instantiate_template(baseline, template, before[2]) == baseline


def test_form_uses_existing_bounded_frontend_shape_and_simulation_comes_from_profile():
    baseline, template, _ = case()
    description = describe_template(baseline, template)
    assert description == {'template_id': template['template_id'], 'name': template['name'],
        'simulated': True, 'help': template['help'], 'fields': template['fields']}
    model = validate_template(ModuleManifestV2.model_validate(baseline), template)
    assert isinstance(model, HardwareTemplateV1)
    assert model.required_features == ['module_hardware_profiles.v1']


@pytest.mark.parametrize('change', [
    {'columns': True}, {'columns': 20.0}, {'columns': '20'}, {'columns': 81},
    {'rows': '4'}, {'rows': 3}, {'backlight_active_high': 1},
    {'display_id': 'INVALID'}, {'display_id': 'a'*65}, {'display_id': ''},
    {'extra': 1},
])
def test_parameters_are_not_coerced_and_cannot_escape_declared_options_or_bounds(change):
    baseline, template, configuration = case()
    with pytest.raises(ValueError):
        instantiate_template(baseline, template, {**configuration, **change})


def test_missing_parameter_does_not_silently_fall_back_to_a_default():
    baseline, template, configuration = case()
    del configuration['rows']
    with pytest.raises(ValueError, match='fields do not match'):
        instantiate_template(baseline, template, configuration)


@pytest.mark.parametrize('pointer', [
    '/permissions/0', '/entrypoints/agent', '/module_id', '/version',
    '/compatibility/protocol', '/registrations/0/registration_id',
    '/registrations/0/metadata/profile_sha256', '/registrations/0/metadata/simulated',
    '/registrations/0/contract/capability_id', '/registrations/0/contract/contract_version',
    '/registrations/0/contract/state_schema/properties/columns/type',
    '/registrations/0/contract/state_schema/properties/columns/maximum',
    '/registrations/0/contract/actions/write_frame/arguments_schema/properties/text/maxLength',
    '/configuration_defaults/missing', '/configuration_defaults',
    '/registrations/00/metadata/columns', '/configuration_defaults/~bad',
])
def test_bindings_cannot_change_privileges_names_contract_structure_or_create_paths(pointer):
    baseline, template, _ = case()
    template['bindings']['columns'] = [pointer]
    with pytest.raises(ValueError):
        validate_template(baseline, template)


@pytest.mark.parametrize('change', ['duplicate_field', 'duplicate_pointer', 'unbound_field', 'wrong_default',
    'array_target', 'executable_key', 'oversized', 'unsupported_feature', 'oversized_pointer'])
def test_malformed_templates_are_refused_before_any_instantiation(change):
    baseline, template, _ = case()
    if change == 'duplicate_field': template['fields'].append(copy.deepcopy(template['fields'][0]))
    elif change == 'duplicate_pointer': template['bindings']['columns'].append('/configuration_defaults/rows')
    elif change == 'unbound_field': del template['bindings']['rows']
    elif change == 'wrong_default': template['fields'][1]['default'] = 20
    elif change == 'array_target': template['bindings']['columns'] = ['/registrations/0/contract/state_schema/properties/columns/enum']
    elif change == 'executable_key': template['validator'] = 'package.module:validate'
    elif change == 'oversized': template['help'] = 'x'*65536
    elif change == 'unsupported_feature': template['required_features'] = ['RUN shell']
    elif change == 'oversized_pointer': template['bindings']['columns'] = ['/configuration_defaults/'+'x'*513]
    with pytest.raises(ValueError): validate_template(baseline, template)


@pytest.mark.parametrize('pattern', [
    '.*', '^(a+)+$', '^[a-z]+$', '^(a|aa){0,63}$', '^a{0,513}$',
    '^a{5,2}$', r'^(a)\1$', '^[a-z]{0,63}[a-z]{0,63}$', '^[z-a]$',
])
def test_template_patterns_are_a_bounded_non_executable_subset(pattern):
    baseline, template, _ = case()
    template['fields'][0]['pattern'] = pattern
    with pytest.raises(ValueError): validate_template(baseline, template)


def test_profile_is_required_and_identity_must_be_derived_from_that_exact_baseline():
    baseline, template, _ = case()
    baseline['module_id'] = 'org.example.not-derived'
    with pytest.raises(ValueError, match='identity'):
        validate_template(baseline, template)
    baseline, template, _ = case()
    del baseline['registrations'][0]['metadata']['profile_sha256']
    with pytest.raises(ValueError, match='exact Agent-only'):
        validate_template(baseline, template)


def test_descriptor_roundtrip_remains_plain_json():
    baseline, template, configuration = case()
    wire = json.loads(json.dumps(template))
    assert instantiate_template(baseline, wire, configuration) == baseline
