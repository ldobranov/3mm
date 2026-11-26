"""Read-only diagnostic cases: collect from Core, or explain a bounded export.

Uses only the standard library and the shared closed diagnostic vocabulary.
Never invokes an application, retries a request, changes rights or reads logs.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import warnings

from backend.system.diagnostics.catalog import CASE_REASONS, CASE_STAGES, DEVICE_STAGES, WORK_ID, checked_work_record, explain_case
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


class DiagnosticReadError(ValueError):
    """Only locally generated messages may be printed; never response bodies."""


def _private_token():
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            return getpass.getpass('Current administrator token (not saved): ')
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt, OSError):
        raise DiagnosticReadError('Private token input is unavailable. Use an interactive terminal; no request was made.') from None


def _endpoint(url):
    message = 'Use a bare HTTPS address or an explicit loopback HTTP endpoint (an SSH tunnel is suitable).'
    if (type(url) is not str or not 1 <= len(url) <= 2048 or not url.isascii()
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 or c in '@?#\\%' for c in url)):
        raise DiagnosticReadError(message)
    try:
        parsed = urllib.parse.urlsplit(url)
        host, port = parsed.hostname, parsed.port
        authority = ('[' + host + ']' if host and ':' in host else host or '') + (f':{port}' if port is not None else '')
        valid = (parsed.scheme in {'http', 'https'} and host and parsed.path in {'', '/'}
                 and parsed.netloc.lower() == authority and port != 0
                 and (parsed.scheme == 'https' or parsed.hostname in {'127.0.0.1', 'localhost', '::1'}))
    except ValueError:
        valid = False
    if not valid:
        raise DiagnosticReadError(message)
    return url.rstrip('/')


def _read(url, token, *, path):
    address = _endpoint(url)
    if not isinstance(token, str) or not token or len(token) > 8192 or any(c in token for c in '\r\n'):
        raise ValueError('A current administrator token is required.')
    request = urllib.request.Request(address + path,
                                    headers={'Authorization': 'Bearer ' + token}, method='GET')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            blob = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        status = error.code if type(error.code) is int and 100 <= error.code <= 599 else None
        detail = {401:'Current sign-in required.',403:'Current administrator access required.',
                  404:'No matching resource.',409:'The selected installation changed or cannot be identified.',
                  429:'Another observation is in progress.'}.get(status, '')
        raise DiagnosticReadError(f'Diagnostic read refused (HTTP {status or "unknown"}). {detail} No retry was performed.') from None
    except (OSError, urllib.error.URLError):
        raise DiagnosticReadError('No confirmed diagnostic response. No action or retry was performed.') from None
    return parse_bundle(blob)


def _case_path(trace_id):
    if trace_id is not None and (type(trace_id) is not str or not TRACE.fullmatch(trace_id)):
        raise DiagnosticReadError('Use an exact Core request identifier.')
    suffix = '' if trace_id is None else '?trace_id=' + trace_id
    return '/api/v1/diagnostics/cases' + suffix


def collect(url, token, *, trace_id=None):
    value = _read(url, token, path=_case_path(trace_id))
    selection = value.get('selection')
    if ('kind' in value or 'browser' in value or type(selection) is not dict
            or 'trace_id' not in selection or selection['trace_id'] != trace_id
            or selection.get('result') not in ('found', 'not_found_in_retained_evidence')):
        raise DiagnosticReadError('The response did not match the requested Core case collection. Nothing was saved.')
    explain(value)  # Also checks retained cases/records against the returned selection.
    return value


def _save_new(path, value):
    # Publish a complete file on the destination filesystem, without replacing
    # someone else's evidence if two operators selected the same name.
    blob = json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode() + b'\n'
    if len(blob) > MAX_BYTES:
        raise DiagnosticReadError('The exported case file exceeds the offline reader limit. Nothing was saved.')
    fd, name = tempfile.mkstemp(prefix='.case-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(blob)
        if os.name == 'nt':
            os.rename(temporary, path)  # Windows rename refuses an existing destination
            temporary = None
        else:
            os.link(temporary, path)  # link the completed 0600 file; no replace
    except OSError:
        raise DiagnosticReadError('Could not publish a complete new case file. Check the destination; no existing evidence was replaced.') from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _application_path(module_id, reference):
    # Bounded identifier only, never a caller-supplied URL/path or a search.
    if (type(module_id) is not str or len(module_id) > 255 or not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)+', module_id)
            or reference is not None and (type(reference) is not str or not WORK_ID.fullmatch(reference))):
        raise DiagnosticReadError('Use one exact module ID and optionally one original task or command reference.')
    return '/api/v1/application-extensions/' + module_id + '/support-snapshot' + ('' if reference is None else '?reference=' + reference)


def inspect_application(url, token, *, module_id, reference=None):
    value = _read(url, token, path=_application_path(module_id, reference))
    owner, work = value.get('application'), value.get('work')
    if (value.get('kind') != 'application_support' or type(owner) is not dict or owner.get('module_id') != module_id
            or 'browser' in value or (reference is None and 'work' in value)
            or reference is not None and (type(work) is not dict or work.get('reference') != reference)):
        raise DiagnosticReadError('The response did not match the requested application or original work. Nothing was saved.')
    result = explain(value)  # disclose only the offline reader's fixed vocabulary
    result['application']['module_id'] = module_id
    return result


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
    from tools.resource_observation import from_service
    sample = from_service(service, instance)
    return {'source': 'imported_app_snapshot', 'instance_id': instance, 'artifact_sha256': artifact,
            **({'resources': sample} if sample is not None else {}),
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
                    or elapsed > total or timing_trace is None or row.get('trace_id') != timing_trace):
                raise ValueError('Invalid device step observation.')
            if timing_trace == trace:
                result[-1].update(step_timing_scope='this_request', last_passed_stage=last,
                                  failed_step_ms=elapsed, duration_ms=total)
            else:
                members = row.get('trace_ids')
                if (type(members) is not list or not 1 <= len(members) <= 8
                        or any(type(member) is not str or not TRACE.fullmatch(member) for member in members)
                        or trace not in members or timing_trace not in members):
                    raise ValueError('Device step observation does not contain the selected request.')
                result[-1]['step_timing_scope'] = 'not_retained_for_this_request'
    summary = {'schema_version': 1, 'status': value['status'], 'cases': result,
            'browser_cases': explain_browser(value.get('browser')),
            'browser': 'separate_untrusted_observations_present' if 'browser' in value else 'not_collected',
            'limitation': 'No retained case is not proof of success or non-execution.'}
    if 'kind' not in value and 'selection' in value:
        selection, records = value['selection'], value.get('trace_records', [])
        if type(selection) is not dict or 'trace_id' not in selection or type(records) is not list:
            raise ValueError('Invalid Core case selection.')
        original = selection['trace_id']
        if (original is not None and (type(original) is not str or not TRACE.fullmatch(original)
                                      or any(row['case_id'] != original for row in result))
                or any(type(row) is not dict or type(row.get('trace_id')) is not str
                       or not TRACE.fullmatch(row['trace_id'])
                       or original is not None and row['trace_id'] != original for row in records)
                or selection.get('result') != ('found' if result or records else 'not_found_in_retained_evidence')):
            raise ValueError('The retained evidence does not match the Core case selection.')
        summary['selection'] = {'trace_id': original, 'result': selection['result'],
                                'failure_cases': len(result), 'detailed_records': len(records)}
    if value.get('kind') == 'application_support':
        summary['application'] = _application_observation(value)
        if 'work' in value:
            summary['work'] = checked_work_record(value['work'])
    return summary


def explain_saved_request(value, trace_id):
    """Select an exact request from an existing export, including older group members."""
    if (not isinstance(trace_id, str) or not TRACE.fullmatch(trace_id)
            or 'kind' in value or not isinstance(value.get('selection'), dict)):
        raise ValueError('Use a Core case export and an exact Core request identifier.')
    result = explain(value)
    original = result['selection']['trace_id']
    if original not in (None, trace_id):
        raise ValueError('This export was collected for a different request.')
    cases = []
    for case, safe in zip(value['cases'], result['cases'], strict=True):
        evidence = case['evidence']
        latest = evidence.get('trace_id')
        members = evidence.get('trace_ids', [latest])
        if (type(members) is not list or not 1 <= len(members) <= 8
                or any(type(item) is not str or not TRACE.fullmatch(item) for item in members)
                or len(set(members)) != len(members) or members[0] != latest
                or safe['timing_trace_id'] != latest or safe['case_id'] != (original or latest)):
            raise ValueError('Invalid retained Core request identities.')
        if trace_id not in members:
            continue
        safe['case_id'] = trace_id
        if trace_id != latest and 'step_timing_scope' in safe:
            safe['step_timing_scope'] = 'not_retained_for_this_request'
            for key in ('failed_step_ms', 'duration_ms', 'last_passed_stage'):
                safe.pop(key, None)
        cases.append(safe)
    detailed = sum(row['trace_id'] == trace_id for row in value.get('trace_records', []))
    result.update(cases=cases, browser_cases=[row for row in result['browser_cases'] if row['trace_id'] == trace_id],
                  selection_source='saved_report', selection={
                      'trace_id': trace_id, 'result': 'found' if cases or detailed else 'not_found_in_retained_evidence',
                      'failure_cases': len(cases), 'detailed_records': detailed})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    reader = commands.add_parser('collect', help='One authenticated read; credentials are not saved')
    reader.add_argument('--url', required=True)
    reader.add_argument('--trace-id')
    reader.add_argument('--output', type=Path, required=True)
    app = commands.add_parser('application', help='Explain one current application support snapshot without saving it')
    app.add_argument('--url', required=True)
    app.add_argument('--module-id', required=True)
    app.add_argument('--reference', help='Optional exact task or device command reference; never invokes the work')
    app.add_argument('--json', action='store_true')
    viewer = commands.add_parser('explain', help='Read an exported bundle; no network or application execution')
    viewer.add_argument('file', type=Path)
    viewer.add_argument('--json', action='store_true')
    viewer.add_argument('--trace-id', help='Find an exact retained Core request in the saved file (no network)')
    comparison = commands.add_parser('compare', help='Compare two saved full Core histories; no network access')
    comparison.add_argument('before', type=Path)
    comparison.add_argument('after', type=Path)
    comparison.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.action == 'compare':
            from tools.diagnostic_comparison import compare
            result = compare(*(parse_bundle(read_regular(path, MAX_BYTES)) for path in (args.before, args.after)))
            if args.json:
                print(json.dumps(result))
            else:
                print('Comparison: ' + result['status'])
                print('Retained in the two snapshots (not a delta):',
                      result['before_retained'], '/', result['after_retained'])
                for label, times in (('Before', result['before_retained_times']), ('After', result['after_retained_times'])):
                    if times is not None:
                        print(f"  {label} retained failures: {times['first_utc']} to {times['last_utc']} UTC "
                              f"({times['span_seconds']} s apart; not service downtime)")
                if result['new_steps'] is not None:
                    print('New recorded failures:', result['new_recorded_failures'])
                    groups = [('New', result['new_steps'])]
                else:
                    groups = [('Before (retained)', result['before_steps']), ('After (retained)', result['after_steps'])]
                for label, rows in groups:
                    for row in rows or ():
                        print(f"  {label}: {row['stage']} / {row['reason']}: {row['occurrences']}")
                print(result['limitation'])
            return 0
        if args.action in {'collect', 'application'}:
            _endpoint(args.url)  # reject destination mistakes before requesting a credential
        if args.action == 'collect':
            _case_path(args.trace_id)
            if args.output.exists():
                raise ValueError('Output exists; evidence will not be overwritten.')
            value = collect(args.url, _private_token(), trace_id=args.trace_id)
            _save_new(args.output,value)
            print('Saved read-only diagnostic evidence. No services, permissions or applications changed.')
        else:
            if args.action == 'application':
                _application_path(args.module_id, args.reference)  # refuse malformed targets before prompting
                result = inspect_application(args.url, _private_token(), module_id=args.module_id, reference=args.reference)
            else:
                value = parse_bundle(read_regular(args.file, MAX_BYTES))
                result = explain(value) if args.trace_id is None else explain_saved_request(value, args.trace_id)
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
                if 'application_access_followup' in result:
                    from tools.recovery_result import ACCESS_FOLLOWUP
                    print(ACCESS_FOLLOWUP[result['application_access_followup']])
                if 'interface_builds' in result:
                    from tools.recovery_result import INTERFACE_FOLLOWUP
                    print(INTERFACE_FOLLOWUP[result['interface_builds']])
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
                if 'selection' in result:
                    selected = result['selection']
                    print(f"Core evidence ({selected['trace_id'] or 'all retained requests'}): "
                          f"{selected['failure_cases']} failure cases; {selected['detailed_records']} detailed records.")
                if 'application' in result:
                    observation = result['application']
                    print(f"Application instance: {observation['instance_id']} | Package: {observation['artifact_sha256']}")
                    print('Service: ' + str(observation['service_state'] or 'not observed') +
                          ' | Last result: ' + str(observation['last_service_result'] or 'not observed') +
                          ' | History: ' + observation['failure_history'])
                    if 'resources' in observation:
                        from tools.resource_observation import lines
                        for line in lines(observation['resources']):
                            print(line)
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
                        print(f"This request: {case['failed_step_ms']} ms in failing step / {case['duration_ms']} ms total. "
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
    except DiagnosticReadError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (ValueError, OSError, TypeError, KeyError, RecursionError):
        print('Diagnostic command stopped: invalid, unavailable or oversized evidence. No action was repeated.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
