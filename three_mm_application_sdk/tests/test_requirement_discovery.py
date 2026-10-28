"""Required/optional observations, identity fences and no hidden execution."""
from copy import deepcopy
from pathlib import Path

import pytest

from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError
from three_mm_application_sdk.tests.test_command_discovery import observation
from three_mm_protocol.platform_transport import PlatformDiscoveryV1, SCOPED_ACTIONS


def platform():
    return PlatformDiscoveryV1(instance_id='a'*24, transport_generation='1'*32,
        recovery_generation='2'*32, authority_revision=1, application_incarnation='3'*32,
        authority_epoch='4'*32, authority_mode='enforced', operations=sorted(SCOPED_ACTIONS)).model_dump(mode='json')


def requirement(name='output', *, required=True, binding='output'):
    return {'requirement_id': name, 'required': required,
        'operations': ['command.discover', 'command.submit'], 'binding_id': binding}


@pytest.fixture
def discovery(monkeypatch):
    class State:
        metadata = platform()
        command = observation()
        calls = []
    state = State()
    def call(client, action, payload):
        state.calls.append((action, payload, client.timeout_seconds))
        if action == 'platform.discover': return deepcopy(state.metadata)
        assert action == 'command.discover', 'Discovery attempted a mutation or inventory fallback'
        return deepcopy(state.command)
    monkeypatch.setattr(ApplicationPlatformClient, '_call', call)
    state.client = ApplicationPlatformClient(Path('unused'), 'a'*24, b's'*32)
    return state


@pytest.mark.parametrize('required, expected', [(True, 'blocked'), (False, 'degraded')])
@pytest.mark.parametrize('fault', ['version', 'operation'])
def test_unsupported_optional_function_degrades_without_dispatch(discovery, required, expected, fault):
    need = requirement(required=required)
    if fault == 'version': need['transport_contract_version'] = 2
    else: need['operations'].append('future.not_implemented')
    result = discovery.client.discover_requirements([need])
    assert result['status'] == expected
    assert result['requirements'][0]['supported'] is False
    assert result['requirements'][0]['command'] is None
    assert [item[0] for item in discovery.calls] == ['platform.discover']


def test_alias_requirements_observe_one_binding_without_selection(discovery):
    result = discovery.client.discover_requirements([requirement(), requirement('optional_output', required=False)])
    assert result['status'] == 'satisfied'
    assert result['admission_required'] is True and result['automatic_selection'] is False
    assert result['automatic_retry'] is False
    assert all(item['command']['selected_device_id'] == observation()['selected_device_id'] for item in result['requirements'])
    assert [item[0] for item in discovery.calls] == ['platform.discover', 'command.discover', 'platform.discover']


def test_transport_support_does_not_claim_resource_or_human_permission(discovery):
    result = discovery.client.discover_requirements([{'requirement_id':'events', 'operations':['event.publish']}])
    assert result['status'] == 'satisfied'
    assert result['requirements'][0]['command'] is None
    assert result['admission_required'] is True
    assert [item[0] for item in discovery.calls] == ['platform.discover']


@pytest.mark.parametrize('mode', ['review_required', 'compatibility'])
def test_other_authority_profiles_never_trigger_compatibility_fallback(discovery, mode):
    discovery.metadata['authority_mode'] = mode
    result = discovery.client.discover_requirements([requirement()])
    row = result['requirements'][0]
    assert result['status'] == 'blocked' and row['supported'] is True
    assert row['reason'] == 'scoped_authority_required' and row['command'] is None
    assert len(discovery.calls) == 1


@pytest.mark.parametrize('fault, expected', [('grant', 'access_required'), ('unavailable', 'resource_unavailable'),
    ('unknown', 'resource_unknown'), ('incompatible', 'binding_unavailable')])
def test_contract_access_and_readiness_remain_distinct(discovery, fault, expected):
    candidate = discovery.command['candidates'][0]
    if fault == 'grant':
        discovery.command.update(access='required', candidates=[], selected_device_id=None)
    elif fault == 'incompatible':
        candidate.update(compatible=False, selectable=False, blockers=['contract_version_mismatch'])
    else:
        candidate.update(readiness=fault, readiness_reason='health_stale' if fault == 'unknown' else 'device_offline')
    result = discovery.client.discover_requirements([requirement()])
    assert result['status'] == 'blocked'
    assert result['requirements'][0]['supported'] is True
    assert result['requirements'][0]['reason'] == expected
    if fault == 'grant':
        assert result['requirements'][0]['command']['candidates'] == []


@pytest.mark.parametrize('field', ['instance_id', 'transport_generation', 'recovery_generation',
    'authority_revision', 'application_incarnation', 'authority_epoch', 'authority_mode', 'operations'])
def test_changed_snapshot_is_discarded_without_retry(monkeypatch, field):
    calls = []
    def call(client, action, payload):
        calls.append(action)
        if action == 'command.discover': return observation()
        value = platform()
        if len(calls) == 3:
            value[field] = ('b'*24 if field == 'instance_id' else 'b'*32 if 'generation' in field or field in
                {'application_incarnation', 'authority_epoch'} else 2 if field == 'authority_revision'
                else 'review_required' if field == 'authority_mode' else ['platform.discover'])
        return value
    monkeypatch.setattr(ApplicationPlatformClient, '_call', call)
    client = ApplicationPlatformClient(Path('unused'), 'a'*24, b's'*32)
    with pytest.raises(ApplicationPlatformError) as error: client.discover_requirements([requirement()])
    assert error.value.reason in {'response_invalid', 'observation_changed'}
    assert not error.value.retryable and calls == ['platform.discover', 'command.discover', 'platform.discover']


@pytest.mark.parametrize('reason', ['operation_unsupported', 'operation_denied', 'operation_failed'])
def test_unavailable_optional_read_has_no_inventory_or_mutation_fallback(monkeypatch, reason):
    calls = []
    def call(client, action, payload):
        calls.append(action)
        if action == 'platform.discover': return platform()
        raise ApplicationPlatformError('Unavailable', reason=reason)
    monkeypatch.setattr(ApplicationPlatformClient, '_call', call)
    result = ApplicationPlatformClient(Path('unused'), 'a'*24, b's'*32).discover_requirements([requirement(required=False)])
    assert result['status'] == 'degraded' and result['requirements'][0]['reason'] == 'observation_unavailable'
    assert result['requirements'][0]['command'] is None
    assert calls == ['platform.discover', 'command.discover', 'platform.discover']


@pytest.mark.parametrize('fault', ['binding', 'inventory', 'signature'])
def test_invalid_optional_observation_is_not_softened(monkeypatch, fault):
    calls = []
    def call(client, action, payload):
        calls.append(action)
        if action == 'platform.discover': return platform()
        if fault == 'signature': raise ApplicationPlatformError('Invalid', reason='authentication_failed')
        value = observation()
        if fault == 'binding': value['binding_id'] = 'other'
        else: value['access'] = 'not_evaluated'
        return value
    monkeypatch.setattr(ApplicationPlatformClient, '_call', call)
    with pytest.raises(ApplicationPlatformError):
        ApplicationPlatformClient(Path('unused'), 'a'*24, b's'*32).discover_requirements([requirement(required=False)])
    assert calls == ['platform.discover', 'command.discover']


def test_one_absolute_deadline_without_mutating_the_shared_client(discovery, monkeypatch):
    import three_mm_application_sdk.discovery as module
    clock = iter([100, 101, 105, 109])
    monkeypatch.setattr(module.time, 'monotonic', lambda: next(clock))
    discovery.client.timeout_seconds = 10
    discovery.client.discover_requirements([requirement()])
    assert [item[2] for item in discovery.calls] == [9, 5, 1]
    assert discovery.client.timeout_seconds == 10


def test_expired_batch_does_not_restart_the_timeout_or_retry(discovery, monkeypatch):
    import three_mm_application_sdk.discovery as module
    clock = iter([100, 101, 111])
    monkeypatch.setattr(module.time, 'monotonic', lambda: next(clock))
    discovery.client.timeout_seconds = 10
    with pytest.raises(ApplicationPlatformError) as error: discovery.client.discover_requirements([requirement()])
    assert error.value.reason == 'deadline_exceeded' and not error.value.retryable
    assert [item[0] for item in discovery.calls] == ['platform.discover']


@pytest.mark.parametrize('fault', ['duplicate', 'count', 'required_bool', 'operation_duplicate', 'binding', 'extra'])
def test_invalid_batch_is_rejected_before_any_connection(discovery, fault):
    needs = [requirement()]
    if fault == 'duplicate': needs.append(requirement())
    elif fault == 'count': needs = [requirement('item_'+str(i)) for i in range(17)]
    elif fault == 'required_bool': needs[0]['required'] = 1
    elif fault == 'operation_duplicate': needs[0]['operations'].append('command.discover')
    elif fault == 'binding': needs[0]['operations'] = ['event.publish']
    else: needs[0]['target_device'] = 'dev_'+'1'*32
    with pytest.raises(ValueError): discovery.client.discover_requirements(needs)
    assert not discovery.calls
