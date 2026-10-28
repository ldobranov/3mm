"""Current Core operation admission and completion around a response-only Runtime wait."""
from backend.services.operation_diagnostics import core_diagnostics
from three_mm_protocol.diagnostics import DiagnosticSpan
from dataclasses import dataclass, replace
import json
import socket
import time
import uuid

from sqlalchemy import update
from starlette.concurrency import run_in_threadpool
from fastapi import HTTPException
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services.application_extensions import (
    ApplicationGatewayError, prepare_application_invocation, validate_operation_payload,
)
from backend.services.application_response_relay import (
    ResponseWaiter, ApplicationResponseBinding, application_snapshot, application_fence,
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
                    raise ApplicationGatewayError("Application host changed before dispatch", phase=DispatchPhase.NOT_DISPATCHED)
            origin.settimeout(remaining(waiter.handoff_deadline))
            # A partial send or failed FD handoff cannot prove non-execution.
            dispatch_started = True
            send_message(origin,request)
            waiter.handoff(origin)
    except (OSError,ValueError,TypeError,KeyError,RecursionError,ApplicationTransportError) as exc:
        phase = DispatchPhase.EXECUTION_UNCONFIRMED if dispatch_started else DispatchPhase.NOT_DISPATCHED
        message = "Application result is unconfirmed; do not replay" if dispatch_started else "Application request was not dispatched"
        raise ApplicationGatewayError(message, phase=phase) from exc


def _reserve(settings):
    import pwd
    return ResponseWaiter.reserve(settings.application_response_socket,pwd.getpwnam(settings.runtime_user).pw_uid)


def begin_invocation(db, settings, admit):
    waiter=None;trace=None
    try:
        first=admit()
        identifier=uuid.uuid4().hex
        trace=DiagnosticSpan(core_diagnostics,"invoke_"+identifier,"application.admission",
            operation="application.invoke",instance_id=first.installation.instance_id)
        prepared=_prepare(first,settings,defer_relational=True)
        binding=ApplicationResponseBinding(first.installation.id,application_snapshot(first.installation,first.package),
            prepared.secret,identifier,first.operation_id)
        db.rollback()
        db.expire_all();current=admit()
        if application_snapshot(current.installation,current.package)!=binding.snapshot:
            raise ApplicationGatewayError("Application changed before dispatch",phase=DispatchPhase.NOT_DISPATCHED)
        # Existing relational metadata exchange is bounded to 2 s, without Core
        # DB/key leases. It issues a ticket only after current service admission.
        prepared=_prepare(current,settings,defer_relational=False)
        if prepared.secret!=binding.secret:
            raise ApplicationGatewayError("Application transport key changed",phase=DispatchPhase.NOT_DISPATCHED)
        if db.execute(update(Installation).where(*application_fence(binding)).values(updated_at=Installation.updated_at)).rowcount!=1:
            raise ApplicationGatewayError("Application changed before dispatch",phase=DispatchPhase.NOT_DISPATCHED)
        # Recheck the human/session/terminal/peer and UI policy after metadata IPC.
        db.expire_all();current=admit()
        if application_snapshot(current.installation,current.package)!=binding.snapshot:
            raise ApplicationGatewayError("Application changed before dispatch",phase=DispatchPhase.NOT_DISPATCHED)
        prepared=replace(prepared,payload=current.payload,context=current.context)
        prepared=replace(prepared,expected_peer=first.expected_peer)
        # This commit is the admission linearization point. Reservation grants
        # response capacity only; it must not time expensive trust/metadata work.
        # Revocation after admission still fences disclosure at completion.
        db.commit()  # No write/read transaction spans reservation or execution.
        waiter=_reserve(settings)
        waiter.timeout_seconds=int(prepared.timeout_seconds)
        trace.end()
        with DiagnosticSpan(core_diagnostics,"invoke_"+binding.request_id,"application.dispatch",
                operation="application.invoke",instance_id=binding.snapshot[0]):
            _send(waiter,prepared,binding.request_id)
        return binding,waiter
    except BaseException as exc:
        if trace is not None:trace.end("error","operation_failed")
        if waiter is not None:waiter.close()
        if waiter is None and isinstance(exc,(OSError,ValueError,TypeError,KeyError,ImportError,RecursionError,ApplicationTransportError)):
            raise ApplicationGatewayError("Application request was not dispatched; admission unavailable",
                phase=DispatchPhase.NOT_DISPATCHED) from exc
        raise
    finally:db.rollback()


def finish_invocation(db,settings,admit,binding,response,on_success=None):
    try:
        db.expire_all();current=admit()
        if application_snapshot(current.installation,current.package)!=binding.snapshot:
            raise ApplicationGatewayError("Application result is unconfirmed; do not replay")
        prepared=_prepare(current,settings,defer_relational=True)
        if prepared.secret!=binding.secret:
            raise ApplicationGatewayError("Application result is unconfirmed; do not replay")
        verified=verify_message(response,prepared.secret,expected_request_id=binding.request_id)
        if verified.get("ok") is not True:
            raise ApplicationGatewayError("Application operation failed; outcome may be unconfirmed")
        result=verified.get("result")
        if not isinstance(result,dict):raise ApplicationGatewayError("Application result is invalid")
        validate_operation_payload(result,prepared.output_schema)
        if len(json.dumps(result,ensure_ascii=False))>1024*1024:raise ApplicationGatewayError("Application result is too large")
        if db.execute(update(Installation).where(*application_fence(binding)).values(updated_at=Installation.updated_at)).rowcount!=1:
            raise ApplicationGatewayError("Application result is unconfirmed; do not replay")
        db.expire_all();admit()  # Current policy under the completion write fence.
        if on_success is not None:on_success()
        db.commit()
        return result
    except HTTPException as exc:
        # A dispatched command may already have committed external effects.
        # A later policy refusal is an unknown outcome, never proof of no execution.
        raise ApplicationGatewayError("Application result is unconfirmed; do not replay") from exc
    finally:db.rollback()


async def invoke_with_relay(db,settings,admit,*,on_success=None):
    from backend.services.application_code_scope import code_verification_scope
    with code_verification_scope():
        return await _invoke_with_relay(db,settings,admit,on_success=on_success)


async def _invoke_with_relay(db,settings,admit,*,on_success=None):
    waiter=None
    try:
        binding,waiter=await run_in_threadpool(begin_invocation,db,settings,admit)
        with DiagnosticSpan(core_diagnostics,"invoke_"+binding.request_id,"application.response",
                operation="application.invoke",instance_id=binding.snapshot[0]):
            response=await waiter.receive()
            return await run_in_threadpool(finish_invocation,db,settings,admit,binding,response,on_success)
    except (OSError,ValueError,TypeError,KeyError,ImportError,RecursionError,ApplicationTransportError) as exc:
        raise ApplicationGatewayError("Application result is unconfirmed; do not replay") from exc
    finally:
        if waiter is not None:waiter.close()
