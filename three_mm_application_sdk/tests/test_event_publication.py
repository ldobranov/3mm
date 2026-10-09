"""Additive SDK publication validation; no Core imports or implicit replay."""

from datetime import UTC, datetime

import pytest

from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError, SDK_VERSION


NOW = datetime(2026, 10, 9, 10, tzinfo=UTC)
ARGS = {'event_id': 'evt_' + 'a' * 32, 'payload': {'value': 1}, 'occurred_at': NOW}


@pytest.mark.parametrize('message', ['Checkpoint identity is invalid', 'Platform action is unsupported'])
def test_old_core_refusal_is_explicit_without_fallback(monkeypatch, message):
    client = ApplicationPlatformClient(None, 'test', b's' * 32)
    calls = []
    def refuse(action, payload):
        calls.append((action, payload))
        raise ApplicationPlatformError(message)
    monkeypatch.setattr(client, '_call', refuse)
    with pytest.raises(ApplicationPlatformError, match='does not support application event publication'):
        client.publish_event('record_changed', **ARGS)
    assert len(calls) == 1 and calls[0][0] == 'event.publish'
    assert calls[0][1] == {'publication': {'publication_request_version': 1,
        'publication_id': 'record_changed', 'event_id': ARGS['event_id'], 'payload': {'value': 1},
        'occurred_at': NOW.isoformat().replace('+00:00', 'Z')}}
    assert SDK_VERSION == '1.3'


def test_authority_refusal_is_not_misreported_or_retried(monkeypatch):
    client = ApplicationPlatformClient(None, 'test', b's' * 32)
    def refuse(*_args):
        raise ApplicationPlatformError('Platform action has no supported resource grant')
    monkeypatch.setattr(client, '_call', refuse)
    with pytest.raises(ApplicationPlatformError, match='no supported resource grant'):
        client.publish_event('record_changed', **ARGS)


@pytest.mark.parametrize('changes', [{'event_id': ''}, {'occurred_at': NOW.replace(tzinfo=None)},
    {'payload': {'value': float('inf')}}])
def test_invalid_publication_never_sends(monkeypatch, changes):
    client = ApplicationPlatformClient(None, 'test', b's' * 32)
    def send(*_args):
        pytest.fail('Invalid publication reached transport')
    monkeypatch.setattr(client, '_call', send)
    with pytest.raises(ValueError):
        client.publish_event('record_changed', **{**ARGS, **changes})


@pytest.mark.parametrize('fault', ['invalid', 'foreign_event', 'foreign_publication'])
def test_invalid_or_mismatched_receipt_is_refused(monkeypatch, fault):
    client = ApplicationPlatformClient(None, 'test', b's' * 32)
    receipt = {'publication_receipt_version': 1, 'event_id': ARGS['event_id'],
        'publication_id': 'record_changed', 'producer': {'kind': 'application',
            'core_installation_id': 'inst_' + 'a' * 32, 'application_installation_id': '1',
            'incarnation': 'b' * 32, 'module_id': 'org.example.reference'},
        'content_sha256': 'c' * 64, 'committed_at': NOW.isoformat()}
    if fault == 'invalid':
        receipt['producer'] = {'kind': 'device'}
    else:
        receipt['event_id' if fault == 'foreign_event' else 'publication_id'] = (
            'evt_' + 'd' * 32 if fault == 'foreign_event' else 'different')
    monkeypatch.setattr(client, '_call', lambda *_args: receipt)
    with pytest.raises(ApplicationPlatformError, match='Publication receipt'):
        client.publish_event('record_changed', **ARGS)
