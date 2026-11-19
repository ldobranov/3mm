"""One bounded, read-only view over the existing recorder and failure ring."""
from datetime import UTC, datetime

from backend.system.diagnostics.catalog import CATALOG_VERSION, case_operation, explain_case


def _case_rows(rows, records, trace_id=None):
    cases = []
    for row in rows:
        traces = row.get('trace_ids', [row['trace_id']])
        cases.append({
            'case_id': trace_id or row['trace_id'], 'source': 'core_observation',
            # For an older member we retain the common refusal and reference,
            # not its own timestamp or latency. Never attribute newer timings to it.
            'timing_trace_id': row['trace_id'],
            'operation': case_operation(row['route'], row['stage']),
            **explain_case(row['stage'], row['reason']),
            'evidence': row,
            'trace_records': [record for record in records if record['trace_id'] in traces],
            'execution': row['phase'], 'automatic_replay_allowed': False,
        })
    return cases


def application_support_snapshot(installation, service, failures):
    """Same offline case format, with deliberately narrower coverage. No probes here."""
    from backend.system.diagnostics.failures import observation_revision
    revision = observation_revision(installation.instance_id, installation.authority_incarnation, installation.sha256)
    if not revision:
        raise ValueError('Installation binding is unavailable')
    history = failures.application_snapshot(installation.instance_id, installation.authority_incarnation, installation.sha256)
    return {
        'schema_version': 1, 'catalog_version': CATALOG_VERSION, 'kind': 'application_support',
        'generated_at': datetime.now(UTC).isoformat(),
        'status': 'ready' if history['status'] == 'ready' and service['state'] in {'observed', 'not_running', 'not_found'} else 'partial',
        'application': {'module_id': installation.module_id, 'package_version': installation.package_version,
                        'artifact_sha256': installation.sha256, 'instance_id': installation.instance_id,
                        'observation_revision': revision},
        'service': service, 'cases': _case_rows(history['records'], ()),
        'coverage': {'failure_history': history['status'], 'retention_seconds': history.get('retention_seconds'),
                     'scope': 'verified_http_admission_to_this_installation_generation_and_package',
                     'application_logs': 'not_collected', 'browser': 'not_collected', 'detailed_recording': 'not_collected'},
        'limitations': ['No matching case is not proof of health or non-execution.',
                        'Failures before identifying the package, other generations and unbound WebSocket failures are excluded.',
                        'History is bounded, may drop observations and is cleared by a Core restart.'],
        'automatic_replay_allowed': False,
    }


def build_cases(failures, recording, observations, *, trace_id=None):
    records = recording.get('records', [])
    rows = failures.get('records', [])
    if trace_id:
        rows = [row for row in rows if trace_id in row.get('trace_ids', [row['trace_id']])]
        records = [row for row in records if row['trace_id'] == trace_id]
    cases = _case_rows(rows, records, trace_id)
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
