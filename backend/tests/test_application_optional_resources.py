"""Absent optional bindings cannot block required work or acquire new authority."""
import os

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.module import ApplicationConnectorBinding, ApplicationExtensionInstallation as Installation
from backend.db.device import DeviceCapabilityProvider
from backend.services import application_authority_management as authority
from backend.services.application_resource_discovery import discover_resources
from backend.tests.test_application_authority_management import installed, source_subject, source_installed
from backend.tests.test_application_consent import state, preview, allow
from backend.tests.test_application_checkpoint_authority import store_checkpoint_package

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Actual sealed grants and read-only snapshots')


@pytest.fixture
def optional(state):
    s = state
    definition = s.validated.application_extension.model_dump(mode='json')
    definition['service']['sdk_version'] = '1.3'
    definition['optional_resources'] = ['connector:business_api']
    store_checkpoint_package(s, definition)
    return s


def require(s, scope):
    prepared = s.manager._prepare(1)
    with s.manager.keys.locked() as key, Session(s.engine) as db:
        return s.manager._require_grant(db, key, 1, prepared, scope)


def test_optional_absent_at_approval_then_appearing_requires_fresh_explicit_consent(optional):
    s = optional
    with s.engine.begin() as db: db.execute(update(ApplicationConnectorBinding).values(enabled=False))
    viewed = preview(s)
    assert viewed['scopes'] == viewed['selected_scopes'] == ['command:pulse']
    assert viewed['optional_resources'] == ['connector:business_api']
    assert viewed['unavailable_resources'] == [{'scope':'connector:business_api', 'reason':'connector_binding_unavailable'}]
    allow(s, viewed)
    assert require(s, 'command:pulse')
    row = discover_resources(s.engine, 1, 'a'*24, ['connector:business_api'])['resources'][0]
    assert row['declared'] is True and row['required'] is False
    assert row['provider'] is None and row['reasons'] == ['optional_resource_unavailable']
    with s.engine.begin() as db: db.execute(update(ApplicationConnectorBinding).values(enabled=True))
    assert require(s, 'command:pulse')
    with pytest.raises(authority.AuthorityManagementError): require(s, 'connector:business_api')
    fresh = preview(s)
    assert fresh['selected_scopes'] == ['command:pulse']  # Appearance never auto-selects.
    allow(s, fresh, scopes=['command:pulse','connector:business_api'])
    assert require(s, 'connector:business_api')


def test_selected_optional_loss_and_replacement_do_not_withdraw_required_work(optional):
    s = optional
    allow(s, preview(s), scopes=['command:pulse','connector:business_api'])
    assert require(s, 'connector:business_api')
    with s.engine.begin() as db: db.execute(update(ApplicationConnectorBinding).values(enabled=False))
    assert require(s, 'command:pulse')
    with pytest.raises(authority.AuthorityManagementError): require(s, 'connector:business_api')
    # Re-enabling changes the current connector revision; it cannot silently
    # adopt that resource under old consent even when its label is unchanged.
    with s.engine.begin() as db: db.execute(update(ApplicationConnectorBinding).values(enabled=True, authority_revision=authority.new_authority_generation()))
    assert require(s, 'command:pulse')
    with pytest.raises(authority.AuthorityManagementError): require(s, 'connector:business_api')


def test_required_resource_loss_and_revocation_still_deny(optional):
    s = optional
    allow(s, preview(s))
    status = s.manager.inspect(1)
    s.manager.revoke(1, actor_token=s.token, request_id=authority.new_authority_generation(),
        expected_revision=status['grant_record_revision'])
    with pytest.raises(authority.AuthorityManagementError): require(s, 'command:pulse')


def test_optional_command_can_be_unconfigured_without_waiving_author_schema_requirements(state):
    from backend.services.application_configuration import resolve_application_configuration, ApplicationConfigurationError
    s = state
    definition = s.validated.application_extension.model_dump(mode='json')
    definition.update(optional_resources=['command:pulse'])
    definition['service']['sdk_version'] = '1.3'
    manifest = s.validated.manifest.model_dump(mode='json')
    manifest['configuration_schema']['required'] = [key for key in manifest['configuration_schema'].get('required', []) if key != 'TARGET_DEVICE_ID']
    store_checkpoint_package(s, definition, manifest)
    configuration = {key:value for key,value in s.configuration.items() if key != 'TARGET_DEVICE_ID'}
    with s.engine.begin() as db: db.execute(update(Installation).values(configuration=configuration))
    assert preview(s)['scopes'] == ['connector:business_api']
    schema = {**manifest['configuration_schema'], 'required':['TARGET_DEVICE_ID']}
    with pytest.raises(ApplicationConfigurationError):
        resolve_application_configuration(schema, {}, s.validated.application_extension, existing=configuration)


def test_optional_command_provider_replacement_retains_required_connector_and_needs_review(state):
    s = state
    definition = s.validated.application_extension.model_dump(mode='json')
    definition['service']['sdk_version'] = '1.3'
    definition['optional_resources'] = ['command:pulse']
    store_checkpoint_package(s,definition)
    allow(s,preview(s),scopes=['command:pulse','connector:business_api'])
    assert require(s,'command:pulse')
    with s.engine.begin() as db: db.execute(update(DeviceCapabilityProvider).values(provider_version='2.0.0'))
    assert require(s,'connector:business_api')
    with pytest.raises(authority.AuthorityManagementError): require(s,'command:pulse')
    row = discover_resources(s.engine,1,'a'*24,['command:pulse'])['resources'][0]
    assert row['provider'] is None and row['reasons'] == ['resource_changed_review_required']
    fresh = preview(s)
    assert 'command:pulse' not in fresh['selected_scopes']
    allow(s,fresh,scopes=['command:pulse','connector:business_api'])
    assert require(s,'command:pulse')


def test_incompatible_optional_command_is_not_promoted_to_supported_or_granted(state):
    from copy import deepcopy
    s = state
    definition = s.validated.application_extension.model_dump(mode='json')
    definition['service']['sdk_version'] = '1.3'
    definition['optional_resources'] = ['command:pulse']
    store_checkpoint_package(s,definition)
    with Session(s.engine) as db: capabilities = deepcopy(db.get(DeviceCapabilityProvider,1).capabilities)
    incompatible = deepcopy(capabilities)
    incompatible[0]['contract']['contract_version'] = '99.0'
    with s.engine.begin() as db: db.execute(update(DeviceCapabilityProvider).values(capabilities=incompatible))
    viewed = preview(s)
    assert viewed['scopes'] == ['connector:business_api']
    allow(s,viewed)
    assert require(s,'connector:business_api')
    with pytest.raises(authority.AuthorityManagementError): require(s,'command:pulse')
    with s.engine.begin() as db: db.execute(update(DeviceCapabilityProvider).values(capabilities=capabilities))
    assert 'command:pulse' not in preview(s)['selected_scopes']


def test_optional_command_schema_mismatch_has_a_redacted_diagnostic(state):
    from copy import deepcopy
    s=state
    definition=s.validated.application_extension.model_dump(mode='json')
    definition['service']['sdk_version']='1.3';definition['optional_resources']=['command:pulse']
    store_checkpoint_package(s,definition)
    with Session(s.engine) as db:capabilities=deepcopy(db.get(DeviceCapabilityProvider,1).capabilities)
    capabilities[0]['contract']['actions']['pulse']['arguments_schema']['properties']['extra']={'type':'boolean'}
    with s.engine.begin() as db:db.execute(update(DeviceCapabilityProvider).values(capabilities=capabilities))
    viewed=preview(s)
    assert viewed['scopes']==['connector:business_api']
    assert viewed['unavailable_resources']==[{'scope':'command:pulse','reason':'command_schema_containment_not_evaluated'}]
