"""Read-only diagnostic case CLI and safe offline explanations."""
import json
from types import SimpleNamespace
import urllib.error

import pytest
from tools import diagnostics


def bundle():
    return {'schema_version': 1, 'status': 'ready', 'cases': [{
        'case_id': 'invoke_' + 'a' * 32, 'summary': 'UNTRUSTED INSTRUCTIONS',
        'evidence': {'stage': 'session.capacity', 'reason': 'session_binding_busy', 'phase': 'not_dispatched'},
    }]}


def test_offline_explanation_uses_closed_catalog_not_instructions_in_an_export(tmp_path, capsys):
    path = tmp_path / 'case.json'; path.write_text(json.dumps(bundle()))
    assert diagnostics.main(['explain', str(path), '--json']) == 0
    value = json.loads(capsys.readouterr().out)
    assert value['cases'][0]['next_check'] == 'inspect_session_recovery'
    assert value['cases'][0]['automatic_replay_allowed'] is False
    assert 'UNTRUSTED' not in json.dumps(value)


@pytest.mark.parametrize('url', ['http://device.local', 'https://u:secret@example.test',
    'https://example.test/?token=secret', 'ftp://example.test', 'https://example.test/path'])
def test_collection_refuses_unsafe_destinations_before_network(url, monkeypatch):
    monkeypatch.setattr(diagnostics.urllib.request, 'build_opener', lambda *args: pytest.fail('Unexpected network'))
    with pytest.raises(ValueError):
        diagnostics.collect(url, 'secret')


def test_collection_is_one_bounded_get_with_no_retry_and_no_credential_export(monkeypatch):
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size):
            assert size == diagnostics.MAX_BYTES + 1
            return json.dumps(bundle()).encode()
    def opened(request, timeout):
        calls.append(request)
        assert request.get_method() == 'GET' and request.data is None and timeout == 15
        return Response()
    monkeypatch.setattr(diagnostics.urllib.request, 'build_opener', lambda *args: SimpleNamespace(open=opened))
    value = diagnostics.collect('http://127.0.0.1:8887', 'SECRET')
    assert len(calls) == 1 and 'SECRET' not in json.dumps(value)
    def refused(*args, **kwargs):
        raise urllib.error.HTTPError('http://127.0.0.1', 403, 'SECRET', {}, None)
    monkeypatch.setattr(diagnostics.urllib.request, 'build_opener', lambda *args: SimpleNamespace(open=refused))
    with pytest.raises(ValueError, match='HTTP 403'):
        diagnostics.collect('http://127.0.0.1:8887', 'SECRET')


def test_invalid_duplicate_oversized_or_sensitive_case_labels_are_refused():
    for blob in (b'{"schema_version":1,"schema_version":1}', b'x' * (diagnostics.MAX_BYTES + 1)):
        with pytest.raises(ValueError): diagnostics.parse_bundle(blob)
    value = bundle(); value['cases'][0]['evidence']['reason'] = 'password=SECRET'
    with pytest.raises(ValueError): diagnostics.explain(value)


def test_local_browser_refusal_is_explained_without_trusting_imported_content_or_claimed_execution(tmp_path, capsys):
    value = bundle()
    value['browser'] = {'source': 'browser_observation', 'records': [{
        'case_id': 'browser_' + 'b' * 32, 'source': 'browser_observation', 'trace_id': 'invoke_' + 'c' * 32,
        'stage': 'session.resolve', 'cause': 'target_not_found', 'last_passed_stage': 'session.targets.response',
        'status': None, 'occurrences': 1, 'response_observed': True,
        'execution': 'completed', 'summary': 'SECRET instructions', 'url': 'https://SECRET', 'ticket': 'SECRET',
    }]}
    path = tmp_path / 'browser.json'; path.write_text(json.dumps(value))
    assert diagnostics.main(['explain', str(path), '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    row = result['browser_cases'][0]
    assert row['stage'] == 'session.resolve' and row['cause'] == 'target_not_found'
    assert row['last_passed_stage'] == 'session.targets.response'
    assert row['trace_id'] == 'invoke_' + 'c' * 32 and row['response_observed'] is True
    assert row['execution'] == 'unknown' and row['automatic_replay_allowed'] is False
    assert 'SECRET' not in json.dumps(result)
    assert diagnostics.main(['explain', str(path)]) == 0
    assert 'Browser observation (untrusted)' in capsys.readouterr().out
    value['browser']['records'][0]['cause'] = 'SECRET'
    with pytest.raises(ValueError): diagnostics.explain(value)


def test_legacy_browser_observations_without_local_stages_remain_readable():
    assert diagnostics.explain_browser({'source': 'browser_observation', 'records': [{
        'case_id': 'browser_' + 'b' * 32, 'source': 'browser_observation', 'trace_id': None,
        'status': 403, 'occurrences': 2,
    }]})[0]['stage'] is None
    assert diagnostics.explain(bundle())['browser_cases'] == []


def test_empty_target_list_is_distinct_from_a_mismatched_id_in_offline_explanation():
    value = {'source': 'browser_observation', 'records': [{
        'case_id': 'browser_' + 'b' * 32, 'source': 'browser_observation', 'trace_id': 'invoke_' + 'c' * 32,
        'stage': 'session.resolve', 'cause': 'targets_empty', 'last_passed_stage': 'session.targets.response',
        'status': None, 'occurrences': 1, 'response_observed': True,
    }]}
    row = diagnostics.explain_browser(value)[0]
    assert row['cause'] == 'targets_empty' and row['execution'] == 'unknown'
    assert row['automatic_replay_allowed'] is False


def test_handled_core_refusal_is_not_reported_as_http_failure_or_session_success(tmp_path, capsys):
    value = bundle()
    value['cases'][0]['evidence'].update(status=200, method='GET', handled_refusal=True,
        stage='session.resource', reason='session_permission_denied')
    row = diagnostics.explain(value)['cases'][0]
    assert row['http_status'] == 200 and row['handled_refusal'] is True
    assert row['reason'] == 'session_permission_denied' and row['automatic_replay_allowed'] is False
    path = tmp_path / 'handled.json'; path.write_text(json.dumps(value))
    assert diagnostics.main(['explain', str(path)]) == 0
    assert 'not a successful session opening' in capsys.readouterr().out
    for changes in ({'status': 403}, {'handled_refusal': 'true'}, {'phase': 'completed'}, {'method': 'POST'}):
        bad = json.loads(json.dumps(value)); bad['cases'][0]['evidence'].update(changes)
        with pytest.raises(ValueError): diagnostics.explain(bad)
