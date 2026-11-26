import json
from copy import deepcopy

import pytest

from backend.system.diagnostics.cases import build_cases
from backend.system.diagnostics.failures import RecentHttpFailures
from tools.diagnostic_comparison import compare
from tools.diagnostics import main


def snapshots():
    t = [0.]
    ring = RecentHttpFailures(clock=lambda: t[0])
    def record(suffix):
        ring.record(trace_id='invoke_' + suffix * 32, method='POST', route='/example', status=500,
                    duration_ms=1, details=[('core.database','database_busy')])
    def snapshot():
        return build_cases(ring.snapshot(), {}, {'probe_status': 'complete'})
    record('a')
    first = snapshot()
    t[0] += 1
    record('b')
    return ring, t, first, snapshot(), snapshot


def test_compare_counts_repetitions_not_groups_and_prints_only_fixed_labels(tmp_path,capsys):
    _, _, first, last, _ = snapshots()
    assert len(first['cases']) == len(last['cases']) == 1
    last['cases'][0]['summary'] = 'PRIVATE_MARKER'
    paths=[tmp_path / 'before.json',tmp_path / 'after.json']
    for path,value in zip(paths,(first,last)):
        path.write_text(json.dumps(value))
    assert main(['compare',*map(str, paths),'--json']) == 0
    output = capsys.readouterr().out
    assert 'PRIVATE_MARKER' not in output
    assert json.loads(output)['by_reason'] == {'database_busy':1}
    assert compare(first,first)['new_recorded_failures'] == 0


def test_reset_expiry_restart_and_old_exports_are_not_improvements():
    ring, t, first, last, snapshot = snapshots()
    t[0] += ring.RETENTION_SECONDS + 1
    assert compare(first,snapshot())['status'] == 'evidence_lost_or_expired'
    assert ring.clear_history(first['failure_history']['history_id']) == 'cleared'
    assert compare(first,snapshot())['status'] == 'history_cleared'
    restarted=build_cases(RecentHttpFailures().snapshot(), {}, {'probe_status':'complete'})
    assert compare(last,restarted)['status'] == 'core_process_changed'
    legacy=deepcopy(first); del legacy['failure_history']['history_id']
    result=compare(legacy,last)
    assert result['status']=='history_epoch_unknown' and result['new_recorded_failures'] is None
    assert (result['before_retained'],result['after_retained'])==(1,2)
    partial=deepcopy(last); partial['failure_history']={'status':'busy'}
    assert compare(first,partial)['status']=='incomplete_history'


def test_filtered_or_untrusted_counts_are_refused():
    _, _, first, last, _ = snapshots()
    last['selection']['trace_id']=first['cases'][0]['case_id']
    with pytest.raises(ValueError): compare(first,last)
    last['selection']['trace_id']=None
    last['cases'][0]['evidence']['occurrences']=True
    with pytest.raises(ValueError): compare(first,last)


@pytest.mark.parametrize('fault', ['future_format','boolean_version','future_catalog','future_history','stripped_cases'])
def test_unsupported_or_truncated_report_is_not_a_clean_observation(fault):
    _, _, before, after, _ = snapshots()
    if fault == 'stripped_cases': after['cases'].clear()
    elif fault == 'future_history': after['failure_history']['schema_version'] = 99
    elif fault == 'future_catalog': after['catalog_version'] = 99
    else: after['schema_version'] = True if fault == 'boolean_version' else 99
    with pytest.raises(ValueError): compare(before, after)


def test_same_database_cause_at_distinct_steps_is_not_interchangeable():
    _, _, first, last, _ = snapshots()
    ev = deepcopy(last['cases'][0])
    ev['evidence'].update(stage='device.heartbeat_write', occurrences=3)
    last['cases'].append(ev)
    result = compare(first, last)
    assert result['by_reason'] == {'database_busy': 4}
    assert result['new_steps'] == [
        {'stage': 'device.heartbeat_write', 'reason': 'database_busy', 'occurrences': 3},
        {'stage': 'core.database', 'reason': 'database_busy', 'occurrences': 1}]
    del last['cases'][0]
    missing = compare(first, last)
    assert missing['status'] == 'evidence_lost_or_expired' and missing['new_steps'] is None
    assert missing['before_steps'][0]['stage'] == 'core.database'
    assert missing['after_steps'][0]['stage'] == 'device.heartbeat_write'
    last['cases'][0]['evidence']['stage'] = 'arbitrary-text'
    with pytest.raises(ValueError): compare(first,last)


def test_retained_times_cover_every_group_and_are_not_a_downtime_metric():
    _, _, before, after, _ = snapshots()
    after['cases'][0]['evidence'].update(first_timestamp=102., timestamp=107.25)
    earlier = deepcopy(after['cases'][0])
    earlier['evidence'].update(first_timestamp=100.5, timestamp=105.)
    after['cases'].append(earlier)
    assert compare(before, after)['after_retained_times'] == {
        'first_utc':'1970-01-01T00:01:40.500+00:00','last_utc':'1970-01-01T00:01:47.250+00:00','span_seconds':6.75}
    for missing_or_unusable in (None, True, 'not a clock', 108., float('inf')):
        earlier['evidence']['first_timestamp'] = missing_or_unusable
        result = compare(before, after)
        assert result['after_retained_times'] is None and result['after_retained'] == 4
