"""Host observations are closed metadata, never error text or execution authority."""
import json

import pytest

from packages.protocol.diagnostics import (
    HOST_FAILURE_STAGES, HOST_FAILURE_REASONS, DiagnosticSession, validated_host_failure,
)
from packages.protocol.diagnostic_snapshot import read_export, validate_record


def detail():
    return dict(version=1, stage='application.host_handler', reason='host_value_error',
                duration_ms=123.5)


@pytest.mark.parametrize('changes', [
    {'version': True}, {'version': 2}, {'stage': 'private payload'}, {'stage': []},
    {'reason': 'Bearer private'}, {'reason': []}, {'duration_ms': True},
    {'duration_ms': -1}, {'duration_ms': float('nan')}, {'duration_ms': float('inf')},
    {'duration_ms': 10**1000}, {'error': 'private'}, {'retryable': True},
])
def test_malformed_or_private_host_detail_is_not_a_diagnostic_channel(changes):
    value = {**detail(), **changes}
    assert validated_host_failure(value) is None


@pytest.mark.parametrize('value', [None, [], 'private', {}, {'version': 1}])
def test_missing_or_incomplete_detail_is_ignored(value):
    assert validated_host_failure(value) is None


def test_all_fixed_host_labels_survive_bounded_record_and_export_validation():
    # One record per fresh allocation avoids turning a rate drop into a pass.
    for stage in HOST_FAILURE_STAGES:
        for reason in HOST_FAILURE_REASONS:
            value = {**detail(), 'stage': stage, 'reason': reason}
            assert validated_host_failure(value) == value
            recorder = DiagnosticSession('core', '1.0')
            recorder.start()
            recorder.record(trace_id='invoke_' + 'a'*32, stage=stage, reason=reason,
                duration_ms=value['duration_ms'], result='error', operation='application.invoke',
                instance_id='1'*24)
            rows = recorder.snapshot()['records']
            assert len(rows) == 1 and validate_record(rows[0]) == rows[0]
            with recorder.export() as chunks:
                assert read_export(b''.join(chunks))['records'] == rows
            assert len(json.dumps(rows[0])) < 2048
