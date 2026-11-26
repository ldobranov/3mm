"""Compare recorded Core failures only when two bounded snapshots are continuous."""
from collections import Counter
from datetime import datetime, timezone
import re
from typing import NamedTuple

from backend.system.diagnostics.catalog import CASE_REASONS, CASE_STAGES, CATALOG_VERSION

_DROPS = ('rate', 'busy', 'invalid', 'evicted', 'expired')
_MAX = 2**63 - 1


class _History(NamedTuple):
    at: datetime
    process: str | None
    epoch: str | None
    dropped: tuple[int, ...]
    counts: Counter[tuple[str, str]]
    bounds: tuple[float, float] | None


def _count(n, minimum):
    if type(n) is not int or not minimum <= n < _MAX:
        raise ValueError('Unsupported diagnostic counter.')
    return n


def _id(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{32}', value) is not None


def _snapshot(value):
    if (not isinstance(value, dict) or value.get('kind') is not None
            or type(value.get('schema_version')) is not int or value['schema_version'] != 1
            or type(value.get('catalog_version')) is not int or not 1 <= value['catalog_version'] <= CATALOG_VERSION
            or value.get('status') not in ('ready', 'partial')
            or not isinstance(value.get('selection'), dict)
            or value['selection'].get('trace_id', True) is not None
            or not isinstance(value.get('failure_history'), dict)
            or not isinstance(value.get('cases'), list) or len(value['cases']) > 100):
        raise ValueError('Two full Core diagnostic case reports are required.')
    history = value['failure_history']
    if history.get('status') != 'ready':
        return None
    if history.get('scope') != 'core_process_memory':
        raise ValueError('Only full Core process observations can be compared.')
    if type(history.get('schema_version')) is not int or history['schema_version'] not in (1, 2):
        raise ValueError('Unsupported failure history format.')
    # An excerpt with all cases stripped must not be compared as zero
    # failures when the exported Core ring still accounts for retained rows.
    if 'buffer_bytes' in history and bool(_count(history['buffer_bytes'], 0)) != bool(value['cases']):
        raise ValueError('The retained cases do not match the reported buffer.')
    when = value.get('generated_at')
    try:
        at = datetime.fromisoformat(when) if isinstance(when, str) else None
    except ValueError:
        at = None
    if at is None or at.utcoffset() is None:
        raise ValueError('Missing or invalid collection time.')
    counts = Counter()
    times = []
    for case in value['cases']:
        row = case.get('evidence') if isinstance(case, dict) else None
        reason = row.get('reason') if isinstance(row, dict) else None
        stage = row.get('stage') if isinstance(row, dict) else None
        if (not isinstance(reason, str) or reason not in CASE_REASONS or reason == 'ok'
                or not isinstance(stage, str) or stage not in CASE_STAGES):
            raise ValueError('Invalid recorded failure type.')
        counts[stage, reason] += _count(row.get('occurrences'), 1)
        first, last = row.get('first_timestamp'), row.get('timestamp')
        if (type(first) in (int, float) and type(last) in (int, float)
                and 0 <= first <= last <= at.timestamp() and last < 253402300799):
            times.append((first, last))
    drops = history.get('dropped')
    if not isinstance(drops, dict) or set(drops) != set(_DROPS):
        raise ValueError('Missing or unsupported evidence loss counters.')
    # Do not invent a narrower interval when a single retained group lacks a clock.
    bounds = ((min(t[0] for t in times), max(t[1] for t in times))
              if times and len(times) == len(value['cases']) else None)
    return _History(at, history.get('process_id'), history.get('history_id'),
                    tuple(_count(drops[k], 0) for k in _DROPS), counts, bounds)


def _observed_times(history):
    if history is None or history.bounds is None:
        return None
    first, last = history.bounds
    def utc(stamp):
        return datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec='milliseconds')
    return dict(first_utc=utc(first), last_utc=utc(last), span_seconds=round(last-first, 3))


def _steps(counts):
    return [{'stage': stage, 'reason': why, 'occurrences': count}
            for (stage, why), count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def compare(before, after):
    first, last = _snapshot(before), _snapshot(after)
    reason = 'comparable'
    if first is None or last is None:
        reason = 'incomplete_history'
    elif first.at > last.at:
        reason = 'not_chronological'
    elif not (_id(first.process) and _id(last.process)):
        reason = 'process_unknown'
    elif first.process != last.process:
        reason = 'core_process_changed'
    elif not (_id(first.epoch) and _id(last.epoch)):
        reason = 'history_epoch_unknown'
    elif first.epoch != last.epoch:
        reason = 'history_cleared'
    elif first.dropped != last.dropped or any(last.counts[k] < n for k, n in first.counts.items()):
        reason = 'evidence_lost_or_expired'
    delta = (last.counts - first.counts) if reason == 'comparable' else None
    by_reason = Counter()
    for (_, why), count in (delta or {}).items():
        by_reason[why] += count
    return {'schema_version': 1, 'kind': 'core_failure_comparison', 'status': reason,
            'scope': 'recorded_core_http_failures_only',
            'before_retained': sum(first.counts.values()) if first is not None else None,
            'after_retained': sum(last.counts.values()) if last is not None else None,
            'before_retained_times': _observed_times(first), 'after_retained_times': _observed_times(last),
            'new_recorded_failures': sum(delta.values()) if delta is not None else None,
            'by_reason': dict(sorted(by_reason.items())) if delta is not None else None,
            'before_steps': _steps(first.counts) if first is not None else None,
            'after_steps': _steps(last.counts) if last is not None else None,
            'new_steps': _steps(delta) if delta is not None else None,
            'limitation': 'Counts in unsigned reports are observations, not proof of successful traffic or a repair.'}
