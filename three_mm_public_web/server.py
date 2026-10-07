"""Minimal public HTTP adapter with no Core database or admin-session access."""

from __future__ import annotations

import argparse
import base64
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import socket
import time
from typing import Mapping
from urllib.parse import parse_qs, unquote_to_bytes, urlsplit
import uuid

from pydantic import ValidationError

from three_mm_protocol import ApplicationPublicHttpResponseV1


PUBLIC_WEB_TRANSPORT_VERSION = 1
PUBLIC_WEB_MESSAGE_BYTES = 1024 * 1024
_SAFE_REQUEST_HEADERS = (
    "accept",
    "accept-language",
    "if-none-match",
    "if-modified-since",
)
_BAD_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")


class PublicWebCoreError(RuntimeError):
    def __init__(self, status_code: int = 503) -> None:
        super().__init__("Public web Core gateway is unavailable")
        self.status_code = status_code if status_code in {400, 404, 405, 503} else 503


class PublicWebCoreClient:
    def __init__(self, socket_path: Path, timeout_seconds: float = 35) -> None:
        self.socket_path = socket_path
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _read(connection: socket.socket) -> dict[str, object]:
        payload = b""
        while b"\n" not in payload and len(payload) <= PUBLIC_WEB_MESSAGE_BYTES:
            chunk = connection.recv(65536)
            if not chunk:
                break
            payload += chunk
        if b"\n" not in payload or len(payload) > PUBLIC_WEB_MESSAGE_BYTES:
            raise PublicWebCoreError()
        try:
            value = json.loads(payload.split(b"\n", 1)[0])
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise PublicWebCoreError() from exc
        if not isinstance(value, dict):
            raise PublicWebCoreError()
        return value

    def request(
        self,
        *,
        method: str,
        path: str,
        query: Mapping[str, list[str]],
        headers: Mapping[str, str],
    ) -> ApplicationPublicHttpResponseV1:
        request_id = uuid.uuid4().hex
        request = {
            "version": PUBLIC_WEB_TRANSPORT_VERSION,
            "request_id": request_id,
            "method": method,
            "path": path,
            "query": dict(query),
            "headers": dict(headers),
        }
        encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > PUBLIC_WEB_MESSAGE_BYTES:
            raise PublicWebCoreError(400)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout_seconds)
                connection.connect(str(self.socket_path))
                connection.sendall(encoded)
                response = self._read(connection)
        except OSError as exc:
            raise PublicWebCoreError() from exc
        if (
            response.get("version") != PUBLIC_WEB_TRANSPORT_VERSION
            or response.get("request_id") != request_id
            or not isinstance(response.get("ok"), bool)
        ):
            raise PublicWebCoreError()
        if response["ok"] is False:
            status = response.get("status")
            raise PublicWebCoreError(status if isinstance(status, int) else 503)
        if set(response) != {"version", "request_id", "ok", "response"}:
            raise PublicWebCoreError()
        try:
            return ApplicationPublicHttpResponseV1.model_validate(response["response"])
        except ValidationError as exc:
            raise PublicWebCoreError() from exc


def _decode_path(raw_path: str) -> str:
    if not raw_path.startswith("/") or _BAD_PERCENT.search(raw_path):
        raise ValueError("invalid path")
    try:
        decoded = unquote_to_bytes(raw_path).decode("utf-8", errors="strict")
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("invalid path") from exc
    if any(ord(char) < 32 or char == "\x7f" for char in decoded):
        raise ValueError("invalid path")
    return decoded


def _query(raw_query: str) -> dict[str, list[str]]:
    try:
        parsed = parse_qs(
            raw_query,
            keep_blank_values=True,
            strict_parsing=False,
            max_num_fields=64,
            encoding="utf-8",
            errors="strict",
        )
    except (UnicodeError, ValueError) as exc:
        raise ValueError("invalid query") from exc
    return {str(key): [str(value) for value in values] for key, values in parsed.items()}


class PublicWebHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address,
        handler_class,
        *,
        client: PublicWebCoreClient,
        bind_and_activate: bool = True,
    ):
        self.client = client
        self.last_activity = time.monotonic()
        super().__init__(server_address, handler_class, bind_and_activate=bind_and_activate)

    def process_request(self, request, client_address):  # type: ignore[no-untyped-def]
        self.last_activity = time.monotonic()
        return super().process_request(request, client_address)


class PublicWebRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "3mm-Public-Web/1"
    sys_version = ""

    @property
    def public_server(self) -> PublicWebHTTPServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, format, *args):  # type: ignore[no-untyped-def]
        return

    def _request_headers(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for name in _SAFE_REQUEST_HEADERS:
            values = self.headers.get_all(name, failobj=[])
            if len(values) > 1:
                raise ValueError("duplicate public header")
            if values:
                result[name] = values[0]
        return result

    def _request(self) -> ApplicationPublicHttpResponseV1:
        content_length = self.headers.get("Content-Length")
        if content_length is not None:
            try:
                if int(content_length) != 0:
                    raise ValueError("GET/HEAD request bodies are not supported")
            except ValueError as exc:
                raise ValueError("invalid content length") from exc
        parts = urlsplit(self.path)
        return self.public_server.client.request(
            method=self.command,
            path=_decode_path(parts.path),
            query=_query(parts.query),
            headers=self._request_headers(),
        )

    @staticmethod
    def _body(response: ApplicationPublicHttpResponseV1) -> bytes:
        if response.body is not None:
            return response.body.encode("utf-8")
        if response.body_base64 is not None:
            return base64.b64decode(response.body_base64, validate=True)
        return b""

    def _write_response(self, response: ApplicationPublicHttpResponseV1) -> None:
        body = self._body(response)
        self.send_response(response.status)
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in response.headers.items():
            self.send_header(name, value)
        if response.location is not None:
            self.send_header("Location", response.location)
        if response.content_type is not None:
            self.send_header("Content-Type", response.content_type)
        if response.status not in {204, 304}:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD" and response.status not in {204, 304} and body:
            self.wfile.write(body)

    def _write_error(self, status: int) -> None:
        messages = {
            400: b"Bad Request\n",
            404: b"Not Found\n",
            405: b"Method Not Allowed\n",
            503: b"Service Unavailable\n",
        }
        status = status if status in messages else 503
        body = messages[status]
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if status == 405:
            self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _handle_public(self) -> None:
        try:
            response = self._request()
        except ValueError:
            self._write_error(400)
            return
        except PublicWebCoreError as exc:
            self._write_error(exc.status_code)
            return
        self._write_response(response)

    def do_GET(self) -> None:
        self._handle_public()

    def do_HEAD(self) -> None:
        self._handle_public()

    def do_POST(self) -> None:
        self._write_error(405)

    def do_PUT(self) -> None:
        self._write_error(405)

    def do_PATCH(self) -> None:
        self._write_error(405)

    def do_DELETE(self) -> None:
        self._write_error(405)

    def do_OPTIONS(self) -> None:
        self._write_error(405)


def create_server(
    core_socket: Path,
    host: str = "127.0.0.1",
    port: int = 8081,
    *,
    client: PublicWebCoreClient | None = None,
) -> PublicWebHTTPServer:
    return PublicWebHTTPServer(
        (host, port),
        PublicWebRequestHandler,
        client=client or PublicWebCoreClient(core_socket),
    )


def create_server_from_socket(
    core_socket: Path,
    listener: socket.socket,
) -> PublicWebHTTPServer:
    server = PublicWebHTTPServer(
        ("127.0.0.1", 0),
        PublicWebRequestHandler,
        client=PublicWebCoreClient(core_socket),
        bind_and_activate=False,
    )
    server.socket.close()
    server.socket = listener
    server.server_address = listener.getsockname()
    server.server_name = "localhost"
    server.server_port = int(server.server_address[1])
    return server


def inherited_systemd_socket() -> socket.socket:
    if (
        os.getenv("LISTEN_PID") != str(os.getpid())
        or os.getenv("LISTEN_FDS") != "1"
    ):
        raise RuntimeError("Exactly one systemd listener socket is required")
    return socket.socket(socket.AF_INET, socket.SOCK_STREAM, fileno=3)


def serve_until_idle(server: PublicWebHTTPServer, idle_seconds: int) -> None:
    if idle_seconds < 5 or idle_seconds > 3600:
        raise ValueError("Idle timeout must be between 5 and 3600 seconds")
    server.timeout = 1
    server.last_activity = time.monotonic()
    while time.monotonic() - server.last_activity < idle_seconds:
        server.handle_request()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-socket", type=Path, required=True)
    parser.add_argument("--systemd-socket", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--idle-seconds", type=int, default=60)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.systemd_socket:
        listener = inherited_systemd_socket()
        server = create_server_from_socket(arguments.core_socket, listener)
    else:
        server = create_server(arguments.core_socket, arguments.host, arguments.port)
    try:
        serve_until_idle(server, arguments.idle_seconds)
    finally:
        server.server_close()
    return 0
