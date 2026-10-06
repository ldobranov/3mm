"""Bounded local transport between the public HTTP runtime and Core."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socket
import threading
from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.config import ApplicationRuntimeSettings
from backend.services.application_public_web import (
    ApplicationPublicWebError,
    dispatch_public_http,
)


PUBLIC_WEB_TRANSPORT_VERSION = 1
PUBLIC_WEB_MESSAGE_BYTES = 1024 * 1024
_REQUEST_ID = re.compile(r"^[0-9a-f]{32}$")


class PublicWebGatewayServer:
    """Expose only public GET/HEAD dispatch over a local Unix socket."""

    def __init__(
        self,
        socket_path: Path,
        application_settings: ApplicationRuntimeSettings,
        *,
        session_factory: Callable[[], Session] | None = None,
        dispatcher=dispatch_public_http,
    ) -> None:
        self.socket_path = socket_path
        self.application_settings = application_settings
        self._session_factory = session_factory
        self._dispatcher = dispatcher
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._server: socket.socket | None = None

    def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.socket_path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        server.listen(32)
        server.settimeout(1)
        self._server = server
        self._thread = threading.Thread(
            target=self._run,
            name="3mm-public-web-gateway",
            daemon=True,
        )
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
                name="3mm-public-web-gateway-request",
                daemon=True,
            ).start()

    @staticmethod
    def _read(connection: socket.socket) -> dict[str, object]:
        payload = b""
        while b"\n" not in payload and len(payload) <= PUBLIC_WEB_MESSAGE_BYTES:
            chunk = connection.recv(65536)
            if not chunk:
                break
            payload += chunk
        if b"\n" not in payload or len(payload) > PUBLIC_WEB_MESSAGE_BYTES:
            raise ValueError("Public web gateway request is invalid")
        value = json.loads(payload.split(b"\n", 1)[0])
        if not isinstance(value, dict):
            raise ValueError("Public web gateway request is invalid")
        return value

    @staticmethod
    def _write(connection: socket.socket, value: dict[str, object]) -> None:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        if len(encoded) > PUBLIC_WEB_MESSAGE_BYTES:
            raise ValueError("Public web gateway response is too large")
        connection.sendall(encoded)

    def _new_session(self):
        if self._session_factory is not None:
            return self._session_factory()
        from backend.database import SessionLocal

        return SessionLocal()

    def _handle(self, connection: socket.socket) -> None:
        request_id = "invalid"
        with connection:
            try:
                request = self._read(connection)
                request_id = request.get("request_id")  # type: ignore[assignment]
                if (
                    request.get("version") != PUBLIC_WEB_TRANSPORT_VERSION
                    or not isinstance(request_id, str)
                    or not _REQUEST_ID.fullmatch(request_id)
                    or request.get("method") not in {"GET", "HEAD"}
                    or not isinstance(request.get("path"), str)
                    or not isinstance(request.get("query"), dict)
                    or not isinstance(request.get("headers"), dict)
                    or set(request) != {
                        "version",
                        "request_id",
                        "method",
                        "path",
                        "query",
                        "headers",
                    }
                ):
                    raise ValueError("Public web gateway request is invalid")
                query = request["query"]
                headers = request["headers"]
                if (
                    not all(
                        isinstance(key, str)
                        and isinstance(values, list)
                        and all(isinstance(value, str) for value in values)
                        for key, values in query.items()
                    )
                    or not all(
                        isinstance(key, str) and isinstance(value, str)
                        for key, value in headers.items()
                    )
                ):
                    raise ValueError("Public web gateway request is invalid")
                db = self._new_session()
                try:
                    response = self._dispatcher(
                        db,
                        self.application_settings,
                        method=request["method"],
                        path=request["path"],
                        query=query,
                        headers=headers,
                    )
                finally:
                    db.close()
                result = {
                    "version": PUBLIC_WEB_TRANSPORT_VERSION,
                    "request_id": request_id,
                    "ok": True,
                    "response": response.model_dump(mode="json", exclude_none=True),
                }
            except ApplicationPublicWebError as exc:
                result = {
                    "version": PUBLIC_WEB_TRANSPORT_VERSION,
                    "request_id": request_id,
                    "ok": False,
                    "status": exc.status_code,
                }
            except Exception:
                # This socket is a public read-only projection. Never expose
                # Core exception details through it.
                result = {
                    "version": PUBLIC_WEB_TRANSPORT_VERSION,
                    "request_id": request_id,
                    "ok": False,
                    "status": 503,
                }
            try:
                self._write(connection, result)
            except (OSError, ValueError):
                return
