"""Application-bound M21 browser connector. Not mounted by production Core.

The trusted composition root must supply an exact already-supervised provider
connection. This module has no provider discovery fallback, shell launcher,
remote enrollment or OS-isolation claim. Browser tickets never replace M20.
"""

import asyncio
import json
import logging
import math
import secrets
import threading
import time
from collections import deque
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from functools import wraps

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.db.audit_log import AuditLog
from backend.applications.management.api import (
    _active_package,
    _installation,
    _ui_route,
)
from backend.applications.authority.access import (
    application_permission_ids,
    resolve_application_principal,
)
from backend.applications.authority.management import AuthorityManagementError
from backend.applications.authority.sources import _read_snapshot
from backend.applications.sessions.authority import SessionAuthorityError
from backend.applications.sessions.runtimes import ReviewedSessionRuntime
from backend.artifacts.code_scope import code_verification_scope
from packages.protocol.interactive_session import (
    MAX_SESSION_FRAME_BYTES,
    MAX_SESSION_PAYLOAD_BYTES,
    SessionControlV1,
    SessionOpenRequestV1,
    decode_session_frame,
    encode_session_frame,
)
from components.system_runtime.session_output import (
    SessionOutputAuthorityError,
    pump_session_output,
)
from components.system_runtime.session_worker import SessionStartupError, startup_step

logger = logging.getLogger(__name__)
from backend.system.diagnostics.operations import observed_step, operation_step, _authority_reason, core_diagnostics, authority_diagnostic_scope
from backend.system.diagnostics.failures import current_trace_id, recent_http_failures, note_instance, note_handled_refusal
from packages.protocol.diagnostic_cases import SESSION_STAGES
from packages.protocol.diagnostics import DiagnosticSpan, REASONS


class _SessionStreamError(RuntimeError):
    """Closed stage/duration only; never input, terminal text or exception text."""
    def __init__(self, stage, reason, duration_ms):
        if (stage not in SESSION_STAGES or reason not in REASONS - {'ok'}
                or not math.isfinite(duration_ms) or not 0 <= duration_ms <= 900000):
            raise ValueError('Invalid session timing')
        super().__init__('Session stream was not confirmed')
        self.diagnostic_stage, self.diagnostic_reason = stage, reason
        self.duration_ms = duration_ms


@contextmanager
def _stream_step(trace, stage):
    began = time.monotonic()
    span = DiagnosticSpan(core_diagnostics, trace, stage, operation='session.stream')
    with authority_diagnostic_scope(trace, operation='session.stream'):
        try:
            yield
        except Exception as error:
            reason = ('deadline_exceeded' if isinstance(error, TimeoutError)
                      else _authority_reason(error) if isinstance(error,
                          (SessionAuthorityError, AuthorityManagementError, HTTPException))
                      else getattr(error, 'diagnostic_reason', 'session_runtime_failed'))
            if type(reason) is not str or reason not in REASONS - {'ok'}:
                reason = 'session_runtime_failed'
            span.end('error', reason)
            if isinstance(error, (_SessionStreamError, SessionStartupError)):
                raise  # Preserve the first exact phase, not a surrounding phase.
            raise _SessionStreamError(stage, reason, (time.monotonic()-began)*1000) from None
        else:
            span.end()


def _serialized_authority(method):
    @wraps(method)
    def invoke(self, *args, **kwargs):
        with operation_step('session.authority.lock_queue'):
            self.authority_lock.acquire()
        try:
            # Reuse immutable bytes only within this check. The next input/output
            # re-reads actual login/grants/resources; no authority is cached.
            with code_verification_scope():
                return method(self, *args, **kwargs)
        finally:
            self.authority_lock.release()

    return invoke


class _OwnedProvider:
    def __init__(self, provider, session_id, module_id, admitted, request):
        self.provider, self.session_id = provider, session_id
        self.module_id, self.admitted, self.request = module_id, admitted, request
        self.finalized = False
        self.lock = asyncio.Lock()
        self.closed = False
        self.failed = False

    async def close(self, session_id, reason):
        async with self.lock:
            if self.failed:
                raise RuntimeError("Session cleanup remains unconfirmed")
            if not self.closed:
                self.closed = True
                try:
                    await asyncio.wait_for(self.provider.close(session_id, reason), 5)
                except BaseException:
                    self.failed = True
                    raise

    async def read_output(self, session_id):
        return await self.provider.read_output(session_id)


class ApplicationBrowserSessions:
    def __init__(
        self,
        authority,
        *,
        runtimes=(),
        runtime_resolver=None,
        allowed_origins=(),
        lifetime=900,
        startup_timeout=110.0,
        startup_check_interval=1.0,
        startup_authorization_timeout=5.0,
    ):
        for name, value, maximum in (
            ("timeout", startup_timeout, 110.0),
            ("check interval", startup_check_interval, 1.0),
            ("authorization timeout", startup_authorization_timeout, 5.0),
        ):
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not 0.01 <= value <= maximum):
                raise ValueError(f"Session startup {name} is outside bounds")
        if not 1 <= lifetime <= 900:
            raise ValueError("Session lifetime is outside bounds")
        self.authority, self.engine = authority, authority.manager.engine
        self.runtimes = tuple(runtimes)
        self.runtime_resolver = runtime_resolver
        self.origins = frozenset(allowed_origins)
        self.lifetime = lifetime
        self.startup_timeout = startup_timeout
        self.startup_check_interval = startup_check_interval
        self.startup_authorization_timeout = startup_authorization_timeout
        self.lock = threading.Lock()
        self.authority_lock = threading.RLock()
        self.clock = time.monotonic
        self.tickets, self.spent, self.owned, self.leases = {}, set(), {}, set()
        self.reservations = {}
        self.diagnostic_traces = {}  # Bounded by the same owned-session leases.
        self.failures = deque(
            maxlen=64
        )  # Types only; never provider text or user input.

    @observed_step('session.ui')
    def verify_ui(self, module_id, binding, authorization):
        # Discover only the installation ID in a short, closed snapshot. Loading
        # and authenticating its UI must not nest readers inside this reader.
        with _read_snapshot(self.engine) as db:
            principal = resolve_application_principal(authorization, db)
            if principal.kind != "user":
                raise SessionAuthorityError("A current user login is required")
            installation = _installation(db, module_id)
            if installation.authority_mode == "compatibility":
                # Compatibility UI remains compatible; _resource still requires
                # a real enforced session grant before offering/opening anything.
                return self._verify_ui_in_snapshot(db, module_id, binding, authorization)
            installation_id = installation.id
        with self.authority.manager.ui_trust_snapshot(
            installation_id, binding.built_ui_sha256
        ) as db:
            return self._verify_ui_in_snapshot(db, module_id, binding, authorization)

    def _verify_ui_in_snapshot(self, db, module_id, binding, authorization):
        # Re-read the actual login, package, role and application permissions in
        # the same fresh snapshot as native code trust. No preflight principal,
        # old permission list or grant is cached across checks.
        principal = resolve_application_principal(authorization, db)
        if principal.kind != "user":
            raise SessionAuthorityError("A current user login is required")
        installation = _installation(db, module_id)
        package = _active_package(db, installation)
        permissions = application_permission_ids(db, installation.id, principal.user_id)
        _definition, route = _ui_route(
            package, binding, principal, permissions, db=db, installation=installation,
        )
        if route.audience not in {"operator", "administrator"}:
            raise SessionAuthorityError("Session route audience is unavailable")
        note_instance(installation.instance_id)
        return installation.id

    def _release(self, admitted):
        self.leases.discard(admitted.session_id)
        self.diagnostic_traces.pop(admitted.session_id, None)
        key = (admitted.installation_id, admitted.binding_id)
        if self.reservations.get(key) == admitted.session_id:
            del self.reservations[key]

    @observed_step('session.resource')
    def _resource(self, installation_id, binding_id, authorization):
        prepared = self.authority.manager._prepare(installation_id)
        with (
            self.authority.manager.keys.read_locked() as key,
            _read_snapshot(self.engine) as db,
        ):
            grant = self.authority.manager._require_grant(
                db, key, installation_id, prepared, f"session:{binding_id}:open"
            )
            resource = next(
                item
                for item in grant["data"]["subject"].get("sessions", ())
                if item["declaration"]["binding_id"] == binding_id
            )
        declaration = resource["declaration"]
        request = SessionOpenRequestV1(
            request_id="discovery",
            provider_id=declaration["provider_id"],
            capability_id=declaration["capability_id"],
            device_id=resource["target_device_id"],
            access_mode=declaration["access_mode"],
            options=declaration["options"],
        )
        self.authority.admit(
            installation_id=installation_id,
            binding_id=binding_id,
            session_id="ses_" + secrets.token_hex(16),
            authorization=authorization,
            request=request,
        )
        return resource

    def _runtime(self, resource):
        if self.runtime_resolver is not None:
            runtime = self.runtime_resolver(resource)
            if runtime is None:
                return None
            candidates = (runtime,)
        else:
            candidates = self.runtimes
        declaration = resource["declaration"]
        matches = [
            item
            for item in candidates
            if (
                item.device_id,
                item.provider_id,
                item.provider_version,
                item.control_revision,
            )
            == (
                resource["target_device_id"],
                declaration["provider_id"],
                resource["provider_version"],
                resource["control_revision"],
            )
        ]
        if (len(matches) != 1 or not callable(matches[0].is_current)
                or matches[0].is_current() is not True) or not all(
            callable(getattr(matches[0].provider, name, None))
            for name in ("open", "receive", "control", "close", "read_output")
        ):
            return None
        return matches[0]

    @_serialized_authority
    def targets(self, module_id, binding, authorization):
        installation_id = self.verify_ui(module_id, binding, authorization)
        prepared = self.authority.manager._prepare(installation_id)
        result = []
        for declaration in prepared.package.application_extension.session_bindings:
            try:
                resource = self._resource(
                    installation_id, declaration.binding_id, authorization
                )
            except (ValueError, AuthorityManagementError, KeyError, StopIteration) as error:
                reason = ('session_resource_unavailable' if isinstance(error, (KeyError, StopIteration))
                          else _authority_reason(error))
                note_handled_refusal('session.resource', reason)
                continue  # No disclosure of a target without both current grants.
            result.append(
                {
                    "bindingId": declaration.binding_id,
                    "deviceId": resource["target_device_id"],
                    "providerId": declaration.provider_id,
                    "capabilityIds": [declaration.capability_id],
                    "accessMode": declaration.access_mode,
                    "controlActions": list(declaration.control_actions),
                    "options": declaration.options,
                    "available": self._runtime(resource) is not None,
                }
            )
        return {"session_host_version": 1, "targets": result}

    @_serialized_authority
    def issue(self, module_id, binding, authorization, binding_id, request):
        installation_id = self.verify_ui(module_id, binding, authorization)
        resource = self._resource(installation_id, binding_id, authorization)
        with operation_step('session.runtime'):
            runtime = self._runtime(resource)
            if runtime is None:
                raise SessionAuthorityError("Reviewed session runtime is not connected", reason='session_runtime_unavailable')
        session_id = "ses_" + secrets.token_hex(16)
        with operation_step('session.authority'):
            admitted = self.authority.admit(
                installation_id=installation_id,
                binding_id=binding_id,
                session_id=session_id,
                authorization=authorization,
                request=request,
            )
        identity = (installation_id, admitted.login_session_id, request.request_id)
        ticket = secrets.token_urlsafe(32)
        now = self.clock()
        with operation_step('session.capacity'), self.lock:
            for key, value in list(self.tickets.items()):
                if value[0] <= now:
                    self._release(value[4])
                    del self.tickets[key]
            # Bounded fail-closed ledger, never evict request IDs to make retries
            # look fresh. Restart is not a durable idempotency/receipt boundary.
            if identity in self.spent:
                raise SessionAuthorityError("Session request already used or capacity unavailable", reason='session_request_used')
            if len(self.spent) >= 1024 or len(self.leases) >= 64:
                raise SessionAuthorityError("Session request already used or capacity unavailable", reason='session_capacity_full')
            if (installation_id, binding_id) in self.reservations:
                raise SessionAuthorityError("Session request already used or capacity unavailable", reason='session_binding_busy')
            self.spent.add(identity)
            self.leases.add(session_id)
            self.reservations[(installation_id, binding_id)] = session_id
            self.diagnostic_traces[session_id] = current_trace_id('invoke_' + secrets.token_hex(16))
            self.tickets[ticket] = (
                now + 15,
                module_id,
                binding,
                authorization,
                admitted,
                request,
                runtime,
            )
        return {
            "session_host_version": 1,
            "ticket": ticket,
            "session_id": session_id,
            "request_id": request.request_id,
            "expires_in_seconds": 15,
        }

    def redeem(self, ticket, module_id, entrypoint_id):
        with self.lock:
            item = self.tickets.pop(ticket, None) if type(ticket) is str else None
        if item is None:
            raise SessionAuthorityError("Session ticket is unavailable", reason='session_ticket_unavailable')
        if (
            item[0] <= self.clock()
            or item[1] != module_id
            or item[2].entrypoint_id != entrypoint_id
        ):
            with self.lock:
                self._release(item[4])
            raise SessionAuthorityError("Session ticket is unavailable", reason='session_ticket_unavailable')
        return item

    def _audit(self, admitted, module_id, outcome, actor_user_id=None):
        with Session(self.engine) as db, db.begin():
            db.add(
                AuditLog(
                    user_id=admitted.user_id,
                    session_id=admitted.login_session_id,
                    action="APPLICATION_SESSION_LIFECYCLE",
                    entity_type="application_session",
                    entity_id=admitted.installation_id,
                    entity_name=module_id,
                    changes={
                        "session_id": admitted.session_id,
                        "binding_id": admitted.binding_id,
                        "grant_revision": admitted.grant_revision,
                        "outcome": outcome,
                        **({"reconciled_by": actor_user_id} if actor_user_id is not None else {}),
                    },
                )
            )

    @_serialized_authority
    def _check_current(
        self, module_id, ui, authorization, admitted, request, operation, action
    ):
        self.verify_ui(module_id, ui, authorization)
        self.authority.check(
            admitted,
            authorization=authorization,
            request=request,
            session_id=admitted.session_id,
            operation=operation,
            control_action=action,
        )

    def _recovery_actor(self, authorization):
        from backend.accounts.dependencies import require_user, require_admin
        with _read_snapshot(self.engine) as db:
            claims = require_user(authorization=authorization, db=db)
            if type(claims.get("sid")) is not int or claims["sid"] < 1:
                raise HTTPException(401, "A current tracked administrator login is required")
            return require_admin(claims=claims, db=db).id

    def recovery_status(self, module_id, authorization):
        self._recovery_actor(authorization)
        with self.lock:
            records = [
                {"session_id": sid, "state": "cleanup_required" if owned.finalized and owned.failed else "active_or_closing",
                 "binding_id": owned.admitted.binding_id, "device_id": owned.request.device_id,
                 "provider_id": owned.request.provider_id, "grant_revision": owned.admitted.grant_revision}
                for sid, owned in self.owned.items() if owned.module_id == module_id
            ]
        return {"session_recovery_version": 1, "sessions": records}

    async def confirm_cleanup(self, module_id, session_id, authorization):
        actor = await asyncio.to_thread(self._recovery_actor, authorization)
        with self.lock:
            owned = self.owned.get(session_id)
            if owned is None or owned.module_id != module_id:
                raise HTTPException(404, "Owned session recovery was not found")
        async with owned.lock:
            if not owned.finalized or not owned.closed or not owned.failed:
                raise HTTPException(409, "Session cleanup is not awaiting reconciliation")
            confirm = getattr(owned.provider, "confirm_cleanup", None)
            if not callable(confirm):
                raise HTTPException(409, "Executor cannot confirm its OS cleanup")
            try:
                if await asyncio.wait_for(confirm(), 5) is not None:
                    raise ValueError("Invalid cleanup observation")
                # Recheck the actor after I/O; revocation cannot release a fence.
                await asyncio.to_thread(self._recovery_actor, authorization)
                await asyncio.to_thread(self._audit, owned.admitted, module_id, "cleanup_reconciled", actor)
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(409, "Exact OS cleanup remains unconfirmed") from None
            with self.lock:
                if self.owned.get(session_id) is not owned:
                    raise HTTPException(409, "Owned session recovery changed")
                self.owned.pop(session_id)
                self._release(owned.admitted)
        return {"session_recovery_version": 1, "session_id": session_id, "state": "cleanup_confirmed"}

    async def _startup_authorize(self, authorize, stage):
        started = time.monotonic()
        try:
            await asyncio.wait_for(authorize(), self.startup_authorization_timeout)
        except Exception as error:
            reason = ('deadline_exceeded' if isinstance(error, TimeoutError)
                      else error.diagnostic_reason if isinstance(error, _SessionStreamError)
                      else _authority_reason(error))
            raise SessionStartupError(stage, reason, (time.monotonic() - started) * 1000) from None

    async def _open_with_authority(self, operation, authorize):
        """Bound cold startup while checking the same live authority throughout.

        The caller authorizes before creating the owned operation. A slow ARM
        worker may need more time than an input/control operation, but that time
        never freezes M20/UI/user/runtime authority or permits an escaped task.
        """
        opening = asyncio.create_task(operation)
        async def guarded():
            while True:
                done, _ = await asyncio.wait(
                    (opening,), timeout=self.startup_check_interval
                )
                if opening in done:
                    # Preserve a worker's original failure instead of masking it
                    # behind a later authorization timeout. Successful readiness
                    # still needs current authority before browser acceptance.
                    await opening
                await self._startup_authorize(authorize, 'session.opening.authority_recheck')
                if opening in done:
                    return
        try:
            with startup_step('session.opening.total'):
                await asyncio.wait_for(guarded(), self.startup_timeout)
        finally:
            if not opening.done():
                opening.cancel()
            # Do not let a revoked/timed-out startup continue behind cleanup.
            await asyncio.gather(opening, return_exceptions=True)

    async def serve(self, websocket, module_id, entrypoint_id):
        started = time.monotonic()
        trace = 'invoke_' + secrets.token_hex(16)
        def record_failure(stage, reason, execution='unknown', step_duration=None):
            try:
                duration = (time.monotonic() - started) * 1000
                recent_http_failures.record(trace_id=trace, method='GET',
                    route='/api/v1/application-extensions/{module_id}/session-host/{entrypoint_id}/ws',
                    status=None, duration_ms=duration, phase=execution,
                    details=((stage, reason),), transport='websocket')
                core_diagnostics.record(trace_id=trace, stage=stage, operation='session.stream',
                    result='error', reason=reason, duration_ms=duration if step_duration is None else step_duration)
            except Exception:
                pass  # Optional diagnostics may not affect session cleanup or admission.
        # No JWT/ticket in a URL, no absent/wildcard Origin fallback.
        if (
            websocket.headers.get("origin") not in self.origins
            or websocket.query_params
        ):
            record_failure('session.authentication', 'session_origin_denied', 'not_dispatched')
            await websocket.close(code=1008)
            return
        await websocket.accept()
        owned = None
        admitted = None
        pump = reader = None
        phase = "authentication"
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), 5)
            auth = json.loads(raw) if len(raw.encode()) <= 1024 else None
            if (
                type(auth) is not dict
                or set(auth) != {"op", "ticket"}
                or auth["op"] != "authenticate"
            ):
                raise SessionAuthorityError("Session authentication is unavailable")
            _, _, ui, authorization, admitted, request, runtime = self.redeem(
                auth["ticket"], module_id, entrypoint_id
            )
            with self.lock:
                trace = self.diagnostic_traces.get(admitted.session_id, trace)
            phase = "opening"
            session_id = admitted.session_id
            deadline = self.clock() + self.lifetime
            send_lock = asyncio.Lock()
            check_lock = asyncio.Lock()
            output_seq, input_seq = 0, 0

            async def check(operation="output", action=None):
                with _stream_step(trace, 'session.runtime.current'):
                    if (self.clock() >= deadline or owned is not None and owned.closed
                        or await asyncio.to_thread(runtime.is_current) is not True):
                        raise SessionAuthorityError("Session expired")
                with _stream_step(trace, 'session.authority.queue'):
                    await check_lock.acquire()
                try:
                    queued = time.monotonic()
                    def current():
                        try:
                            core_diagnostics.record(trace_id=trace, stage='session.authority.thread_queue',
                                operation='session.stream', result='ok', reason='ok',
                                duration_ms=(time.monotonic()-queued)*1000)
                        except Exception:
                            pass  # Optional timing never changes current authority.
                        self._check_current(module_id, ui, authorization, admitted,
                            request, operation, action)
                    with _stream_step(trace, 'session.authority.current'):
                        await asyncio.to_thread(current)
                finally:
                    check_lock.release()

            async def send_json(value, *, operation="output"):
                with _stream_step(trace, 'session.output.send_queue'):
                    await send_lock.acquire()
                try:
                    if operation == "input":
                        # Empty PTY responses have no intervening output I/O:
                        # the fresh post-input check and ACK admission are one
                        # boundary, AFTER any send-lock wait, not two full reads.
                        with _stream_step(trace, 'session.input.after'):
                            await check("input")
                    else:
                        await check(operation)
                    await asyncio.wait_for(websocket.send_json(value), 10)
                finally:
                    send_lock.release()

            async def send_output(data):
                nonlocal output_seq
                if (
                    type(data) is not bytes
                    or not 1 <= len(data) <= MAX_SESSION_PAYLOAD_BYTES
                ):
                    raise SessionAuthorityError("Session output exceeds bounds")
                with _stream_step(trace, 'session.output.send_queue'):
                    await send_lock.acquire()
                try:
                    await check()
                    output_seq += 1
                    frame = encode_session_frame(
                        op="data",
                        seq=output_seq,
                        session_id=session_id,
                        payload=data,
                        payload_kind="binary",
                    )
                    with _stream_step(trace, 'session.output.send'):
                        await asyncio.wait_for(websocket.send_bytes(frame), 10)
                finally:
                    send_lock.release()

            async def send_frame(frame):
                _header, payload = decode_session_frame(frame)
                await send_output(payload)

            await self._startup_authorize(lambda: check('status'), 'session.opening.authority_initial')
            owned = _OwnedProvider(runtime.provider, session_id, module_id, admitted, request)
            with self.lock:
                self.owned[session_id] = owned
            with startup_step('session.opening.audit'):
                await asyncio.to_thread(self._audit, admitted, module_id, "start_requested")
            # Context is Core-owned, not the browser payload or a naked hello.
            await self._open_with_authority(
                runtime.provider.open(
                    {
                        "session_id": session_id,
                        "device_id": request.device_id,
                        "capability_id": request.capability_id,
                        "access_mode": request.access_mode,
                        "options": request.options,
                    }
                ),
                lambda: check("status"),
            )
            created = datetime.now(UTC)
            with startup_step('session.opening.acceptance'):
                await send_json(
                    {
                        "op": "opened",
                        "acceptance": {
                            "request_id": request.request_id,
                            "session_id": session_id,
                            "state": "active",
                            "device_id": request.device_id,
                            "provider_id": request.provider_id,
                            "capability_id": request.capability_id,
                            "created_at": created.isoformat(),
                            "expires_at": (
                                created + timedelta(seconds=max(0, deadline - self.clock()))
                            ).isoformat(),
                        },
                    }
                )
            pump = asyncio.create_task(
                pump_session_output(owned, session_id, send_frame, authorize=check)
            )
            controls = set()
            while True:
                phase = "stream"
                reader = asyncio.create_task(websocket.receive())
                done, _ = await asyncio.wait(
                    (reader, pump), return_when=asyncio.FIRST_COMPLETED
                )
                if pump in done:
                    await pump
                    break
                message = reader.result()
                reader = None
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    phase = "input"
                    data = message["bytes"]
                    if len(data) > MAX_SESSION_FRAME_BYTES:
                        raise SessionAuthorityError("Session input exceeds bounds")
                    header, payload = decode_session_frame(data)
                    if (
                        header.session_id != session_id
                        or header.op != "data"
                        or header.seq != input_seq + 1
                    ):
                        raise SessionAuthorityError("Session input sequence is invalid")
                    with _stream_step(trace, 'session.input.before'):
                        await check("input")
                    input_seq = header.seq
                    with _stream_step(trace, 'session.input.provider'):
                        output = await asyncio.wait_for(
                            runtime.provider.receive(session_id, payload), 10
                        )
                    if type(output) is not bytes:
                        raise SessionAuthorityError(
                            "Session provider response is invalid"
                        )
                    if output:
                        with _stream_step(trace, 'session.input.after'):
                            await check("input")
                        await send_output(output)
                    with _stream_step(trace, 'session.input.ack'):
                        await send_json(
                            {"op": "input_ack", "session_id": session_id, "seq": input_seq},
                            operation="input",
                        )
                else:
                    phase = "control"
                    text = message.get("text", "")
                    if len(text.encode()) > MAX_SESSION_FRAME_BYTES:
                        raise SessionAuthorityError("Session control exceeds bounds")
                    value = json.loads(text)
                    if value == {"op": "close", "session_id": session_id}:
                        break  # Owned cleanup remains possible after revocation.
                    if (
                        type(value) is not dict
                        or set(value) != {"op", "control"}
                        or value["op"] != "control"
                    ):
                        raise SessionAuthorityError("Unsupported session operation")
                    control = SessionControlV1.model_validate(
                        value["control"], strict=True
                    )
                    if (
                        control.session_id != session_id
                        or control.control_id in controls
                        or len(controls) >= 1024
                    ):
                        raise SessionAuthorityError(
                            "Session control is invalid or already used"
                        )
                    await check("control", control.action)
                    controls.add(control.control_id)
                    with _stream_step(trace, 'session.control.provider'):
                        await asyncio.wait_for(
                            runtime.provider.control(
                                session_id,
                                {"action": control.action, "arguments": control.arguments},
                            ),
                            10,
                        )
                    await send_json(
                        {
                            "op": "control_ack",
                            "session_id": session_id,
                            "control_id": control.control_id,
                        }
                    )
        except Exception as exc:
            # No output, tokens, tickets, provider exception or command data in errors.
            self.failures.append(type(exc).__name__)
            category = (
                "authority_timeout"
                if isinstance(exc, SessionOutputAuthorityError)
                and isinstance(exc.__cause__, TimeoutError)
                else "authority"
                if isinstance(
                    exc,
                    (SessionAuthorityError, AuthorityManagementError, HTTPException, SessionOutputAuthorityError),
                )
                else "timeout" if isinstance(exc, TimeoutError) else "runtime"
            )
            logger.warning(
                "Application session stopped: phase=%s category=%s", phase, category
            )
            reason = ('deadline_exceeded' if isinstance(exc, TimeoutError) or isinstance(exc.__cause__, TimeoutError)
                      else _authority_reason(exc) if category == 'authority'
                      else 'request_invalid' if phase == 'authentication'
                      else 'session_runtime_failed')
            detail = (exc.__cause__ if isinstance(exc, SessionOutputAuthorityError)
                      and isinstance(exc.__cause__, _SessionStreamError) else exc)
            stage = detail.diagnostic_stage if isinstance(detail, (SessionStartupError, _SessionStreamError)) else 'session.' + phase
            if isinstance(detail, (SessionStartupError, _SessionStreamError)):
                reason = detail.diagnostic_reason
            record_failure(stage, reason, 'execution_unconfirmed' if owned is not None else 'not_dispatched',
                           detail.duration_ms if isinstance(detail, (SessionStartupError, _SessionStreamError)) else None)
        finally:

            async def finalize():
                for task in (reader, pump):
                    if task is not None and not task.done():
                        task.cancel()
                await asyncio.gather(
                    *(task for task in (reader, pump) if task is not None),
                    return_exceptions=True,
                )
                if owned is not None:
                    try:
                        await owned.close(owned.session_id, "browser_closed")
                    except BaseException:
                        owned.failed = True
                        record_failure('session.cleanup', 'session_cleanup_unconfirmed', 'execution_unconfirmed')
                        logger.warning("Application session cleanup unconfirmed")
                    try:
                        await asyncio.to_thread(
                            self._audit,
                            admitted,
                            module_id,
                            "cleanup_unconfirmed" if owned.failed else "closed",
                        )
                    except Exception:
                        owned.failed = True  # Audit outcome must not disappear, either.
                        record_failure('session.cleanup', 'session_cleanup_unconfirmed', 'execution_unconfirmed')
                        logger.warning("Application session cleanup audit unavailable")
                    if not owned.failed:
                        with self.lock:
                            self.owned.pop(owned.session_id, None)
                            self._release(admitted)
                elif admitted is not None:
                    with self.lock:
                        self._release(admitted)
                if owned is not None:
                    owned.finalized = True

            cleanup = asyncio.create_task(finalize())
            try:
                await asyncio.wait_for(asyncio.shield(cleanup), 15)
            except asyncio.CancelledError:
                # Repeated disconnect/cancel must not abandon an owned close.
                try:
                    await asyncio.wait_for(asyncio.shield(cleanup), 15)
                except BaseException:
                    if owned is not None:
                        owned.failed = True
            except Exception:
                if owned is not None:
                    owned.failed = True
            try:
                await websocket.close(
                    code=1000 if owned is not None and not owned.failed else 1008
                )
            except Exception:
                pass
