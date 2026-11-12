import pytest
from pydantic import ValidationError
from packages.protocol import ModuleManifestV2
from packages.protocol.hardware_profiles import hardware_profile, profile_digest, validate_hardware_approval


def manifest(**changes):
    configuration = {'bus': 1, 'address': 39, 'layout': 'fixed-example'}
    value = {'manifest_version': 2, 'module_id': 'org.example.hardware', 'name': 'Example',
        'version': '1.0.0', 'runtimes': ['agent'], 'entrypoints': {'agent': 'builtin:example'},
        'compatibility': {'protocol': '1.0', 'architectures': ['any']},
        'permissions': ['hardware.gpio'], 'capabilities': {'provides': ['example.output']},
        'configuration_defaults': configuration,
        'health_check': {'type': 'file_exists', 'path': 'health/ready'},
        'registrations': [{'kind': 'capability', 'registration_id': 'example.output',
            'metadata': {'profile_sha256': profile_digest(configuration), 'simulated': False}}]}
    value.update(changes)
    return ModuleManifestV2.model_validate(value)


def test_generic_declaration_and_consent_bind_device_package_profile_not_a_module_name():
    m = manifest()
    profile = hardware_profile(m)
    approval = {'device_id': 'dev_'+'a'*32, 'package_sha256': 'b'*64,
                'profile_sha256': profile.profile_sha256}
    assert validate_hardware_approval(m, approval, device_id=approval['device_id'],
                                     package_sha256='b'*64).model_dump()['schema_version'] == 1
    for field, changed in [('device_id', 'dev_'+'c'*32), ('package_sha256', 'c'*64),
                           ('profile_sha256', 'c'*64)]:
        with pytest.raises(ValueError, match='does not match'):
            validate_hardware_approval(m, {**approval, field: changed},
                device_id=approval['device_id'], package_sha256='b'*64)
    with pytest.raises(ValueError, match='required'):
        validate_hardware_approval(m, None, device_id=approval['device_id'], package_sha256='b'*64)
    with pytest.raises(ValidationError):
        validate_hardware_approval(m, {**approval, 'write_frame': True},
            device_id=approval['device_id'], package_sha256='b'*64)


def test_profile_changes_and_untrusted_entrypoints_cannot_reuse_declaration():
    m = manifest()
    with pytest.raises(ValueError, match='digest'):
        hardware_profile(manifest(configuration_defaults={**m.configuration_defaults, 'address': 38}))
    with pytest.raises(ValueError, match='trusted Agent'):
        hardware_profile(manifest(entrypoints={'agent': 'arbitrary.py'}))
    with pytest.raises(ValueError, match='trusted Agent'):
        hardware_profile(manifest(permissions=['data.write']))


def test_simulation_is_not_physical_approval_and_requires_a_real_boolean():
    m = manifest()
    registration = m.registrations[0].model_dump()
    with pytest.raises(ValueError, match='disagree'):
        hardware_profile(manifest(registrations=[{**registration,
            'metadata': {**registration['metadata'], 'simulated': 1}}]))
    simulated = manifest(registrations=[{**registration,
        'metadata': {**registration['metadata'], 'simulated': True}}])
    assert validate_hardware_approval(simulated, None, device_id=None, package_sha256='b'*64) is None
    with pytest.raises(ValueError, match='does not match'):
        validate_hardware_approval(simulated, {'device_id': 'dev_'+'a'*32,
            'package_sha256': 'b'*64, 'profile_sha256': hardware_profile(m).profile_sha256},
            device_id='dev_'+'a'*32, package_sha256='b'*64)
