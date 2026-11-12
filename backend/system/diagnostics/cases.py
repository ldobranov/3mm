"""One bounded, read-only view over the existing recorder and failure ring."""
from datetime import UTC, datetime

from packages.protocol.diagnostic_cases import CATALOG_VERSION, explain_failure, operation_for_route


def build_cases(failures, recording, observations, *, trace_id=None):
    records = recording.get('records', [])
    rows = failures.get('records', [])
    if trace_id:
        rows = [row for row in rows if trace_id in row.get('trace_ids', [row['trace_id']])]
        records = [row for row in records if row['trace_id'] == trace_id]
    cases = []
    for row in rows:
        traces = row.get('trace_ids', [row['trace_id']])
        cases.append({
            'case_id': row['trace_id'], 'source': 'core_observation',
            'operation': operation_for_route(row['route']),
            **explain_failure(row['reason']),
            'evidence': row,
            'trace_records': [record for record in records if record['trace_id'] in traces],
            'execution': row['phase'], 'automatic_replay_allowed': False,
        })
    detailed_status = 'available' if records else 'no_matching_records'
    gaps = [
        'History is bounded and is cleared by a Core process restart.',
        'No matching record is not proof that an operation succeeded or never executed.',
        'Component health is an observation, not application or hardware execution proof.',
        'Remote producer traces and application-owned internals are not automatically collected.',
        'No request bodies, credentials, terminal text or arbitrary exception messages are collected.',
    ]
    complete = (failures.get('status') == 'ready' and recording.get('status') != 'busy'
                and observations.get('probe_status') == 'complete')
    return {
        'schema_version': 1, 'catalog_version': CATALOG_VERSION,
        'generated_at': datetime.now(UTC).isoformat(),
        'status': 'ready' if complete else 'partial',
        'selection': {'trace_id': trace_id,
                      'result': 'found' if cases or records else 'not_found_in_retained_evidence'},
        'failure_history': {key: value for key, value in failures.items() if key != 'records'},
        'recording': {key: value for key, value in recording.items() if key != 'records'},
        'observations': observations, 'cases': cases,
        'trace_records': records,
        'coverage': [
            {'boundary': 'core.http', 'status': failures.get('status', 'unavailable'),
             'scope': 'router_templates_http_4xx_5xx_and_explicit_handled_read_refusals'},
            {'boundary': 'core.sessions', 'status': 'instrumented',
             'scope': 'targets_ticket_websocket_failures'},
            {'boundary': 'core.detailed_traces', 'status': detailed_status},
            {'boundary': 'browser', 'status': 'not_collected', 'trust': 'client_observation_only'},
            {'boundary': 'remote_producers', 'status': 'not_collected'},
        ],
        'limitations': gaps,
        'actions_performed': {'application_invoked': False, 'services_changed': False,
                              'rights_changed': False, 'automatic_retry': False},
    }
