"""Metadata vocabulary for Core cases and their offline reader. No I/O or service dependencies."""
import re
from packages.protocol.diagnostic_cases import explain_failure as _explain, operation_for_route
from packages.protocol.diagnostics import HOST_FAILURE_STAGES, REASONS, STAGES

# This is the support-export catalog, not a new app SDK or host wire version.
CATALOG_VERSION = 3
LOGIN_STAGES = frozenset({'login.account_read', 'login.session_policy', 'login.session_write', 'login.audit_write'})
DEVICE_STAGES = frozenset({'device.credential_header', 'device.credential', 'device.credential_write', 'device.identity_match',
                           'device.authority_snapshot', 'device.execution_permit', 'device.notification_wait', 'device.authority_sign',
                           'device.authority_commit', 'device.heartbeat_write'})
_DEVICE = {
    'device_credential_refused': ('Core did not accept the Agent credential.', 'Inspect the current device enrollment and revocation state; do not change application grants.'),
    'device_identity_mismatch': ('The request did not match the authenticated device.', 'Compare the selected device with its enrollment.'),
    'device_access_denied': ('The authenticated device operation was refused.', 'Inspect the current device authority without granting access or resending.'),
    'installation_identity_unavailable': ('Core could not use its installation identity.', 'Inspect installation identity availability and Core readiness. This is not an application permission denial.'),
    'device_step_unknown': ('Core observed the failing device step but not a supported cause.', 'Inspect this step and the original request time. Duration alone does not identify the cause.'),
}
_STORAGE = {
    'database_busy': 'SQLite reported a busy or locked database.',
    'database_read_only': 'SQLite refused a write because the database was read-only.',
    'database_full': 'SQLite reported that storage was full.',
    'database_cannot_open': 'SQLite could not open the database.',
    'database_io_error': 'SQLite reported a storage I/O error.',
    'database_operation_failed': 'The database operation failed without a more specific supported code.',
    'database_constraint': 'SQLite refused a change because a data constraint was not satisfied.',
}
CASE_STAGES = frozenset(STAGES) | LOGIN_STAGES | DEVICE_STAGES | {'http.response', 'core.database'}
CASE_REASONS = frozenset(REASONS) | _STORAGE.keys() | _DEVICE.keys() | {'unclassified_conflict', 'server_error', 'client_refused'}
WORK_ID = re.compile(r'(task|cmd)_[0-9a-f]{32}\Z')
WORK_STATES = {
    'task': frozenset({'queued', 'running', 'succeeded', 'failed', 'expired', 'cancelled', 'unknown', 'resolved'}),
    'cmd': frozenset({'queued', 'delivered', 'succeeded', 'failed', 'expired'}),
}
TASK_BOUNDARIES = ('no_dispatch_record', 'dispatch_recorded', 'start_permit_consumed', 'inconsistent')
MAX_CLOCK_SECONDS = 366 * 24 * 3600


def checked_work_record(record):
    """Project even an offline, untrusted record onto the public diagnostic vocabulary."""
    if not isinstance(record, dict):
        raise ValueError('Invalid work observation')
    ref = record.get('reference')
    match = WORK_ID.fullmatch(ref) if type(ref) is str else None
    status = record.get('status')
    if match is None or type(status) is not str or status not in {'found', 'not_found_in_scope', 'unavailable'}:
        raise ValueError('Invalid work observation')
    result = {'reference': ref, 'status': status}
    if status != 'found':
        return result
    kind, state = match[1], record.get('recorded_state')
    if type(state) is not str or state not in WORK_STATES[kind]:
        raise ValueError('Invalid work state')
    result['recorded_state'] = state
    if kind == 'task':
        progress = record.get('progress')
        if type(progress) is not int or not 0 <= progress <= 100:
            raise ValueError('Invalid work progress')
        result['progress'] = progress
        if 'start_boundary' in record:
            boundary = record['start_boundary']
            if boundary not in TASK_BOUNDARIES:
                raise ValueError('Invalid task boundary')
            result['start_boundary'] = boundary
    else:
        task, event = record.get('linked_task'), record.get('device_event_recorded')
        if task is not None and (type(task) is not str or not re.fullmatch(r'task_[0-9a-f]{32}', task)):
            raise ValueError('Invalid linked task')
        if type(event) is not bool:
            raise ValueError('Invalid event observation')
        result.update(linked_task=task, device_event_recorded=event)
        if 'delivery' in record:
            delivery = record['delivery']
            if type(delivery) is not dict or 'queue_to_latest_offer_seconds' not in delivery:
                raise ValueError('Invalid delivery observation')
            attempts, seconds = delivery.get('recorded_attempts'), delivery.get('queue_to_latest_offer_seconds')
            if type(attempts) is not int or not 0 <= attempts <= 2**31-1 or (
                    seconds is not None and (type(seconds) is not int or not 0 <= seconds <= MAX_CLOCK_SECONDS or not attempts)):
                raise ValueError('Invalid delivery observation')
            result['delivery'] = {'recorded_attempts': attempts, 'queue_to_latest_offer_seconds': seconds}
            if 'permit_claimed' in delivery:
                if type(delivery['permit_claimed']) is not bool:
                    raise ValueError('Invalid command permit observation')
                result['delivery']['permit_claimed'] = delivery['permit_claimed']
    return result


def case_operation(route, stage):
    if route == '/api/v1/devices/{device_id}/authority-exchange':
        return 'device.authority_exchange'
    if route == '/api/v1/devices/{device_id}/heartbeat':
        return 'device.heartbeat'
    if stage in LOGIN_STAGES or route == '/api/user/login':
        return 'account.login'
    if isinstance(route, str) and any(route.endswith('/{module_id}/' + audience + 'operations/{operation_id}')
                                      for audience in ('', 'operator/', 'kiosk/', 'public/')):
        return 'application.invoke'
    session = operation_for_route(route)
    if session:
        return session
    if stage == 'application.ui_discovery':
        return 'application.ui.discover'
    if (stage in HOST_FAILURE_STAGES or stage in {'application.admission', 'application.dispatch',
            'application.response', 'application.completion'} or STAGES.get(stage) == 'application.completion'):
        return 'application.invoke'
    return None


def explain_case(stage, reason):
    if stage == 'core.database' and reason in _STORAGE:
        return {'summary': _STORAGE[reason], 'next_check': 'inspect_core_storage',
                'next_check_help': 'Inspect Core storage at the recorded time. The inner step and writer were not identified.'}
    if reason in _DEVICE:
        summary, help_text = _DEVICE[reason]
        return {'summary': summary, 'next_check': 'inspect_' + reason, 'next_check_help': help_text}
    if stage in DEVICE_STAGES and reason in _STORAGE:
        return {'summary': _STORAGE[reason], 'next_check': 'inspect_device_storage',
                'next_check_help': 'Review the device step and storage status. A later writer sample cannot identify a past lock owner.'}
    if stage in LOGIN_STAGES and reason in _STORAGE:
        return {'summary': _STORAGE[reason], 'next_check': 'inspect_login_storage',
                'next_check_help': ('Review this login stage; if busy errors recur, measure current writers in operation diagnostics. '
                                    'The measurement cannot identify a past lock owner. Do not automatically retry.'
                                    if reason == 'database_busy' else
                                    'Check the recorded login stage, storage space and service logs for the same time. Do not replay the request automatically.')}
    return _explain(reason)
