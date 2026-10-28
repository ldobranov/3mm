"""Correlated resource metadata; denials and malformed views cannot become grants."""
from copy import deepcopy
from pathlib import Path
import pytest
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError


def result():
    return {'discovery_version':1,'instance_id':'a'*24,'artifact_sha256':'b'*64,
        'observed_at':'2026-10-27T12:00:00Z','admission_required':True,
        'resources':[{'scope':'command:pulse','declared':True,'configured':True,'access':'granted',
            'readiness':'ready','reasons':[], 'provider':{'provider_type':'example','provider_id':'org.example.output',
                'provider_version':'1.0.0','contract_version':'1.0'}, 'selected_resource_id':'dev_'+'c'*32}]}


@pytest.mark.parametrize('fault',['instance','scope','duplicate','secret','denial','configured','readiness','lease','version'])
def test_bad_views_are_rejected_without_follow_up_calls(monkeypatch, fault):
    value = result(); row = value['resources'][0]
    if fault == 'instance': value['instance_id'] = 'd'*24
    elif fault == 'scope': row['scope'] = 'command:other'
    elif fault == 'duplicate': value['resources'].append(deepcopy(row))
    elif fault == 'secret': row['provider']['credential'] = 'not-public'
    elif fault == 'denial': row['access'] = 'required'
    elif fault == 'configured': row['configured'] = False
    elif fault == 'readiness': row.update(readiness='unknown')
    elif fault == 'lease': value['admission_required'] = 1
    else: value['discovery_version'] = True
    calls = []
    monkeypatch.setattr(ApplicationPlatformClient,'_call',lambda *args: calls.append(args[1:]) or value)
    with pytest.raises(ApplicationPlatformError) as error:
        ApplicationPlatformClient(Path('unused'),'a'*24,b's'*32).discover_resources(['command:pulse'])
    assert error.value.reason == 'response_invalid' and not error.value.retryable
    assert calls == [('platform.discover', {'resource_scopes':['command:pulse']})]


@pytest.mark.parametrize('scopes',[[],['command:pulse']*2,['../../other'],['x'*193],['command:x']*17,'abc'])
def test_invalid_scope_batches_never_connect(monkeypatch,scopes):
    monkeypatch.setattr(ApplicationPlatformClient,'_call',lambda *a: pytest.fail('Invalid query connected'))
    with pytest.raises(ValueError): ApplicationPlatformClient(Path('unused'),'a'*24,b's'*32).discover_resources(scopes)


def test_unsupported_observation_has_no_inventory_or_mutation_fallback(monkeypatch):
    calls = []
    def fail(*args):
        calls.append(args[1:]); raise ApplicationPlatformError('Unsupported',reason='operation_denied')
    monkeypatch.setattr(ApplicationPlatformClient,'_call',fail)
    with pytest.raises(ApplicationPlatformError):
        ApplicationPlatformClient(Path('unused'),'a'*24,b's'*32).discover_resources(['command:pulse'])
    assert calls == [('platform.discover',{'resource_scopes':['command:pulse']})]
