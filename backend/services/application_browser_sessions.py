"""Application-bound M21 browser connector. Not mounted by production Core.

The trusted composition root must supply an exact already-supervised provider
connection. This module has no provider discovery fallback, shell launcher,
remote enrollment or OS-isolation claim. Browser tickets never replace M20.
"""

import asyncio
import json
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import wraps

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.db.audit_log import AuditLog
from backend.routes.application_extensions import (
    _active_package,
    _installation,
    _ui_route,
)
from backend.services.application_access import (
    application_permission_ids,
    resolve_application_principal,
)
from backend.services.application_authority_management import AuthorityManagementError
from backend.services.application_authority_sources import _read_snapshot
from backend.services.application_session_authority import SessionAuthorityError
from three_mm_protocol.interactive_session import (
    MAX_SESSION_FRAME_BYTES,
    MAX_SESSION_PAYLOAD_BYTES,
    SessionControlV1,
    SessionOpenRequestV1,
    decode_session_frame,
    encode_session_frame,
)
from three_mm_runtime.session_output import pump_session_output


def _serialized_authority(method):
    @wraps(method)
    def invoke(self, *args, **kwargs):
        with self.authority_lock:
            return method(self, *args, **kwargs)

    return invoke


@dataclass(frozen=True)
class ReviewedSessionRuntime:
    """Trusted runtime connection, pinned to the reviewed registry generation."""

    device_id: str
    provider_id: str
    provider_version: str
    control_revision: str
    provider: object


class _OwnedProvider:
    def __init__(self, provider, session_id):
        self.provider, self.session_id = provider, session_id
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
    def __init__(self, authority, *, runtimes=(), runtime_resolver=None, allowed_origins=(), lifetime=900):
        if not 1 <= lifetime <= 900:
            raise ValueError("Session lifetime is outside bounds")
        self.authority, self.engine = authority, authority.manager.engine
        self.runtimes = tuple(runtimes)
        self.runtime_resolver = runtime_resolver
        self.origins = frozenset(allowed_origins)
        self.lifetime = lifetime
        self.lock = threading.Lock()
        self.authority_lock = threading.RLock()
        self.clock = time.monotonic
        self.tickets, self.spent, self.owned, self.leases = {}, set(), {}, set()
        self.reservations = {}
        self.failures = deque(
            maxlen=64
        )  # Types only; never provider text or user input.

    def verify_ui(self, module_id, binding, authorization):
        # Reuse the real compiled-build/native-review and dynamic route checks.
        with _read_snapshot(self.engine) as db:
            principal = resolve_application_principal(authorization, db)
            if principal.kind != "user":
                raise SessionAuthorityError("A current user login is required")
            installation = _installation(db, module_id)
            package = _active_package(db, installation)
            permissions = application_permission_ids(
                db, installation.id, principal.user_id
            )
            _definition, route = _ui_route(
                package,
                binding,
                principal,
                permissions,
                db=db,
                installation=installation,
            )
            if route.audience not in {"operator", "administrator"}:
                raise SessionAuthorityError("Session route audience is unavailable")
            return installation.id

    def _release(self, admitted):
        self.leases.discard(admitted.session_id)
        key = (admitted.installation_id, admitted.binding_id)
        if self.reservations.get(key) == admitted.session_id:
            del self.reservations[key]

    def _resource(self, installation_id, binding_id, authorization):
        prepared = self.authority.manager._prepare(installation_id)
        with (
            self.authority.manager.keys.locked() as key,
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
        if len(matches) != 1 or not all(
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
            except (ValueError, AuthorityManagementError, KeyError, StopIteration):
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
        runtime = self._runtime(resource)
        if runtime is None:
            raise SessionAuthorityError("Reviewed session runtime is not connected")
        session_id = "ses_" + secrets.token_hex(16)
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
        with self.lock:
            for key, value in list(self.tickets.items()):
                if value[0] <= now:
                    self._release(value[4])
                    del self.tickets[key]
            # Bounded fail-closed ledger, never evict request IDs to make retries
            # look fresh. Restart is not a durable idempotency/receipt boundary.
            if (
                identity in self.spent
                or len(self.spent) >= 1024
                or len(self.leases) >= 64
                or (installation_id, binding_id) in self.reservations
            ):
                raise SessionAuthorityError(
                    "Session request already used or capacity unavailable"
                )
            self.spent.add(identity)
            self.leases.add(session_id)
            self.reservations[(installation_id, binding_id)] = session_id
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
            raise SessionAuthorityError("Session ticket is unavailable")
        if (
            item[0] <= self.clock()
            or item[1] != module_id
            or item[2].entrypoint_id != entrypoint_id
        ):
            with self.lock:
                self._release(item[4])
            raise SessionAuthorityError("Session ticket is unavailable")
        return item

    def _audit(self, admitted, module_id, outcome):
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

    async def serve(self, websocket, module_id, entrypoint_id):
        # No JWT/ticket in a URL, no absent/wildcard Origin fallback.
        if (
            websocket.headers.get("origin") not in self.origins
            or websocket.query_params
        ):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        owned = None
        admitted = None
        pump = reader = None
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
            session_id = admitted.session_id
            deadline = self.clock() + self.lifetime
            send_lock = asyncio.Lock()
            check_lock = asyncio.Lock()
            output_seq, input_seq = 0, 0

            async def check(operation="output", action=None):
                if self.clock() >= deadline or owned is not None and owned.closed:
                    raise SessionAuthorityError("Session expired")
                async with check_lock:
                    await asyncio.to_thread(
                        self._check_current,
                        module_id,
                        ui,
                        authorization,
                        admitted,
                        request,
                        operation,
                        action,
                    )

            async def send_json(value):
                async with send_lock:
                    await check()
                    await asyncio.wait_for(websocket.send_json(value), 10)

            async def send_output(data):
                nonlocal output_seq
                if (
                    type(data) is not bytes
                    or not 1 <= len(data) <= MAX_SESSION_PAYLOAD_BYTES
                ):
                    raise SessionAuthorityError("Session output exceeds bounds")
                async with send_lock:
                    await check()
                    output_seq += 1
                    frame = encode_session_frame(
                        op="data",
                        seq=output_seq,
                        session_id=session_id,
                        payload=data,
                        payload_kind="binary",
                    )
                    await asyncio.wait_for(websocket.send_bytes(frame), 10)

            async def send_frame(frame):
                _header, payload = decode_session_frame(frame)
                await send_output(payload)

            await check("status")
            owned = _OwnedProvider(runtime.provider, session_id)
            with self.lock:
                self.owned[session_id] = owned
            await asyncio.to_thread(self._audit, admitted, module_id, "start_requested")
            # Context is Core-owned, not the browser payload or a naked hello.
            await asyncio.wait_for(
                runtime.provider.open(
                    {
                        "session_id": session_id,
                        "device_id": request.device_id,
                        "capability_id": request.capability_id,
                        "access_mode": request.access_mode,
                        "options": request.options,
                    }
                ),
                10,
            )
            await check("status")
            created = datetime.now(UTC)
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
                            created + timedelta(seconds=self.lifetime)
                        ).isoformat(),
                    },
                }
            )
            pump = asyncio.create_task(
                pump_session_output(owned, session_id, send_frame, authorize=check)
            )
            controls = set()
            while True:
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
                    await check("input")
                    input_seq = header.seq
                    output = await asyncio.wait_for(
                        runtime.provider.receive(session_id, payload), 10
                    )
                    await check("input")
                    if type(output) is not bytes:
                        raise SessionAuthorityError(
                            "Session provider response is invalid"
                        )
                    if output:
                        await send_output(output)
                    await send_json(
                        {"op": "input_ack", "session_id": session_id, "seq": input_seq}
                    )
                else:
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
                    try:
                        await asyncio.to_thread(
                            self._audit,
                            admitted,
                            module_id,
                            "cleanup_unconfirmed" if owned.failed else "closed",
                        )
                    except Exception:
                        owned.failed = True  # Audit outcome must not disappear, either.
                    if not owned.failed:
                        with self.lock:
                            self.owned.pop(owned.session_id, None)
                            self._release(admitted)
                elif admitted is not None:
                    with self.lock:
                        self._release(admitted)

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
