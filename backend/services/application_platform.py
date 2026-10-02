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
import time

try:
    import grp
except ImportError:  # pragma: no cover - Windows development host
    grp = None

from sqlalchemy import select

from backend.db.module import (
    ApplicationExtensionInstallation,
    ApplicationSyncCheckpoint,
)
from backend.services.application_connectors import execute_connector_request


MAX_PLATFORM_MESSAGE_BYTES = 6 * 1024 * 1024
INSTANCE_PATTERN = re.compile(r"^[0-9a-f]{24}$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,95}$")


class ApplicationPlatformServer:
    def __init__(self, socket_path: Path, key_root: Path, group: str = "3mm-app") -> None:
        self.socket_path = socket_path
        self.key_root = key_root
        self.group = group
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._server: socket.socket | None = None

    @staticmethod
    def _canonical(value: dict[str, object]) -> bytes:
        return json.dumps(
            {key: item for key, item in value.items() if key != "signature"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        self.socket_path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o660)
        if grp is not None:
            try:
                os.chown(self.socket_path, -1, grp.getgrnam(self.group).gr_gid)
            except (KeyError, PermissionError):
                pass
        server.listen(16)
        server.settimeout(1)
        self._server = server
        self._thread = threading.Thread(target=self._run, name="3mm-application-platform", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._server is not None:
            self._server.close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.socket_path.unlink(missing_ok=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _ = self._server.accept()  # type: ignore[union-attr]
            except (TimeoutError, OSError):
                continue
            threading.Thread(
                target=self._handle,
                args=(connection,),
                name="3mm-application-platform-request",
                daemon=True,
            ).start()

    def _read(self, connection: socket.socket) -> dict[str, object]:
        payload = b""
        while b"\n" not in payload and len(payload) <= MAX_PLATFORM_MESSAGE_BYTES:
            chunk = connection.recv(65536)
            if not chunk:
                break
            payload += chunk
        if b"\n" not in payload or len(payload) > MAX_PLATFORM_MESSAGE_BYTES:
            raise ValueError("Platform request is invalid")
        value = json.loads(payload.split(b"\n", 1)[0])
        if not isinstance(value, dict):
            raise ValueError("Platform request is invalid")
        return value

    def _handle(self, connection: socket.socket) -> None:
        from backend.database import SessionLocal

        request_id = "invalid"
        secret: bytes | None = None
        with connection:
            try:
                request = self._read(connection)
                request_id = str(request.get("request_id", "invalid"))
                instance_id = request.get("instance_id")
                if not isinstance(instance_id, str) or not INSTANCE_PATTERN.fullmatch(instance_id):
                    raise ValueError("Platform instance identity is invalid")
                secret = (self.key_root / f"{instance_id}.key").read_bytes()
                if len(secret) != 32:
                    raise ValueError("Platform transport key is invalid")
                signature = request.get("signature")
                expected = hmac.new(secret, self._canonical(request), hashlib.sha256).hexdigest()
                if (
                    request.get("version") != 1
                    or not isinstance(signature, str)
                    or not hmac.compare_digest(signature, expected)
                    or abs(int(time.time()) - int(request.get("timestamp", 0))) > 30
                ):
                    raise ValueError("Platform request authentication failed")
                db = SessionLocal()
                try:
                    installation = db.scalar(
                        select(ApplicationExtensionInstallation).where(
                            ApplicationExtensionInstallation.instance_id == instance_id,
                        )
                    )
                    if installation is None or (request.get('action') != 'command.lookup' and (
                        not installation.enabled or installation.status != 'active'
                    )):
                        raise ValueError("Application installation is not active")
                    result = self._dispatch(db, installation, request)
                finally:
                    db.close()
                response: dict[str, object] = {"ok": True, "result": result}
            except Exception as exc:
                response = {"ok": False, "error": str(exc)[:500]}
            if secret is None:
                return
            signed: dict[str, object] = {
                "version": 1,
                "request_id": request_id,
                "timestamp": int(time.time()),
                **response,
            }
            signed["signature"] = hmac.new(
                secret, self._canonical(signed), hashlib.sha256
            ).hexdigest()
            connection.sendall(json.dumps(signed, separators=(",", ":")).encode("utf-8") + b"\n")

    def _dispatch(self, db, installation, request: dict[str, object]) -> dict[str, object]:
        action = request.get("action")
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
            if action == "installation.identity.get":
                return installation_identity(db).model_dump(mode="json")
            return prove_installation_identity(db, request.get("proof_request")).model_dump(mode="json")
        if action == 'command.lookup':
            from backend.services.application_commands import command_lookup
            return command_lookup(db, installation, request.get('lookup'))
        if action in {'command.submit', 'command.status'}:
            from backend.services.application_commands import submit_command, command_status
            if action == 'command.submit':
                return submit_command(db, installation, request.get('command'))
            return command_status(db, installation, str(request.get('command_id', '')))
        if action == "connector.request":
            headers = request.get("headers")
            if not isinstance(headers, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in headers.items()
            ):
                raise ValueError("Connector headers are invalid")
            try:
                body = base64.b64decode(str(request.get("body_base64", "")), validate=True)
            except ValueError as exc:
                raise ValueError("Connector body is invalid") from exc
            return execute_connector_request(
                db,
                installation,
                connector_id=str(request.get("connector_id", "")),
                request_id=str(request.get("connector_request_id", "")),
                method=str(request.get("method", "")),
                path=str(request.get("path", "")),
                headers=headers,
                body=body,
                idempotency_key=(
                    request["idempotency_key"]
                    if isinstance(request.get("idempotency_key"), str)
                    else None
                ),
            )
        checkpoint_id = request.get("checkpoint_id")
        if not isinstance(checkpoint_id, str) or not IDENTIFIER_PATTERN.fullmatch(checkpoint_id):
            raise ValueError("Checkpoint identity is invalid")
        checkpoint = db.scalar(
            select(ApplicationSyncCheckpoint).where(
                ApplicationSyncCheckpoint.application_installation_id == installation.id,
                ApplicationSyncCheckpoint.checkpoint_id == checkpoint_id,
            )
        )
        if action == "checkpoint.get":
            return {
                "checkpoint_id": checkpoint_id,
                "revision": checkpoint.revision if checkpoint is not None else 0,
                "value": checkpoint.value if checkpoint is not None else {},
            }
        if action != "checkpoint.put":
            raise ValueError("Platform action is unsupported")
        expected_revision = request.get("expected_revision")
        value = request.get("value")
        if (
            not isinstance(expected_revision, int)
            or isinstance(expected_revision, bool)
            or expected_revision < 0
            or not isinstance(value, dict)
            or len(json.dumps(value)) > 256 * 1024
        ):
            raise ValueError("Checkpoint update is invalid")
        current_revision = checkpoint.revision if checkpoint is not None else 0
        if current_revision != expected_revision:
            raise ValueError("Checkpoint revision conflict")
        if checkpoint is None:
            checkpoint = ApplicationSyncCheckpoint(
                application_installation_id=installation.id,
                checkpoint_id=checkpoint_id,
                revision=0,
                value={},
            )
            db.add(checkpoint)
        checkpoint.revision = current_revision + 1
        checkpoint.value = value
        db.commit()
        return {
            "checkpoint_id": checkpoint_id,
            "revision": checkpoint.revision,
            "value": checkpoint.value,
        }
