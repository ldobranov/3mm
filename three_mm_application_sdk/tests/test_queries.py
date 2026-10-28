import pytest

from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError, OperationContext
from three_mm_platform_wire import COMPATIBILITY_ACTIONS, SCOPED_ACTIONS


def client():
    return ApplicationPlatformClient('/not-a-socket', 'a'*24, b's'*32)


def test_query_uses_scoped_wire_once_and_preserves_provider_contract_metadata(monkeypatch):
    seen = []
    answer = dict(query_version=1, binding_id='directory', provider_instance_id='b'*24,
        contract_digest='c'*64, output={'label': 'Здравей'})
    def call(action, payload): seen.append((action, payload)); return answer
    value = client(); monkeypatch.setattr(value, '_call', call)
    assert value.query('directory', arguments={'reference': 'x'}) == answer
    assert seen == [('query.request', {'binding_id': 'directory', 'arguments': {'reference': 'x'}})]
    assert 'query.request' in SCOPED_ACTIONS and 'query.request' not in COMPATIBILITY_ACTIONS


@pytest.mark.parametrize('answer', [None, {}, {'query_version': True},
    dict(query_version=1, binding_id='foreign', provider_instance_id='b'*24, contract_digest='c'*64, output={})])
def test_wrong_query_response_never_becomes_a_valid_result(monkeypatch, answer):
    value = client(); monkeypatch.setattr(value, '_call', lambda *args: answer)
    with pytest.raises(ApplicationPlatformError) as error: value.query('directory', arguments={})
    assert error.value.reason == 'response_invalid'


def test_unconfirmed_query_is_never_retried(monkeypatch):
    seen = []
    def call(*args):
        seen.append(args)
        raise ApplicationPlatformError('Lost response', reason='transport_unavailable')
    value = client(); monkeypatch.setattr(value, '_call', call)
    with pytest.raises(ApplicationPlatformError): value.query('directory', arguments={})
    assert len(seen) == 1


@pytest.mark.parametrize('arguments', [{'x': float('nan')}, {'x': 'a'*8193}])
def test_invalid_query_arguments_are_refused_before_transport(monkeypatch, arguments):
    value = client(); monkeypatch.setattr(value, '_call', lambda *args: pytest.fail('Must not send'))
    with pytest.raises(ValueError): value.query('directory', arguments=arguments)


def caller():
    return dict(instance_id='a'*24, module_id='org.example.consumer', artifact_sha256='b'*64,
        binding_id='directory', contract_digest='c'*64)


@pytest.mark.parametrize('extra', [{'audience': 'public'}, {'user_id': 1},
    {'permission_ids': ['read']}, {'platform_administrator': True}, {'idempotency_key': 'replay'}])
def test_application_caller_cannot_borrow_human_identity_or_replay_permission(extra):
    with pytest.raises(ValueError): OperationContext.from_platform(dict(audience='internal', application_caller=caller()) | extra)


def test_application_actor_keeps_host_executor_without_delegating_a_user():
    context = OperationContext.from_platform(dict(audience='internal', application_caller=caller(),
        executor=dict(module_id='org.example.provider', instance_id='d'*24, artifact_sha256='e'*64)))
    assert context.actor.kind == 'application' and context.actor.application_instance_id == 'a'*24
    assert context.executor.instance_id == 'd'*24 and not context.has_application_permission('read')


def test_query_cannot_wait_inside_a_scoped_relational_transaction():
    from three_mm_application_sdk.transaction_guard import relational_transaction_active
    token = relational_transaction_active.set(True)
    try:
        with pytest.raises(RuntimeError, match='inside a scoped relational transaction'):
            client().query('directory', arguments={})
    finally: relational_transaction_active.reset(token)


def test_query_observation_preserves_the_full_authority_package_version_budget():
    from three_mm_protocol.application_resources import ResourceProviderV1
    version = '1.0.0+'+'a'*90
    assert len(version) == 96
    assert ResourceProviderV1(provider_type='application_query', provider_id='org.example.provider',
        provider_version=version).provider_version == version
