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


def test_offline_recovery_evidence_keeps_capture_distinct_from_activation_and_ignores_untrusted_text(tmp_path,capsys):
    from backend.system.backups.evidence import checked_inventory
    from tools.recovery_result import checked_result
    path=tmp_path/'check.json'
    blob=dict(schema_version=1,kind='backup_inventory_check',scope='capture_preflight_only',archive_verified=False,
              ready_to_capture=True,inventory='available',file_count=41,listed_application_groups=2,
              unlisted_application_files=0,issues=[dict(severity='warning',code='state.application_separate_preparation',
              occurrences=1,message='private operator data')],private_path='private operator data')
    path.write_text(json.dumps(blob))
    assert diagnostics.main(['explain',str(path),'--json'])==0
    actual=capsys.readouterr().out
    assert 'will be refused' in actual and 'private operator data' not in actual
    assert diagnostics.main(['explain',str(path)])==0 and 'No existing archive' in capsys.readouterr().out
    for change in ({'inventory':'not_available'},{'scope':'restore'},{'archive_verified':True},
                   {'unlisted_application_files':42},{'file_count':True},{'issues':blob['issues']*2},
                   {'issues':[{**blob['issues'][0],'code':'private'}]}):
        with pytest.raises(ValueError): checked_inventory({**blob,**change})
    blocked=dict(blob,ready_to_capture=False,inventory='not_available',file_count=None,
                 listed_application_groups=None,unlisted_application_files=None)
    assert checked_inventory(blocked)['file_count'] is None
    file_result=dict(schema_version=1,kind='portable_recovery_check',scope='offline_archive_validation_only',
                     service_activation_tested=False,target_architecture='aarch64',state='not_verified',
                     reason='target_incompatible',next_check='private operator instructions')
    path.write_text(json.dumps(file_result))
    assert diagnostics.main(['explain',str(path)])==0
    actual=capsys.readouterr().out
    assert 'migration path' in actual and 'private' not in actual and 'not a signed attestation' in actual
    for change in ({'state':'validated'},{'service_activation_tested':True},{'reason':['private']}):
        with pytest.raises(ValueError): checked_result({**file_result,**change})


def test_local_peer_report_explanation_never_prints_payload_or_suggests_sender_actions(tmp_path, capsys):
    path = tmp_path / 'report.json'
    base = {'schema_version': 1, 'kind':'peer_report_observation', 'source':'local_outbound_slot',
            'module_id':'org.example.meter', 'link_id':'peer_'+'a'*32, 'report_id':'report_'+'b'*32,
            'state':'acknowledged', 'automatic_replay_allowed':False}
    for state in ('acknowledged','not_observed_in_scope','unavailable','outcome_unconfirmed'):
        path.write_text(json.dumps({**base, 'state':state, 'payload':'private details'}))
        assert diagnostics.main(['explain',str(path),'--json']) == 0
        report = json.loads(capsys.readouterr().out)
        assert report['state'] == state and report['automatic_replay_allowed'] is False
        assert 'not proof of non-delivery' in report['limitation'] and 'private' not in json.dumps(report)
        assert diagnostics.main(['explain',str(path)]) == 0
        assert state in capsys.readouterr().out
    for changes in ({'state':['private']}, {'schema_version':True}, {'source':'remote'},
                    {'automatic_replay_allowed':True}, {'link_id':'not-a-link'}, {'module_id':'private/path'}):
        with pytest.raises(ValueError):
            diagnostics.parse_bundle(json.dumps({**base, **changes}).encode())


def test_database_sample_read_is_closed_vocabulary_not_a_root_cause_claim(tmp_path, capsys):
    path = tmp_path / 'sample.json'
    row = {'source':'devices', 'observed':4, 'longest_ms':120, 'open_at_end':1, 'sql':'private contents'}
    payload = {'schema_version':1, 'kind':'sqlite_write_sample', 'coverage':'new_core_engine_connections',
               'window_ms':5001, 'limited':False, 'families':[row], 'path':'private location'}
    path.write_text(json.dumps(payload))
    assert diagnostics.main(['explain', str(path), '--json']) == 0
    output = capsys.readouterr().out
    assert 'cannot identify' in output and 'private' not in output and json.loads(output)['families'][0]['observed'] == 4
    assert diagnostics.main(['explain', str(path)]) == 0 and 'devices: 4 observed' in capsys.readouterr().out
    for invalid in ([row, row], [{**row, 'longest_ms':5010}], [{**row, 'source':['devices']}], [{**row,'open_at_end':True}]):
        with pytest.raises(ValueError):
            diagnostics.parse_bundle(json.dumps({**payload, 'families':invalid}).encode())


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


def test_application_support_file_cannot_inject_process_text_or_a_foreign_case():
    value = bundle()
    value.update(kind='application_support',
        application={'instance_id':'b'*24, 'artifact_sha256':'c'*64, 'observation_revision':'d'*64, 'name':'SECRET'},
        service={'state':'observed','supervision':{'state':'active','result':'success','restart_count':0},'log':'SECRET'},
        coverage={'failure_history':'ready'})
    evidence = value['cases'][0]['evidence']
    evidence.update(instance_id='b'*24, application_revision='d'*64)
    result = diagnostics.explain(value)
    assert result['application']['automatic_restarts'] == 0 and 'SECRET' not in json.dumps(result)
    cmd = dict(reference='cmd_'+'2'*32,status='found',recorded_state='succeeded',linked_task=None,
               device_event_recorded=False)
    value['work'] = {**cmd, 'delivery':{'recorded_attempts':2,'queue_to_latest_offer_seconds':19,
                                        'physical_time':'SECRET'}}
    assert diagnostics.explain(value)['work']['delivery'] == {'recorded_attempts':2,'queue_to_latest_offer_seconds':19}
    for attempts, seconds in ((True,0),(0,2),(1,-1),(1,True),(1,10**12)):
        value['work']['delivery'] = {'recorded_attempts':attempts,'queue_to_latest_offer_seconds':seconds}
        with pytest.raises(ValueError): diagnostics.explain(value)
    value['work']=cmd  # Earlier saved evidence: never fabricate timing.
    assert 'delivery' not in diagnostics.explain(value)['work']
    value['service']['supervision']['result'] = 'arbitrary private text'
    with pytest.raises(ValueError): diagnostics.explain(value)
    value['service']['supervision'] = {}
    evidence['application_revision'] = 'f'*64
    with pytest.raises(ValueError): diagnostics.explain(value)
