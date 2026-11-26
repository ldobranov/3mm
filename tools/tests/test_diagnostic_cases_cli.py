"""Read-only diagnostic case CLI and safe offline explanations."""
import json
from types import SimpleNamespace
import urllib.error

import pytest
from tools import diagnostics


def bundle():
    return {'schema_version': 1, 'status': 'ready', 'selection': {'trace_id': None, 'result':'found'}, 'cases': [{
        'case_id': 'invoke_' + 'a' * 32, 'summary': 'UNTRUSTED INSTRUCTIONS',
        'evidence': {'stage': 'session.capacity', 'reason': 'session_binding_busy', 'phase': 'not_dispatched'},
    }]}


def test_selected_attempt_never_inherits_another_attempts_step_time(tmp_path, capsys):
    from backend.system.diagnostics.cases import build_cases
    from backend.system.diagnostics.failures import RecentHttpFailures
    ring = RecentHttpFailures()
    first, latest = ('invoke_' + char * 32 for char in 'ab')
    for trace, elapsed in ((first, 5), (latest, 271)):
        ring.record(trace_id=trace, method='POST', route='/api/v1/devices/{device_id}/heartbeat',
                    status=500, duration_ms=elapsed + 2, details=[('device.credential_write', 'database_busy')],
                    step_timing=('device.credential', elapsed))
    def snapshot(trace):
        return build_cases(ring.snapshot(), {}, {'probe_status': 'complete'}, trace_id=trace)
    case, = diagnostics.explain(snapshot(latest))['cases']
    assert (case['step_timing_scope'], case['failed_step_ms']) == ('this_request', 271)
    selected = snapshot(first)
    case, = diagnostics.explain(selected)['cases']
    assert (case['case_id'], case['timing_trace_id'], case['step_timing_scope']) == (
        first, latest, 'not_retained_for_this_request')
    assert not {'failed_step_ms', 'duration_ms', 'last_passed_stage'} & case.keys()
    f = tmp_path/'selection.json'
    f.write_text(json.dumps(selected))
    assert diagnostics.main(['explain', str(f)]) == 0
    text = capsys.readouterr().out
    assert 'not this request' in text and '271 ms' not in text
    selected['cases'][0]['evidence']['trace_ids'] = [latest]
    with pytest.raises(ValueError): diagnostics.explain(selected)
    selected['cases'][0]['timing_trace_id'] = first
    with pytest.raises(ValueError): diagnostics.explain(selected)


def test_exact_offline_lookup_from_full_file_preserves_attempt_and_evidence_boundaries(tmp_path, capsys, monkeypatch):
    from backend.system.diagnostics.cases import build_cases
    from backend.system.diagnostics.failures import RecentHttpFailures
    def not_online(*args, **kwargs):
        pytest.fail('A saved request lookup must never use transport or prompt for credentials.')
    monkeypatch.setattr(diagnostics, '_private_token', not_online)
    monkeypatch.setattr(diagnostics, '_read', not_online)
    old, latest, detail_only, browser_only, absent = ('invoke_' + ch * 32 for ch in 'abcde')
    ring = RecentHttpFailures()
    for trace, duration in ((old, 2), (latest, 33)):
        ring.record(trace_id=trace, method='POST', route='/heartbeat', status=500, duration_ms=duration,
                    details=[('device.heartbeat_write', 'database_busy')], step_timing=('device.identity_match', duration))
    recording = {'records': [{'trace_id': detail_only, 'extra': 'PRIVATE_MARKER'}]}
    value = build_cases(ring.snapshot(), recording, {'probe_status': 'complete'})
    value['browser'] = {'source': 'browser_observation', 'records': [{
        'case_id': 'browser_' + '1' * 32, 'source': 'browser_observation',
        'trace_id': browser_only, 'occurrences': 1, 'stage': 'session.resolve', 'cause': 'target_not_found'}]}
    path = tmp_path / 'saved.json'
    path.write_text(json.dumps(value))
    def read(trace):
        assert diagnostics.main(['explain', str(path), '--trace-id', trace, '--json']) == 0
        out = capsys.readouterr().out
        assert 'PRIVATE_MARKER' not in out
        return json.loads(out)
    record = read(old)
    case, = record['cases']
    assert record['selection_source'] == 'saved_report' and not record['browser_cases']
    assert (case['case_id'], case['timing_trace_id'], case['step_timing_scope']) == (
        old, latest, 'not_retained_for_this_request')
    assert not {'failed_step_ms', 'duration_ms', 'last_passed_stage'} & case.keys()
    assert read(latest)['cases'][0]['failed_step_ms'] == 33
    assert read(detail_only)['selection'] == dict(trace_id=detail_only, result='found', failure_cases=0, detailed_records=1)
    separate = read(browser_only)
    assert separate['selection']['result'] == 'not_found_in_retained_evidence' and separate['browser_cases'][0]['execution'] == 'unknown'
    assert not read(absent)['cases']
    selected = build_cases(ring.snapshot(), recording, {'probe_status': 'complete'}, trace_id=latest)
    with pytest.raises(ValueError, match='different request'):
        diagnostics.explain_saved_request(selected, old)
    value['cases'][0]['evidence']['trace_ids'] = [old, latest]
    with pytest.raises(ValueError, match='identities'):
        diagnostics.explain_saved_request(value, old)


def test_trace_without_failure_differs_from_no_observation_and_never_implies_execution(tmp_path, capsys):
    from backend.system.diagnostics.cases import build_cases
    trace = 'platform_'+'4'*32
    path = tmp_path/'case.json'
    for rows in ([], [{'trace_id':trace, 'private_text':'DO NOT PRINT'}]):
        actual = build_cases({'status':'ready', 'records':[]}, {'records':rows},
                             {'probe_status':'complete'}, trace_id=trace)
        path.write_text(json.dumps(actual))
        assert diagnostics.main(['explain',str(path),'--json']) == 0
        output = capsys.readouterr().out
        assert 'DO NOT PRINT' not in output
        summary = json.loads(output)
        assert summary['selection'] == dict(trace_id=trace, result='found' if rows else 'not_found_in_retained_evidence',
                                            failure_cases=0, detailed_records=len(rows))
        assert summary['cases'] == [] and 'not proof' in summary['limitation']
        assert diagnostics.main(['explain',str(path)]) == 0
        assert f'0 failure cases; {len(rows)} detailed records' in capsys.readouterr().out
        actual['selection']['result'] = 'not_found_in_retained_evidence' if rows else 'found'
        with pytest.raises(ValueError): diagnostics.explain(actual)


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


def test_saved_case_is_private_complete_readable_and_never_overwrites(tmp_path, monkeypatch):
    import os
    import stat
    target = tmp_path/'operator.json'
    diagnostics._save_new(target,bundle())
    assert diagnostics.explain(diagnostics.parse_bundle(target.read_bytes()))['cases'][0]['http_status'] is None
    if os.name == 'posix':
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    first = target.read_bytes()
    with pytest.raises(ValueError):
        diagnostics._save_new(target,{'different':True})
    assert target.read_bytes() == first and list(tmp_path.iterdir()) == [target]
    monkeypatch.setattr(diagnostics, 'MAX_BYTES',12)
    with pytest.raises(ValueError):
        diagnostics._save_new(tmp_path/'too-long',bundle())
    assert list(tmp_path.iterdir()) == [target]


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
    for claim in (False, True):
        value['work']['delivery']['permit_claimed'] = claim
        assert diagnostics.explain(value)['work']['delivery']['permit_claimed'] is claim
    value['work']['delivery']['permit_claimed'] = 'PRIVATE_MARKER'
    with pytest.raises(ValueError): diagnostics.explain(value)
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


def resource_bundle():
    instance = 'b' * 24
    return dict(schema_version=1, kind='application_support', status='ready', cases=[],
        application=dict(instance_id=instance, artifact_sha256='c'*64, observation_revision='d'*64),
        coverage=dict(failure_history='ready'), service=dict(schema_version=1, state='observed',
            scope='unit_cgroup', unit=f'3mm-application-extension@{instance}.service',
            limits=dict(cpu=dict(state='os_enforced', quota_usec=100000, period_usec=100000),
                        memory=dict(state='unavailable', reason='controller_not_available_on_host'),
                        tasks=dict(state='not_set_here')),
            hierarchy_limits=dict(cpu=dict(state='os_enforced', source='parent', quota_usec=40000,
                                           period_usec=80000, complete=True, path='PRIVATE PATH'),
                                  memory=dict(state='unavailable', complete=False),
                                  tasks=dict(state='no_visible_cap', complete=True)),
            usage=dict(memory_bytes=None, tasks=0, command='PRIVATE COMMAND')))


def test_saved_resource_sample_explains_shared_ceiling_and_never_invents_cpu_usage(tmp_path, capsys):
    value = resource_bundle()
    path = tmp_path / 'saved.json'
    path.write_text(json.dumps(value))
    assert diagnostics.main(['explain', str(path)]) == 0
    out = capsys.readouterr().out
    assert '1/2 CPU of bandwidth (40000/80000' in out and '(shared parent)' in out and 'hierarchy incomplete' in out
    assert 'no cap found in the visible groups' in out and 'RAM unavailable; tasks (including threads) 0' in out
    assert diagnostics.main(['explain', str(path), '--json']) == 0
    raw = capsys.readouterr().out
    saved = json.loads(raw)['application']['resources']
    assert 'PRIVATE' not in raw and saved['usage'] == {'memory_bytes':None, 'tasks':0}
    assert saved['hierarchy_limits']['cpu']['complete'] is True
    del value['service']['hierarchy_limits']
    assert 'hierarchy_limits' not in diagnostics.explain(value)['application']['resources']
    del value['service']['limits'], value['service']['usage']
    assert 'resources' not in diagnostics.explain(value)['application']


@pytest.mark.parametrize('field,mutate', [
    ('', lambda s:s.update(unit='3mm-agent.service')),
    ('', lambda s:s.update(state='not_running')),
    ('usage', lambda s:s.update(tasks=True)), ('usage', lambda s:s.update(memory_bytes=2**64)),
    ('limits', lambda s:s['cpu'].update(period_usec=0)),
    ('limits', lambda s:s['memory'].update(reason='arbitrary_private_reason')),
    ('hierarchy_limits', lambda s:s['cpu'].update(source='unit')),
    ('hierarchy_limits', lambda s:s['cpu'].update(quota_usec=80001)),
    ('hierarchy_limits', lambda s:s['cpu'].update(source='private_mount')),
    ('hierarchy_limits', lambda s:s['tasks'].update(complete=False)),
    ('hierarchy_limits', lambda s:s['memory'].update(complete=True)),
])
def test_saved_resource_sample_refuses_mixed_or_misleading_measurements(field, mutate):
    value = resource_bundle()
    service = value['service']
    mutate(service[field] if field else service)
    with pytest.raises(ValueError):
        diagnostics.explain(value)
