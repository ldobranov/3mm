"""Current Core operation admission and completion around a response-only Runtime wait."""
from backend.services.operation_diagnostics import core_diagnostics, authority_diagnostic_scope, authority_failure_span
from backend.services.http_failures import current_trace_id, note_failure, note_dispatch
from three_mm_protocol.diagnostics import DiagnosticSpan, validated_host_failure
from dataclasses import dataclass, replace
from contextlib import contextmanager
import json
import socket
import time
import uuid

from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from fastapi import HTTPException
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services.application_extensions import (
    ApplicationGatewayError, prepare_application_invocation, complete_application_preparation, validate_operation_payload,
)
from backend.services.application_response_relay import (
    ResponseWaiter, ApplicationResponseError, ApplicationResponseBinding, application_snapshot, application_fence,
)
from three_mm_platform_wire import remaining
from three_mm_runtime.application_transport import sign_message, send_message, verify_message, ApplicationTransportError, DispatchPhase


@dataclass(frozen=True)
class InvocationSpec:
    installation: object
    package: object
    operation_id: str
    payload: dict
    context: dict
    audience: str
    expected_peer: tuple[int, int, str] | None = None


def _failure_reason(error, stage):
    """Fixed metadata only. Never inspect exception messages or app payloads."""
    from backend.services.application_authority_keys import AuthorityReviewKeyError
    from backend.services.application_authority_management import AuthorityManagementError
    if isinstance(error, ApplicationResponseError):
        return error.reason
    if isinstance(error, ApplicationGatewayError):
        return error.diagnostic_reason
    if isinstance(error, HTTPException):
        return ('authentication_failed' if error.status_code == 401 else
            'operation_denied' if error.status_code == 403 else 'authority_unavailable')
    if isinstance(error, (AuthorityReviewKeyError, AuthorityManagementError, SQLAlchemyError)):
        return 'authority_unavailable'
    if isinstance(error, TimeoutError):
        return 'deadline_exceeded'
    if isinstance(error, OSError):
        return 'transport_unavailable'
    if isinstance(error, ApplicationTransportError):
        return 'response_invalid'
    if isinstance(error, (ValueError, TypeError, KeyError)):
        return 'authority_unavailable' if stage in {'application.admission', 'application.completion'} else 'response_invalid'
    return 'operation_failed'


def _end_failure(span, error, stage):
    reason = _failure_reason(error, stage)
    note_failure(stage, reason)
    span.end('denied' if reason in {'authentication_failed', 'operation_denied', 'authority_unavailable'} else 'error', reason)


def _record_host_failure(verified, binding):
    """Only call after signature/request validation, for a negative response.

    Keep the existing unconfirmed error and phase even if this observation is
    malformed or recording fails. No raw host error text reaches either export.
    """
    try:
        detail = validated_host_failure(verified.get('failure'))
        if detail is None:
            return
        note_failure(detail['stage'], detail['reason'])
        core_diagnostics.record(trace_id=current_trace_id('invoke_' + binding.request_id),
            stage=detail['stage'], reason=detail['reason'], duration_ms=detail['duration_ms'],
            operation='application.invoke', instance_id=binding.snapshot[0], result='error')
    except Exception:
        pass  # Observability must not replace the original application refusal.


@contextmanager
def _invocation_span(identifier, stage, instance_id=None):
    span = DiagnosticSpan(core_diagnostics, current_trace_id('invoke_' + identifier), stage,
        operation='application.invoke', instance_id=instance_id)
    try:
        yield span
    except BaseException as error:
        _end_failure(span, error, stage)
        raise
    else:
        span.end()


def _prepare(spec, settings, *, defer_relational):
    return prepare_application_invocation(spec.installation, spec.package, settings,
        spec.operation_id, spec.payload, spec.context, required_audience=spec.audience,
        defer_relational=defer_relational)


def _send(waiter, prepared, request_id):
    dispatch_started = False
    try:
        request=sign_message({"version":1,"request_id":request_id,"timestamp":int(time.time()),
            "operation_id":prepared.operation_id,"payload":prepared.payload,"context":prepared.context,
            **({"relational_invocation":prepared.relational_invocation} if prepared.relational_invocation is not None else {})},prepared.secret)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as origin:
            origin.settimeout(remaining(waiter.handoff_deadline));origin.connect(str(prepared.socket_path))
            if prepared.expected_peer is not None:
                from three_mm_platform_wire import peer_identity, process_generation
                pid, uid, _gid = peer_identity(origin)
                if (pid, uid, process_generation(pid, uid)) != prepared.expected_peer:
                    raise ApplicationGatewayError("Application host changed before dispatch", phase=DispatchPhase.NOT_DISPATCHED,
                        diagnostic_reason='authority_unavailable')
            origin.settimeout(remaining(waiter.handoff_deadline))
            # A partial send or failed FD handoff cannot prove non-execution.
            dispatch_started = True
            note_dispatch('execution_unconfirmed')
            send_message(origin,request)
            waiter.handoff(origin)
    except (OSError,ValueError,TypeError,KeyError,RecursionError,ApplicationTransportError) as exc:
        phase = DispatchPhase.EXECUTION_UNCONFIRMED if dispatch_started else DispatchPhase.NOT_DISPATCHED
        message = "Application result is unconfirmed; do not replay" if dispatch_started else "Application request was not dispatched"
        raise ApplicationGatewayError(message, phase=phase,
            diagnostic_reason=_failure_reason(exc, 'application.dispatch')) from exc


def _reserve(settings):
    import pwd
    return ResponseWaiter.reserve(settings.application_response_socket,pwd.getpwnam(settings.runtime_user).pw_uid)


@contextmanager
def _policy_transaction(db, boundary, binding=None, *, request_id=None):
    db.rollback()
    db.expire_all()
    def fence():
        if db.execute(update(Installation).where(*application_fence(binding))
                .values(updated_at=Installation.updated_at)).rowcount != 1:
            raise ApplicationGatewayError('Application changed at policy boundary',
                phase=DispatchPhase.NOT_DISPATCHED, diagnostic_reason='authority_unavailable')
    identifier = request_id if request_id is not None else binding.request_id
    with authority_diagnostic_scope(current_trace_id('invoke_' + identifier)):
        if boundary is not None:
            with boundary(fence=fence if binding is not None else None):
                yield
        else:
            try:
                if binding is not None and binding.authority_mode != 'compatibility':
                    raise ApplicationGatewayError('Current invocation requires an authority boundary',
                        phase=DispatchPhase.NOT_DISPATCHED, diagnostic_reason='authority_unavailable')
                if binding is not None:
                    fence()
                yield
            finally:
                db.rollback()


def begin_invocation(db, settings, admit, boundary=None):
    waiter=None
    identifier=uuid.uuid4().hex
    trace=DiagnosticSpan(core_diagnostics,current_trace_id('invoke_'+identifier),'application.admission', operation='application.invoke')
    try:
        with _policy_transaction(db,boundary,request_id=identifier):
            first=admit()
            trace.instance_id=first.installation.instance_id
            if boundary is None and first.installation.authority_mode != 'compatibility':
                raise ApplicationGatewayError('Current invocation requires an authority boundary',
                    phase=DispatchPhase.NOT_DISPATCHED, diagnostic_reason='authority_unavailable')
            prepared=_prepare(first,settings,defer_relational=True)
            binding=ApplicationResponseBinding(first.installation.id,application_snapshot(first.installation,first.package),
                prepared.secret,identifier,first.operation_id)
        # Existing relational metadata exchange is bounded to 2 s, without Core
        # DB/key leases. It issues a ticket only after current service admission.
        prepared=complete_application_preparation(db,binding.installation_id,prepared,
            required_audience=first.audience)
        with _policy_transaction(db,boundary,binding):
            current=admit()
            if application_snapshot(current.installation,current.package)!=binding.snapshot:
                raise ApplicationGatewayError("Application changed before dispatch",phase=DispatchPhase.NOT_DISPATCHED,
                    diagnostic_reason='authority_unavailable')
            fresh=_prepare(current,settings,defer_relational=True)
            if fresh.secret!=binding.secret or fresh.socket_path!=prepared.socket_path:
                raise ApplicationGatewayError("Application transport key or host changed",phase=DispatchPhase.NOT_DISPATCHED,
                    diagnostic_reason='authority_unavailable')
            # Recheck current human/session/terminal/peer policy under the same
            # transaction's code proof, AFTER metadata IPC and its write fence.
            db.expire_all();current=admit()
            if application_snapshot(current.installation,current.package)!=binding.snapshot:
                raise ApplicationGatewayError("Application changed before dispatch",phase=DispatchPhase.NOT_DISPATCHED,
                    diagnostic_reason='authority_unavailable')
            prepared=replace(fresh,payload=current.payload,context=current.context,
                relational_invocation=prepared.relational_invocation,
                needs_relational_invocation=False,expected_peer=first.expected_peer)
            # Admission linearizes here; no DB/key lease spans the host wait.
            db.commit()
        waiter=_reserve(settings)
        waiter.timeout_seconds=int(prepared.timeout_seconds)
        trace.end()
        with _invocation_span(binding.request_id,'application.dispatch',binding.snapshot[0]):
            _send(waiter,prepared,binding.request_id)
        return binding,waiter
    except BaseException as exc:
        _end_failure(trace,exc,'application.admission')
        if waiter is not None:waiter.close()
        if waiter is None and isinstance(exc,(OSError,ValueError,TypeError,KeyError,ImportError,RecursionError,ApplicationTransportError,SQLAlchemyError)):
            raise ApplicationGatewayError("Application request was not dispatched; admission unavailable",
                phase=DispatchPhase.NOT_DISPATCHED, diagnostic_reason=_failure_reason(exc,'application.admission')) from exc
        raise
    finally:db.rollback()


def finish_invocation(db,settings,admit,binding,response,on_success=None,boundary=None):
    try:
        with _policy_transaction(db,boundary,binding):
            # Preserve the first failing check before UI/key adapters or this
            # function redact it. These spans observe only; no retry or policy
            # decision depends on the optional diagnostic record.
            with authority_failure_span('application.policy_check'):
                current=admit()
            with authority_failure_span('application.binding_check'):
                if application_snapshot(current.installation,current.package)!=binding.snapshot:
                    raise ApplicationGatewayError("Application result is unconfirmed; do not replay", diagnostic_reason='authority_unavailable')
                prepared=_prepare(current,settings,defer_relational=True)
                if prepared.secret!=binding.secret:
                    raise ApplicationGatewayError("Application result is unconfirmed; do not replay", diagnostic_reason='authority_unavailable')
            with authority_failure_span('application.response_check'):
                verified=verify_message(response,prepared.secret,expected_request_id=binding.request_id)
                if verified.get("ok") is not True:
                    _record_host_failure(verified, binding)
                    raise ApplicationGatewayError("Application operation failed; outcome may be unconfirmed")
                result=verified.get("result")
                if not isinstance(result,dict):raise ApplicationGatewayError("Application result is invalid", diagnostic_reason='response_invalid')
                try:
                    validate_operation_payload(result,prepared.output_schema)
                except ApplicationGatewayError as exc:
                    raise ApplicationGatewayError('Application result is invalid', diagnostic_reason='response_invalid') from exc
                if len(json.dumps(result,ensure_ascii=False))>1024*1024:raise ApplicationGatewayError("Application result is too large", diagnostic_reason='response_too_large')
            with authority_failure_span('application.policy_recheck'):
                db.expire_all();admit()  # Current policy under the completion write fence.
            with authority_failure_span('application.commit'):
                if on_success is not None:on_success()
                db.commit()
            return result
    except HTTPException as exc:
        # A dispatched command may already have committed external effects.
        # A later policy refusal is an unknown outcome, never proof of no execution.
        raise ApplicationGatewayError("Application result is unconfirmed; do not replay",
            diagnostic_reason=_failure_reason(exc,'application.completion')) from exc
    except ApplicationGatewayError as exc:
        # A failed completion fence cannot make an already-dispatched call
        # "not dispatched" or authorize the browser to replay it.
        if exc.phase == DispatchPhase.NOT_DISPATCHED:
            raise ApplicationGatewayError("Application result is unconfirmed; do not replay",
                diagnostic_reason=exc.diagnostic_reason) from exc
        raise
    finally:db.rollback()


async def invoke_with_relay(db,settings,admit,*,on_success=None,boundary=None):
    from backend.services.application_code_scope import code_verification_scope
    with code_verification_scope():
        return await _invoke_with_relay(db,settings,admit,on_success=on_success,boundary=boundary)


async def _invoke_with_relay(db,settings,admit,*,on_success=None,boundary=None):
    waiter=None
    note_dispatch('not_dispatched')
    stage='application.admission'
    try:
        binding,waiter=await run_in_threadpool(begin_invocation,db,settings,admit,boundary)
        stage='application.response'
        with _invocation_span(binding.request_id,'application.response',binding.snapshot[0]):
            response=await waiter.receive()
        stage='application.completion'
        with _invocation_span(binding.request_id,'application.completion',binding.snapshot[0]):
            result = await run_in_threadpool(finish_invocation,db,settings,admit,binding,response,on_success,boundary)
            note_dispatch('completed')
            return result
    except (OSError,ValueError,TypeError,KeyError,ImportError,RecursionError,ApplicationTransportError,SQLAlchemyError) as exc:
        raise ApplicationGatewayError("Application result is unconfirmed; do not replay",
            diagnostic_reason=_failure_reason(exc,stage)) from exc
    finally:
        if waiter is not None:waiter.close()
