"""Signed local platform socket used by network-isolated application services."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import socket
import threading
import secrets

from backend.services.local_socket import prepare_socket_path, socket_identity, unlink_owned_socket
import time

try:
    import grp
except ImportError:  # pragma: no cover - Windows development host
    grp = None

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from three_mm_runtime.application_transport import ApplicationTransportError

from backend.db.module import ApplicationExtensionInstallation
from backend.services.operation_diagnostics import core_diagnostics
from three_mm_protocol.diagnostics import DiagnosticSession, DiagnosticSpan


from three_mm_protocol.platform_transport import (
    MAX_MESSAGE_BYTES as MAX_PLATFORM_MESSAGE_BYTES, MAX_CONNECTIONS,
    READ_TIMEOUT_SECONDS, REQUEST_TIMEOUT_SECONDS, MAX_CLOCK_SKEW_SECONDS, MAX_RECENT_REQUESTS,
    DISCOVERY_ACTION, SCOPED_ACTIONS, COMPATIBILITY_ACTIONS, ENVELOPE_FIELDS,
    PlatformDiscoveryV1, canonical, read_frame, remaining,
)
INSTANCE_PATTERN = re.compile(r"^[0-9a-f]{24}$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,95}$")


from three_mm_platform_wire import (
    RUNTIME_ACTIONS, AUTHORITY_CONNECTIONS, AUTHORITY_MAX_BYTES,
    AUTHORITY_READ_SECONDS, AUTHORITY_CONTRACT, peer_identity, process_generation,
    receive_authority_frame,
)


class ApplicationPlatformServer:
    def __init__(self, socket_path: Path, key_root: Path, group: str = "3mm-app", *,
                 diagnostics: DiagnosticSession | None = None,
                 allowed_actions=RUNTIME_ACTIONS, max_connections=MAX_CONNECTIONS, runtime_root=None) -> None:
        self.socket_path = socket_path
        self.key_root = key_root
        self.runtime_root = runtime_root
        if runtime_root is None and socket_path is not None and socket_path.name == "platform.sock" and socket_path.parent.name == "platform":
            self.runtime_root = socket_path.parent.parent
        self.group = group
        self.allowed_actions = frozenset(allowed_actions)
        self.max_connections = max_connections
        self._origin = threading.local()
        self.diagnostics = diagnostics if diagnostics is not None else core_diagnostics
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._server: socket.socket | None = None
        self._socket_identity = None
        self._connections: set[socket.socket] = set()
        self._handlers: set[threading.Thread] = set()
        self._handlers_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(self.max_connections)
        self._generation: str | None = None
        self._recent: dict[tuple[str, str], float] = {}
        self._recent_lock = threading.Lock()

    _canonical = staticmethod(canonical)

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    @property
    def active_connections(self) -> int:
        with self._handlers_lock:
            return len(self._connections)

    def start(self) -> None:
        with self._handlers_lock:
            if self._server is not None or self._handlers:
                raise RuntimeError("Local listener has already been started or has unfinished work")
        self._stop.clear()
        self._generation = secrets.token_hex(16)
        self._recent.clear()
        self.socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        prepare_socket_path(self.socket_path)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server = server
        try:
            server.bind(str(self.socket_path))
            self._socket_identity = socket_identity(self.socket_path)
            os.chmod(self.socket_path, 0o660)
            if grp is not None:
                try:
                    os.chown(self.socket_path, -1, grp.getgrnam(self.group).gr_gid)
                except (KeyError, PermissionError):
                    pass
            server.listen(self.max_connections)
            server.settimeout(0.2)
            self._thread = threading.Thread(target=self._run, name="3mm-application-platform", daemon=True)
            self._thread.start()
        except BaseException:
            self.stop()
            raise

    def stop(self) -> None:
        self._stop.set()
        if self._server is not None:
            self._server.close()
        deadline = time.monotonic() + 5
        if self._thread is not None and self._thread.ident is not None:
            self._thread.join(timeout=max(0, deadline - time.monotonic()))
        with self._handlers_lock:
            connections, handlers = list(self._connections), list(self._handlers)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        for handler in handlers:
            handler.join(timeout=max(0, deadline - time.monotonic()))
        running = bool(self._thread and self._thread.is_alive()) or any(h.is_alive() for h in handlers)
        self._thread = None
        self._server = None
        unlink_owned_socket(self.socket_path, self._socket_identity)
        self._socket_identity = None
        if running:
            # Python cannot kill an adapter blocked in native work. Keep its slot
            # occupied and refuse an in-process restart until it actually exits.
            raise TimeoutError("Local listener has unfinished work")

    def _run(self) -> None:
        server = self._server
        while not self._stop.is_set():
            try:
                connection, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                return  # A broken listener must become visibly unavailable, not spin.
            if not self._slots.acquire(blocking=False):
                connection.close()  # No authenticated identity: no unsigned busy reply.
                continue
            handler = None
            try:
                handler = threading.Thread(target=self._serve, args=(connection,),
                                           name="3mm-application-platform-request", daemon=True)
                with self._handlers_lock:
                    self._connections.add(connection)
                    self._handlers.add(handler)
                handler.start()
            except Exception:
                with self._handlers_lock:
                    self._connections.discard(connection)
                    self._handlers.discard(handler)
                connection.close()
                self._slots.release()

    def _serve(self, connection):
        try:
            if not self._stop.is_set():
                self._handle(connection)
        finally:
            connection.close()
            with self._handlers_lock:
                self._connections.discard(connection)
                self._handlers.discard(threading.current_thread())
            self._slots.release()

    def _read(self, connection: socket.socket, deadline=None) -> dict[str, object]:
        return read_frame(connection, deadline if deadline is not None else time.monotonic() + READ_TIMEOUT_SECONDS)

    def _handle(self, connection: socket.socket, *, decoded_request=None, origin=None) -> None:
        from backend.database import SessionLocal

        request_id = "invalid"
        secret: bytes | None = None
        trace = None
        reason = "request_invalid"
        deadline = time.monotonic() + REQUEST_TIMEOUT_SECONDS
        with connection:
            try:
                request = (self._read(connection, min(deadline, time.monotonic() + READ_TIMEOUT_SECONDS))
                           if decoded_request is None else decoded_request)
                if (not ENVELOPE_FIELDS <= request.keys()
                        or type(request.get("version")) is not int or request["version"] != 1
                        or type(request.get("timestamp")) is not int
                        or not isinstance(request.get("request_id"), str)
                        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", request["request_id"]) is None
                        or not isinstance(request.get("action"), str)):
                    raise ValueError("Platform request fields are invalid")
                request_id = request["request_id"]
                instance_id = request.get("instance_id")
                if not isinstance(instance_id, str) or not INSTANCE_PATTERN.fullmatch(instance_id):
                    raise ValueError("Platform instance identity is invalid")
                reason = "authentication_failed"
                candidate = (self.key_root / f"{instance_id}.key").read_bytes()
                if len(candidate) != 32:
                    raise ValueError("Platform transport key is invalid")
                signature = request.get("signature")
                expected = hmac.new(candidate, self._canonical(request), hashlib.sha256).hexdigest()
                if (not isinstance(signature, str) or not hmac.compare_digest(signature, expected)
                        or abs(int(time.time()) - request["timestamp"]) > MAX_CLOCK_SKEW_SECONDS):
                    raise ValueError("Platform request authentication failed")
                secret = candidate
                with self._recent_lock:
                    now = time.monotonic()
                    self._recent = {key: expiry for key, expiry in self._recent.items() if expiry > now}
                    key = (instance_id, request_id)
                    if key in self._recent:
                        reason = "request_replayed"
                        raise ValueError("Platform request was already admitted; execution may be unconfirmed")
                    if len(self._recent) >= MAX_RECENT_REQUESTS:
                        reason = "overloaded"
                        raise ValueError("Platform request capacity is exhausted")
                    self._recent[key] = now + 2 * MAX_CLOCK_SKEW_SECONDS
                if request["action"] in self.allowed_actions:
                    trace = DiagnosticSpan(self.diagnostics, request_id, "core.request",
                        operation=request["action"], instance_id=instance_id)
                reason = "installation_unavailable"
                db = SessionLocal()
                try:
                    installation = db.scalar(select(ApplicationExtensionInstallation).where(
                        ApplicationExtensionInstallation.instance_id == instance_id))
                    if installation is None or (request['action'] not in {
                            'command.lookup', 'task.lookup', 'task.cancel', 'task.schedule.lookup', 'task.schedule.cancel',
                            'event.publish', 'files.execute', 'files.status', 'relational.complete', 'relational.status'}
                            and (not installation.enabled or installation.status != 'active')):
                        raise ValueError("Application installation is not active")
                    if request["action"] not in self.allowed_actions:
                        reason = "operation_unsupported"
                        raise ValueError("Platform action is unsupported")
                    remaining(deadline)
                    reason = "operation_denied"
                    if request["action"] == "relational.boot.startup":
                        if not hasattr(socket, "SO_PEERCRED"):
                            raise ValueError("Boot startup peer unavailable")
                        peer = peer_identity(origin if origin is not None else connection)
                        result = self._dispatch(db, installation, request, transport_secret=secret, peer_credentials=peer)
                    else:
                        result = self._dispatch(db, installation, request, transport_secret=secret)
                finally:
                    db.close()
                from backend.services.application_connector_transport import ConnectorDispatch
                if isinstance(result, ConnectorDispatch):
                    from three_mm_platform_wire import send_authority_frame
                    try:
                        connection.settimeout(1)
                        send_authority_frame(connection, {"connector_execution_contract": 1,
                            "receipt": result.receipt, "timeout_seconds": result.timeout}, origin=result.connection)
                    finally: result.connection.close()
                    return
                remaining(deadline)
                response: dict[str, object] = {"ok": True, "result": result}
            except Exception as exc:
                if secret is None:
                    return  # Unauthenticated peers receive neither details nor signed errors.
                if isinstance(exc, TimeoutError):
                    reason, message = "deadline_exceeded", "Platform deadline exceeded; execution may be unconfirmed"
                elif isinstance(exc, ValueError):
                    message = str(exc)[:500]
                else:
                    reason, message = "operation_failed", "Platform operation failed"
                response = {"ok": False, "reason": reason, "error": message}
            signed: dict[str, object] = {"version": 1, "request_id": request_id,
                "timestamp": int(time.time()), **response}
            try:
                signed["signature"] = hmac.new(secret, self._canonical(signed), hashlib.sha256).hexdigest()
                encoded = json.dumps(signed, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
                if len(encoded) > MAX_PLATFORM_MESSAGE_BYTES:
                    raise ValueError("Platform response is too large")
            except (ValueError, TypeError, RecursionError):
                reason = "response_too_large"
                signed = {"version": 1, "request_id": request_id, "timestamp": int(time.time()),
                          "ok": False, "reason": reason, "error": "Platform response is invalid or too large; execution may be unconfirmed"}
                signed["signature"] = hmac.new(secret, self._canonical(signed), hashlib.sha256).hexdigest()
                encoded = json.dumps(signed, separators=(",", ":")).encode("utf-8") + b"\n"
                response = signed
            try:
                connection.settimeout(max(0.001, min(1, deadline - time.monotonic())))
                self._send_encoded(connection, encoded)
            except OSError:
                if trace is not None:
                    trace.end("error", "transport_unavailable")
            else:
                if trace is not None:
                    trace.end("ok" if response["ok"] else "denied" if reason in {"operation_denied", "installation_unavailable"} else "error",
                              "ok" if response["ok"] else reason)

    def _send_encoded(self, connection, encoded):
        connection.sendall(encoded)

    def _dispatch(self, db, installation, request: dict[str, object], *, transport_secret=None, peer_credentials=None) -> dict[str, object]:
        action = request.get("action")
        if action not in self.allowed_actions:
            raise ValueError("Platform action requires its current Runtime transport")
        mode = db.scalar(select(ApplicationExtensionInstallation.authority_mode).where(
            ApplicationExtensionInstallation.id == installation.id))
        if action == DISCOVERY_ACTION:
            if set(request) == ENVELOPE_FIELDS | {'resource_scopes'}:
                from backend.services.application_resource_discovery import discover_resources
                from three_mm_protocol.application_resources import ResourceDiscoveryRequestV1
                query = ResourceDiscoveryRequestV1(scopes=request['resource_scopes'])
                engine = db.get_bind().engine; identifier = installation.id; instance = installation.instance_id
                if db.new or db.dirty or db.deleted: raise ValueError('Resource observation requires a clean transaction')
                db.rollback()
                return discover_resources(engine, identifier, instance, query.scopes, transport_secret=transport_secret)
            if set(request) != ENVELOPE_FIELDS:
                raise ValueError("Platform discovery fields are invalid")
            from backend.services.authority_metadata import read_authority_guard, read_application_authority
            guard = read_authority_guard(db)
            current = read_application_authority(db, installation.id)
            return PlatformDiscoveryV1(
                instance_id=installation.instance_id, transport_generation=getattr(self._origin, "generation", self._generation),
                recovery_generation=guard.generation, authority_revision=guard.revision,
                application_incarnation=current.incarnation, authority_epoch=current.epoch,
                authority_mode=current.mode,
                operations=sorted(self.allowed_actions & (COMPATIBILITY_ACTIONS if current.mode == "compatibility" else SCOPED_ACTIONS)),
            ).model_dump(mode="json")
        if mode != 'compatibility' and action not in SCOPED_ACTIONS:
            raise ValueError('Platform action has no supported resource grant')
        if action in {"delegation.execute", "delegation.lookup"}:
            from backend.services.application_delegations import execute_delegation, inspect_delegation
            from backend.config import get_settings
            if mode != "enforced" or set(request) != ENVELOPE_FIELDS | {"delegation_id"}:
                raise ValueError("Delegation requires current scoped service authority")
            identifier = installation.id
            engine = db.get_bind().engine
            db.rollback()
            from fastapi import HTTPException
            try:
                if action == "delegation.lookup":
                    return inspect_delegation(engine, identifier, request["delegation_id"])
                return execute_delegation(engine, identifier, request["delegation_id"],
                    transport_secret=transport_secret, settings=get_settings().applications)
            except HTTPException:
                raise ValueError("Delegation is unavailable for the current actor") from None
        if action in {"task.submit", "task.lookup", "task.cancel", "task.start", "task.progress"}:
            from backend.services.application_tasks import submit_task, lookup_task, cancel_task, start_task, progress_task
            field = {"task.submit": "task", "task.lookup": "lookup", "task.cancel": "lookup", "task.start": "execution", "task.progress": "progress"}[action]
            if set(request) != ENVELOPE_FIELDS | {field}:
                raise ValueError("Task transport fields are invalid")
            handler = {"task.submit": submit_task, "task.lookup": lookup_task, "task.cancel": cancel_task, "task.start": start_task, "task.progress": progress_task}[action]
            return handler(db, installation, request[field])
        if action in {"task.schedule.create", "task.schedule.lookup", "task.schedule.cancel"}:
            from backend.services.application_task_schedules import create_schedule, lookup_schedule, cancel_schedule
            field = "schedule" if action == "task.schedule.create" else "lookup"
            if set(request) != ENVELOPE_FIELDS | {field}:
                raise ValueError("Schedule transport fields are invalid")
            handler = {"task.schedule.create": create_schedule, "task.schedule.lookup": lookup_schedule,
                "task.schedule.cancel": cancel_schedule}[action]
            return handler(db, installation, request[field])
        if action == 'installation.peers.read':
            from backend.services.application_peer_read import read_application_peer
            return read_application_peer(db, installation, request)
        if mode != 'compatibility' and action == 'installation.identity.get':
            from backend.services.application_identity_read import read_application_identity
            return read_application_identity(db, installation, request, diagnostics=self.diagnostics)
        if mode != 'compatibility' and action == 'installation.status.get':
            from backend.services.application_status_read import read_application_status
            return read_application_status(db, installation, request)
        if action == "relational.boot.startup":
            from backend.services.application_relational_startup import admit_boot_startup

            if (set(request) != {"version", "request_id", "timestamp", "instance_id", "action", "signature", "runtime_nonce"}
                    or type(request.get("version")) is not int or request["version"] != 1
                    or len(json.dumps(request, allow_nan=False).encode("utf-8")) > 8192
                    or self.runtime_root is None or not self.runtime_root.is_absolute()):
                raise ValueError("Boot startup metadata is invalid")
            return admit_boot_startup(db, installation.id, request["runtime_nonce"], transport_secret=transport_secret,
                runtime_root=self.runtime_root, peer_credentials=peer_credentials)
        if action in {'relational.admit', 'relational.complete', 'relational.status'}:
            from backend.services.application_relational import (
                admit_host_transaction,
                record_host_commit,
                transaction_status,
            )
            from three_mm_runtime.application_relational_session import MAX_METADATA_BYTES

            fields = {
                "version", "request_id", "timestamp", "instance_id", "action",
                "signature",
            }
            fields |= {
                "relational.admit": {"transaction_id", "mode"},
                "relational.complete": {"receipt"},
                "relational.status": {"transaction_id"},
            }[action]
            if (
                type(transport_secret) is not bytes
                or len(transport_secret) != 32
                or set(request) != fields
                or type(request.get("version")) is not int
                or request["version"] != 1
                or len(json.dumps(request, allow_nan=False).encode("utf-8"))
                > MAX_METADATA_BYTES
            ):
                raise ValueError("Relational transport metadata is invalid")
            identifier = installation.id  # Freeze before resolver rollback/IPC.
            if action == "relational.admit":
                return admit_host_transaction(
                    db, identifier, request["transaction_id"], request["mode"],
                    transport_secret=transport_secret,
                )
            if action == "relational.complete":
                return record_host_commit(
                    db, identifier, request["receipt"],
                    transport_secret=transport_secret,
                )
            return transaction_status(db, identifier, request["transaction_id"])
        if action in {'files.execute', 'files.status'}:
            from backend.services.application_files import execute_private_file, file_operation_status
            if type(transport_secret) is not bytes or len(transport_secret) != 32:
                raise ValueError('Private files require authenticated instance transport')
            if action == 'files.status':
                return file_operation_status(db, installation, request.get('file_request_id'))
            return execute_private_file(db, installation, request.get('file_request'), transport_secret=transport_secret)
        if action == 'event.publish':
            from backend.services.application_event_publication import publish_application_event
            return publish_application_event(db, installation, request.get('publication'))
        if action in {"installation.peers.enroll", "installation.peers.list", "installation.peers.capabilities", "installation.peers.approve", "installation.peers.revoke", "installation.peers.rotate", "installation.peers.report", "installation.status.get"}:
            from backend.services import installation_peers as peers
            from backend.services.installation_projection import installation_projection
            permissions = {
                "installation.peers.enroll": "installation.peers.enroll",
                "installation.peers.rotate": "installation.peers.enroll",
                "installation.peers.approve": "installation.peers.receive",
                "installation.peers.report": "installation.peers.report",
                "installation.status.get": "installation.status.read",
            }
            _, _, definition = peers._application(db, installation.module_id)
            if action in {"installation.peers.list", "installation.peers.capabilities"}:
                if not {"installation.peers.receive", "installation.peers.enroll"} & set(definition.platform_permissions):
                    raise ValueError("Installation peer permissions are not declared")
                if action == "installation.peers.capabilities":
                    if definition.service.sdk_version != "1.3":
                        raise ValueError("Peer approval binding capabilities require SDK 1.3")
                    return peers.peer_capabilities()
                return peers.list_peers(db, installation)
            if action == "installation.peers.revoke":
                permission = "installation.peers.receive" if request.get("direction") == "inbound" else "installation.peers.enroll"
            else:
                permission = permissions[action]
            if permission not in definition.platform_permissions:
                raise ValueError("Installation peer permission is not declared")
            if action == "installation.peers.enroll":
                return peers.enroll_outbound(db, installation, str(request.get("link_id", "")))
            if action == "installation.peers.rotate":
                return peers.rotate_outbound(db, installation, str(request.get("link_id", "")))
            if action == "installation.peers.approve":
                return peers.approve_inbound(
                    db, installation, str(request.get("binding_id", "")), request.get("expected_generation"),
                    expected_metadata_revision=request.get("expected_metadata_revision"),
                    expected_metadata_hash=request.get("expected_metadata_hash"),
                )
            if action == "installation.peers.revoke":
                return peers.revoke_peer(db, installation, str(request.get("peer_id", "")), request.get("direction"))
            if action == "installation.peers.report":
                return peers.report_outbound(db, installation, str(request.get("link_id", "")), str(request.get("report_id", "")))
            projection = installation_projection(db, installation, str(request.get("link_id", "")))
            db.commit()
            return projection.model_dump(mode="json")
        if action in {"installation.identity.get", "installation.identity.prove"}:
            from backend.db.module import ModulePackage
            from backend.services.application_extensions import load_application_definition
            from backend.services.installation_identity import installation_identity, prove_installation_identity

            if not installation.enabled or installation.status != "active":
                raise ValueError("Application installation is not active")
            package = db.get(ModulePackage, installation.module_package_id)
            if package is None:
                raise ValueError("Application package is unavailable")
            definition = load_application_definition(package)
            permission = (
                "installation.identity.read" if action == "installation.identity.get"
                else "installation.identity.prove"
            )
            if permission not in definition.platform_permissions:
                raise ValueError("Installation identity permission is not declared")
            if action == "installation.identity.prove" and definition.peer_bindings:
                raise ValueError("Peer bindings do not authorize generic identity proofs")
            if action == "installation.identity.get":
                return installation_identity(db).model_dump(mode="json")
            return prove_installation_identity(db, request.get("proof_request")).model_dump(mode="json")
        if action == 'command.discover':
            from backend.services.application_command_discovery import discover_selected_command
            from three_mm_protocol.application_command_discovery import CommandDiscoveryRequestV1
            if set(request) != ENVELOPE_FIELDS | {'binding_id'}:
                raise ValueError('Command discovery fields are invalid')
            query = CommandDiscoveryRequestV1(binding_id=request['binding_id'])
            return discover_selected_command(db.get_bind().engine, installation.id,
                request['instance_id'], query.binding_id)
        if action == 'command.lookup':
            from backend.services.application_commands import command_lookup
            return command_lookup(db, installation, request.get('lookup'))
        if action in {'command.submit', 'command.status'}:
            from backend.services.application_commands import submit_command, command_status
            if action == 'command.submit':
                if set(request) not in (ENVELOPE_FIELDS | {'command'}, ENVELOPE_FIELDS | {'command', 'task_execution'}):
                    raise ValueError('Command transport fields are invalid')
                return submit_command(db, installation, request.get('command'), task_execution=request.get('task_execution'))
            return command_status(db, installation, str(request.get('command_id', '')))
        if action == "connector.request":
            from backend.services.application_connector_transport import begin_connector
            if not hasattr(self, "connector_worker_path"):
                raise ValueError("Connector worker is unavailable")
            return begin_connector(db, installation, request, secret=transport_secret,
                runtime_generation=getattr(self._origin, "generation", None),
                worker_path=self.connector_worker_path, worker_uid=self.connector_worker_uid)
        if action in {'checkpoint.get', 'checkpoint.put'}:
            from backend.services.application_checkpoints import execute_checkpoint
            return execute_checkpoint(db, installation, request)
        raise ValueError("Platform action is unsupported")


class CoreRuntimeAuthorityServer(ApplicationPlatformServer):
    """Private current-admission gate for one dedicated Runtime OS principal."""
    def __init__(self, socket_path, key_root, *, runtime_uid, group="3mm-platform", diagnostics=None, runtime_root=None, connector_worker_path=None, connector_worker_uid=None):
        if type(runtime_uid) is not int or runtime_uid <= 0:
            raise ValueError("Runtime must have an explicit non-root OS identity")
        super().__init__(socket_path, key_root, group=group, diagnostics=diagnostics,
                         allowed_actions=RUNTIME_ACTIONS, max_connections=AUTHORITY_CONNECTIONS, runtime_root=runtime_root)
        self.runtime_uid = runtime_uid
        self.connector_worker_path = connector_worker_path
        self.connector_worker_uid = connector_worker_uid

    def _send_encoded(self, connection, encoded):
        if getattr(self._origin, "connector", False): connection.sendall(b"\0")
        connection.sendall(encoded)

    def _dispatch(self, db, installation, request, *, transport_secret=None, peer_credentials=None):
        if request.get("action")=="installation.identity.get":
            # This extracted boundary is the initialized public scoped read.
            # Compatibility is never authority to initialize/sign a Core identity.
            from backend.services.application_identity_read import read_application_identity
            return read_application_identity(db,installation,request,diagnostics=self.diagnostics)
        return super()._dispatch(db,installation,request,transport_secret=transport_secret,
                                 peer_credentials=peer_credentials)

    def _handle(self, connection):
        origin = None
        try:
            pid, uid, gid = peer_identity(connection)
            if uid != self.runtime_uid:
                return
            self._origin.generation = process_generation(pid, uid)
            request, origin = receive_authority_frame(connection, time.monotonic() + AUTHORITY_READ_SECONDS)
            if (origin is not None) != (request.get("action") == "relational.boot.startup"):
                return
            self._origin.connector = request.get("action") == "connector.request"
            if ({"authority_probe", "authority_contract"} <= set(request)
                    and set(request) <= {"authority_probe", "authority_contract", "public_web_contract", "event_delivery_contract", "connector_execution_contract", "application_response_contract"}):
                nonce = request["authority_probe"]
                if (request["authority_contract"] != AUTHORITY_CONTRACT
                        or type(request["authority_contract"]) is not int
                        or not isinstance(nonce,str) or re.fullmatch(r"[0-9a-f]{32}",nonce) is None):
                    return
                result = {"authority_contract":AUTHORITY_CONTRACT,"authority_probe":nonce}
                for feature in ("public_web_contract", "event_delivery_contract", "connector_execution_contract", "application_response_contract"):
                    if feature in request:
                        if type(request[feature]) is not int or request[feature]!=1:return
                        result[feature]=1
                connection.settimeout(AUTHORITY_READ_SECONDS)
                connection.sendall(json.dumps(result,separators=(",", ":")).encode()+b"\n")
                return
            if "task_execution_contract" in request:
                if type(request["task_execution_contract"]) is not int or request["task_execution_contract"] != 1:
                    return
                from backend.database import SessionLocal
                from backend.config import get_settings
                from backend.services.application_tasks import claim_task, dispatch_task, finish_task
                with SessionLocal() as task_db:
                    task_engine = task_db.get_bind().engine
                if set(request) == {"task_execution_contract", "action"} and request["action"] == "claim":
                    result = claim_task(task_engine,
                        settings=get_settings().applications.model_copy(update={"key_root": self.key_root}),
                        worker_generation=self._origin.generation)
                elif set(request) == {"task_execution_contract", "action"} and request["action"] == "schedule.poll":
                    from backend.services.application_task_schedules import poll_schedules
                    result = poll_schedules(task_engine)
                elif (set(request) == {"task_execution_contract", "action", "schedule_id", "request_hash", "due_at"}
                        and request["action"] == "schedule.tick"
                        and isinstance(request["schedule_id"], str) and re.fullmatch(r"schedule_[0-9a-f]{32}", request["schedule_id"])
                        and isinstance(request["request_hash"], str) and re.fullmatch(r"[0-9a-f]{64}", request["request_hash"])
                        and isinstance(request["due_at"], str) and len(request["due_at"]) <= 64):
                    from backend.services.application_task_schedules import tick_schedule
                    result = tick_schedule(task_engine, schedule_id=request["schedule_id"],
                        request_hash=request["request_hash"], due_at=request["due_at"])
                elif (set(request) == {"task_execution_contract", "action", "task_run_id", "lease_token", "response"}
                        and request["action"] == "dispatch"
                        and isinstance(request["task_run_id"], str) and re.fullmatch(r"task_[0-9a-f]{32}", request["task_run_id"])
                        and isinstance(request["lease_token"], str) and re.fullmatch(r"[0-9a-f]{64}", request["lease_token"])):
                    result = dispatch_task(task_engine,
                        settings=get_settings().applications.model_copy(update={"key_root": self.key_root}),
                        worker_generation=self._origin.generation, task_run_id=request["task_run_id"],
                        lease_token=request["lease_token"], response=request["response"])
                elif (set(request) in ({"task_execution_contract", "action", "task_run_id", "lease_token", "response"},
                        {"task_execution_contract", "action", "task_run_id", "lease_token", "failure"})
                        and request["action"] == "complete"
                        and isinstance(request["task_run_id"], str) and re.fullmatch(r"task_[0-9a-f]{32}", request["task_run_id"])
                        and isinstance(request["lease_token"], str) and re.fullmatch(r"[0-9a-f]{64}", request["lease_token"])
                        and request.get("failure", "execution_unconfirmed") == "execution_unconfirmed"):
                    result = finish_task(task_engine, key_root=self.key_root,
                        worker_generation=self._origin.generation, task_run_id=request["task_run_id"],
                        lease_token=request["lease_token"], response=request.get("response"))
                else:
                    return
                connection.settimeout(1)
                connection.sendall(json.dumps({"task_execution_contract": 1, "task": result}, separators=(",", ":")).encode() + b"\n")
                return
            if "connector_execution_contract" in request:
                if (type(request["connector_execution_contract"]) is not int or request["connector_execution_contract"] != 1
                        or set(request) not in ({"connector_execution_contract", "receipt", "response"},
                            {"connector_execution_contract", "receipt", "failure"})): return
                from backend.database import SessionLocal
                from backend.services.application_connector_transport import finish_connector
                with SessionLocal() as db:
                    result = finish_connector(db, request["receipt"], request.get("response"),
                        key_root=self.key_root, runtime_generation=self._origin.generation,
                        failure_category=request.get("failure"))
                connection.settimeout(1)
                connection.sendall(json.dumps(result,separators=(",", ":")).encode()+b"\n")
                return
            if "public_web_contract" in request:
                if type(request["public_web_contract"]) is not int or request["public_web_contract"] != 1:
                    return
                from backend.services.application_public_web_transport import handle_public_http
                handle_public_http(connection, request, key_root=self.key_root,
                    core_generation=self._generation, runtime_generation=self._origin.generation)
                return
            if "event_delivery_contract" in request:
                if type(request["event_delivery_contract"]) is not int or request["event_delivery_contract"]!=1:return
                from backend.services.application_events import handle_event_delivery
                handle_event_delivery(connection,request,key_root=self.key_root,
                                      runtime_generation=self._origin.generation)
                return
            # No caller-chosen origins/generations or peer credentials are forwarded.
            if not isinstance(request.get("action"), str) or request["action"] not in RUNTIME_ACTIONS:
                return
            super()._handle(connection, decoded_request=request, origin=origin)
        except (OSError,ValueError,TypeError,KeyError,IndexError,SQLAlchemyError,ApplicationTransportError):
            return
        finally:
            if origin is not None:
                origin.close()
            if hasattr(self._origin,"generation"): del self._origin.generation
            if hasattr(self._origin,"connector"): del self._origin.connector
            connection.close()
