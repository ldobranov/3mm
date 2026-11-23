"""Read-only diagnostic cases: collect from Core, or explain a bounded export.

Uses only the standard library and the shared closed diagnostic vocabulary.
Never invokes an application, retries a request, changes rights or reads logs.
"""
import argparse
import getpass
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from backend.system.diagnostics.catalog import CASE_REASONS, CASE_STAGES, DEVICE_STAGES, checked_work_record, explain_case
from backend.storage.observation_format import checked_sample
from packages.protocol.diagnostic_snapshot import decode, read_regular

MAX_BYTES = 4 * 1024 * 1024
TRACE = re.compile(r'(?:invoke|platform)_[0-9a-f]{32}\Z')
BROWSER_ID = re.compile(r'browser_[0-9a-f]{32}\Z')
# Browser-local observations have a separate vocabulary and are never Core receipts.
BROWSER_STAGES = frozenset('''host.context host.binding host.request host.response host.features host.operations host.identity
    session.ui session.targets.request session.targets.response session.resolve session.request session.ticket.request
    session.ticket.response session.socket session.opening session.stream'''.split())
BROWSER_CAUSES = frozenset('''host_context_missing host_binding_invalid host_response_mismatch host_features_invalid
    host_operations_invalid host_identity_changed ui_build_missing targets_response_invalid target_schema_invalid
    target_binding_duplicate targets_empty target_not_found target_ambiguous session_request_invalid session_request_mismatch
    session_recovery_required ticket_response_invalid socket_backend_unset socket_audience_denied socket_url_invalid
    socket_construction_failed session_protocol_invalid session_callback_failed session_outcome_unconfirmed'''.split())


def explain_browser(browser):
    if browser is None:
        return []
    if (type(browser) is not dict or browser.get('source') != 'browser_observation'
            or type(browser.get('records')) is not list or len(browser['records']) > 100):
        raise ValueError('Invalid browser observations.')
    result = []
    for row in browser['records']:
        if type(row) is not dict:
            raise ValueError('Invalid browser observation.')
        identifier, trace = row.get('case_id'), row.get('trace_id')
        stage, cause, last = row.get('stage'), row.get('cause'), row.get('last_passed_stage')
        status, count = row.get('status'), row.get('occurrences')
        if (row.get('source') != 'browser_observation'
                or type(identifier) is not str or not BROWSER_ID.fullmatch(identifier)
                or trace is not None and (type(trace) is not str or not TRACE.fullmatch(trace))
                or stage is not None and (type(stage) is not str or stage not in BROWSER_STAGES)
                or last is not None and (type(last) is not str or last not in BROWSER_STAGES)
                or cause is not None and (type(cause) is not str or cause not in BROWSER_CAUSES)
                or status is not None and (type(status) is not int or not 400 <= status <= 599)
                or type(count) is not int or not 1 <= count <= 9007199254740991):
            raise ValueError('Invalid browser observation labels.')
        result.append({'case_id': identifier, 'source': 'browser_observation', 'stage': stage, 'cause': cause,
            'last_passed_stage': last, 'trace_id': trace, 'status': status, 'occurrences': count,
            'response_observed': row.get('response_observed') is True or status is not None,
            'execution': 'unknown', 'automatic_replay_allowed': False,
            'next_check_help': 'Inspect the failed browser check and its original Core reference, if present. Do not replay.'})
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def collect(url, token, *, trace_id=None):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {'', '/'}
            or parsed.scheme == 'http' and parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}):
        raise ValueError('Use HTTPS or an explicit loopback HTTP endpoint (an SSH tunnel is suitable).')
    if not isinstance(token, str) or not token or len(token) > 8192 or any(c in token for c in '\r\n'):
        raise ValueError('A current administrator token is required.')
    if trace_id is not None and (type(trace_id) is not str or not TRACE.fullmatch(trace_id)):
        raise ValueError('Use an exact Core request identifier.')
    suffix = '' if trace_id is None else '?trace_id=' + trace_id
    request = urllib.request.Request(url.rstrip('/') + '/api/v1/diagnostics/cases' + suffix,
                                    headers={'Authorization': 'Bearer ' + token}, method='GET')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            blob = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise ValueError(f'Diagnostic read refused (HTTP {error.code}); no retry was performed.') from None
    except (OSError, urllib.error.URLError):
        raise ValueError('No confirmed diagnostic response. No action or retry was performed.') from None
    value = parse_bundle(blob)
    return value


def parse_bundle(blob):
    if type(blob) is not bytes or not 1 <= len(blob) <= MAX_BYTES:
        raise ValueError('Diagnostic bundle exceeds its bounded size.')
    value = decode(blob)
    if isinstance(value, dict) and value.get('kind') == 'backup_inventory_check':
        from backend.system.backups.evidence import checked_inventory
        return checked_inventory(value)
    if isinstance(value, dict) and value.get('kind') == 'portable_recovery_check':
        from tools.recovery_result import checked_result
        return checked_result(value)
    if isinstance(value, dict) and value.get('kind') == 'peer_report_observation':
        from backend.installation.report_receipts import checked_observation
        return checked_observation(value)
    if isinstance(value, dict) and value.get('kind') == 'sqlite_write_sample':
        return checked_sample(value)
    if (type(value) is not dict or type(value.get('schema_version')) is not int or value.get('schema_version') != 1
            or value.get('status') not in {'ready', 'partial'}
            or type(value.get('cases')) is not list or len(value['cases']) > 100):
        raise ValueError('Unsupported diagnostic case bundle.')
    return value


def _application_observation(value):
    """An imported support file is untrusted. Rebuild only allowlisted observations."""
    from deployment.service_resources import SERVICE_RESULTS
    owner, service, coverage = (value.get(key) for key in ('application', 'service', 'coverage'))
    if not all(type(item) is dict for item in (owner, service, coverage)):
        raise ValueError('Missing application observation.')
    instance, artifact, revision = (owner.get(k) for k in ('instance_id', 'artifact_sha256', 'observation_revision'))
    status = service.get('state')
    history = coverage.get('failure_history')
    if (not all(type(s) is str and re.fullmatch(r'[0-9a-f]{' + str(n) + '}', s)
                for s, n in ((instance, 24), (artifact, 64), (revision, 64)))
            or type(status) is not str or status not in {'observed', 'not_running', 'not_found', 'unsupported', 'unavailable'}
            or type(history) is not str or history not in {'ready','busy','unavailable'}
            or any(case['evidence'].get('instance_id') != instance or
                   case['evidence'].get('application_revision') != revision for case in value['cases'])):
        raise ValueError('Invalid or mixed application observation.')
    manager = service.get('supervision', {})
    if type(manager) is not dict:
        raise ValueError('Invalid service supervision.')
    state, result, restarts = (manager.get(k) for k in ('state', 'result', 'restart_count'))
    if (state is not None and (type(state) is not str or state not in {'active', 'stopped', 'failed', 'starting', 'stopping', 'restarting', 'unknown'})
            or result is not None and (type(result) is not str or result not in SERVICE_RESULTS | {'other'})
            or restarts is not None and (type(restarts) is not int or not 0 <= restarts < 2**32)):
        raise ValueError('Invalid service supervision labels.')
    return {'source': 'imported_app_snapshot', 'instance_id': instance, 'artifact_sha256': artifact,
            'observation_revision': revision, 'resource_observation': status, 'service_state': state,
            'last_service_result': result, 'automatic_restarts': restarts, 'failure_history': history}


def explain(value):
    """Do not print untrusted descriptions/paths from a supplied export."""
    if value.get('kind') == 'backup_inventory_check':
        from backend.system.backups.evidence import NOTICES, checked_inventory
        result = checked_inventory(value)
        result['issues'] = [{**row,'meaning':NOTICES[row['code']]} for row in result['issues']]
        return {**result,'limitation':'Imported capture check only. No existing archive, restore or service activation was verified.'}
    if value.get('kind') == 'portable_recovery_check':
        from tools.recovery_result import checked_result
        return {**checked_result(value),'limitation':
            'Imported offline observation, not a signed attestation. No device boot, application activation or live restore was tested.'}
    if value.get('kind') == 'peer_report_observation':
        from backend.installation.report_receipts import checked_observation
        return {**checked_observation(value), 'limitation':
                'Only the latest matching local outbound slot is observed. Missing is not proof of non-delivery. No report was sent.'}
    if value.get('kind') == 'sqlite_write_sample':
        return {**checked_sample(value), 'limitation':
                'Only newly opened Core connections were sampled. A duration or an empty sample cannot identify the writer of an earlier failure.'}
    result = []
    for case in value['cases']:
        if type(case) is not dict or type(case.get('evidence')) is not dict:
            raise ValueError('Invalid case evidence.')
        row = case['evidence']
        trace, reason, stage, phase = case.get('case_id'), row.get('reason'), row.get('stage'), row.get('phase')
        timing_trace = case.get('timing_trace_id', row.get('trace_id'))
        status, handled = row.get('status'), row.get('handled_refusal', False)
        if (type(trace) is not str or not TRACE.fullmatch(trace) or type(reason) is not str
                or timing_trace is not None and (type(timing_trace) is not str or not TRACE.fullmatch(timing_trace))
                or reason not in CASE_REASONS or reason == 'ok'
                or type(stage) is not str or stage not in CASE_STAGES
                or phase not in {'unknown', 'not_dispatched', 'execution_unconfirmed', 'completed'}
                or type(handled) is not bool
                or status is not None and (type(status) is not int or not 100 <= status <= 599)
                or handled and (status != 200 or phase != 'not_dispatched' or row.get('method') != 'GET')):
            raise ValueError('Invalid case labels.')
        result.append({'case_id': trace, 'timing_trace_id': timing_trace, 'stage': stage, 'reason': reason, 'execution': phase,
                       'http_status': status, 'handled_refusal': handled,
                       **explain_case(stage, reason), 'automatic_replay_allowed': False})
        if 'failed_step_ms' in row:
            last, elapsed, total = row.get('last_passed_stage'), row['failed_step_ms'], row.get('duration_ms')
            if (stage not in DEVICE_STAGES or last is not None and (type(last) is not str or last not in DEVICE_STAGES)
                    or any(type(n) not in (int, float) or not 0 <= n <= 86400000 for n in (elapsed, total))
                    or elapsed > total or timing_trace is None):
                raise ValueError('Invalid device step observation.')
            result[-1].update(last_passed_stage=last, failed_step_ms=elapsed, duration_ms=total)
    summary = {'schema_version': 1, 'status': value['status'], 'cases': result,
            'browser_cases': explain_browser(value.get('browser')),
            'browser': 'separate_untrusted_observations_present' if 'browser' in value else 'not_collected',
            'limitation': 'No retained case is not proof of success or non-execution.'}
    if value.get('kind') == 'application_support':
        summary['application'] = _application_observation(value)
        if 'work' in value:
            summary['work'] = checked_work_record(value['work'])
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    reader = commands.add_parser('collect', help='One authenticated read; credentials are not saved')
    reader.add_argument('--url', required=True)
    reader.add_argument('--trace-id')
    reader.add_argument('--output', type=Path, required=True)
    viewer = commands.add_parser('explain', help='Read an exported bundle; no network or application execution')
    viewer.add_argument('file', type=Path)
    viewer.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.action == 'collect':
            if args.output.exists():
                raise ValueError('Output exists; evidence will not be overwritten.')
            value = collect(args.url, getpass.getpass('Current administrator token: '), trace_id=args.trace_id)
            with args.output.open('xb') as stream:
                stream.write(json.dumps(value, ensure_ascii=True, allow_nan=False).encode() + b'\n')
            print('Saved read-only diagnostic evidence. No services, permissions or applications changed.')
        else:
            result = explain(parse_bundle(read_regular(args.file, MAX_BYTES)))
            if args.json:
                print(json.dumps(result, ensure_ascii=True))
            elif result.get('kind') == 'backup_inventory_check':
                print('Capture check: ' + ('ready' if result['ready_to_capture'] else 'not ready') +
                      ' | Inventory: ' + result['inventory'])
                for row in result['issues']:
                    print(f"{row['severity']} ({row['occurrences']}): {row['meaning']}")
                print(result['limitation'])
            elif result.get('kind') == 'portable_recovery_check':
                print('Portable archive: '+result['state']+' | Target: '+str(result['target_architecture'] or 'not verified'))
                if 'next_check' in result: print(result['next_check'])
                print(result['limitation'])
            elif result.get('kind') == 'peer_report_observation':
                print(f"Peer report: {result['report_id']} | {result['state']}")
                print(result['limitation'])
            elif result.get('kind') == 'sqlite_write_sample':
                print(f"Core database write sample: {result['window_ms']} ms; limited: {result['limited']}")
                for row in result['families']:
                    print(f"{row['source']}: {row['observed']} observed; longest {row['longest_ms']} ms; still open {row['open_at_end']}")
                print(result['limitation'])
            else:
                print('Diagnostic cases: ' + result['status'])
                if 'application' in result:
                    observation = result['application']
                    print(f"Application instance: {observation['instance_id']} | Package: {observation['artifact_sha256']}")
                    print('Service: ' + str(observation['service_state'] or 'not observed') +
                          ' | Last result: ' + str(observation['last_service_result'] or 'not observed') +
                          ' | History: ' + observation['failure_history'])
                if 'work' in result:
                    work = result['work']
                    print(f"Core record: {work['reference']} | {work.get('recorded_state', work['status'])}")
                    if work.get('linked_task'):
                        print('Linked task: ' + work['linked_task'])
                    if work.get('device_event_recorded'):
                        print('Core also retained a correlated device event. No physical action was replayed.')
                    if 'start_boundary' in work:
                        print('Core task journal: ' + work['start_boundary'] +
                              '. A consumed start permit does not prove the task finished.')
                    if 'delivery' in work:
                        delivery = work['delivery']
                        seconds = delivery['queue_to_latest_offer_seconds']
                        print(f"Core delivery offers: {delivery['recorded_attempts']}. "
                              + (f"Queued to latest offer: about {seconds} s." if seconds is not None
                                 else "Queued to latest offer: not measured.")
                              + " This is not device or physical execution time.")
                        if 'permit_claimed' in delivery:
                            print('Core recorded a one-use execution permit claim. Physical execution is not confirmed by this record.'
                                  if delivery['permit_claimed'] else 'No one-use execution permit claim is recorded for this command.')
                for case in result['cases']:
                    print(f"{case['case_id']} | {case['stage']} | {case['reason']}")
                    print(case['summary'])
                    if case['timing_trace_id'] is not None and case['timing_trace_id'] != case['case_id']:
                        print('The group timestamp and duration belong to its latest request, not this request.')
                    if 'failed_step_ms' in case:
                        print(f"Latest request: {case['failed_step_ms']} ms in failing step / {case['duration_ms']} ms total. "
                              f"Last passed: {case['last_passed_stage'] or 'not observed'}.")
                    if case['handled_refusal']:
                        print('HTTP200 returned a discovery response; a resource check was refused, not a successful session opening.')
                    print('Next check: ' + case['next_check_help'])
                    print('Execution: ' + case['execution'] + '; automatic replay is not permitted.')
                for case in result['browser_cases']:
                    print(f"Browser observation (untrusted): {case['case_id']} | {case['stage']} | {case['cause']}")
                    print(f"Last passed check: {case['last_passed_stage']}; Core reference: {case['trace_id']}")
                    print(case['next_check_help'])
                print(result['limitation'])
    except (ValueError, OSError, TypeError, KeyError, RecursionError):
        print('Diagnostic command stopped: invalid, unavailable or oversized evidence. No action was repeated.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
