"""Minimal public HTTP adapter with no Core database or admin-session access."""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import socket
import threading
import time
from typing import Mapping
from urllib.parse import parse_qs, unquote_to_bytes, urlsplit
import uuid

from pydantic import ValidationError

from three_mm_platform_wire import read_frame, remaining
from three_mm_protocol import ApplicationPublicHttpResponseV1
from three_mm_protocol.public_forms import (
    FORM_ID, FORM_REQUEST_ID, GUEST_COOKIE, GUEST_PROOF_FIELD, GUEST_TTL_SECONDS,
    MAX_FORM_BYTES, MAX_FORM_FIELDS, guest_cookie_name, public_form_origin_host,
)
from three_mm_protocol.public_webhooks import MAX_WEBHOOK_BYTES
from three_mm_public_web.webhook_pilot import PILOT_SECONDS, SIGNED_HEADERS, WebhookPilotClient, valid_signed_fields


PUBLIC_WEB_TRANSPORT_VERSION = 1
PUBLIC_WEB_MESSAGE_BYTES = 1024 * 1024
_SAFE_REQUEST_HEADERS = (
    "accept",
    "accept-language",
    "if-none-match",
    "if-modified-since",
)
_BAD_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
FORM_BODY_SECONDS = 3
FORM_CONCURRENT = 4
FORM_WINDOW_SECONDS = 60
FORM_PER_SOURCE = 12
FORM_PER_WINDOW = 120


class PublicWebRuntimeError(RuntimeError):
    def __init__(self, status_code: int = 503) -> None:
        super().__init__("Public web Runtime gateway is unavailable")
        self.status_code = status_code if status_code in {400, 403, 404, 405, 503} else 503


@dataclass(frozen=True, slots=True)
class GuestPage:
    response: ApplicationPublicHttpResponseV1
    path: str
    cookie: str = field(repr=False)


class PublicWebRuntimeClient:
    def __init__(self, socket_path: Path, timeout_seconds: float = 35) -> None:
        self.socket_path = socket_path
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        *,
        method: str,
        path: str,
        query: Mapping[str, list[str]],
        headers: Mapping[str, str],
        form: Mapping[str, str] | None = None,
        guest: dict[str, str | None] | None = None,
    ) -> ApplicationPublicHttpResponseV1 | GuestPage:
        request_id = uuid.uuid4().hex
        request = {
            "version": PUBLIC_WEB_TRANSPORT_VERSION,
            "request_id": request_id,
            "method": method,
            "path": path,
            "query": dict(query),
            "headers": dict(headers),
        }
        if form is not None:
            request['form'] = dict(form)
        if guest is not None:
            request['guest'] = guest
        encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > PUBLIC_WEB_MESSAGE_BYTES:
            raise PublicWebRuntimeError(400)
        deadline = time.monotonic() + self.timeout_seconds
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(remaining(deadline))
                connection.connect(str(self.socket_path))
                connection.settimeout(remaining(deadline))
                connection.sendall(encoded)
                response = read_frame(connection, deadline, max_bytes=PUBLIC_WEB_MESSAGE_BYTES)
        except (OSError, ValueError) as exc:
            raise PublicWebRuntimeError() from exc
        if (
            response.get("version") != PUBLIC_WEB_TRANSPORT_VERSION
            or response.get("request_id") != request_id
            or not isinstance(response.get("ok"), bool)
        ):
            raise PublicWebRuntimeError()
        if response["ok"] is False:
            status = response.get("status")
            raise PublicWebRuntimeError(status if isinstance(status, int) else 503)
        fields = {"version", "request_id", "ok", "response"}
        if 'guest_cookie' in response:
            fields.add('guest_cookie')
        if set(response) != fields:
            raise PublicWebRuntimeError()
        try:
            body = ApplicationPublicHttpResponseV1.model_validate(response["response"])
        except ValidationError as exc:
            raise PublicWebRuntimeError() from exc
        if 'guest_cookie' not in response:
            return body
        token = response['guest_cookie']
        if (method != 'GET' or guest is None or body.status != 200
                or not isinstance(token, str) or GUEST_COOKIE.fullmatch(token) is None):
            raise PublicWebRuntimeError()
        return GuestPage(body, path, token)


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


def _form_fields(body: bytes, *, allow_guest=False) -> dict[str, str]:
    raw = body.decode('ascii', errors='strict')
    if _BAD_PERCENT.search(raw):
        raise ValueError('Invalid form encoding')
    parsed = parse_qs(raw, keep_blank_values=True, strict_parsing=True,
                      encoding='utf-8', errors='strict', max_num_fields=MAX_FORM_FIELDS + 1 + allow_guest)
    special = {FORM_REQUEST_ID, GUEST_PROOF_FIELD} if allow_guest else {FORM_REQUEST_ID}
    if (any(len(values) != 1 or (name not in special and re.fullmatch(r'[a-z][a-z0-9_]{0,63}', name) is None)
            for name, values in parsed.items())
            or FORM_ID.fullmatch(parsed.get(FORM_REQUEST_ID, [''])[0]) is None):
        raise ValueError('Invalid form fields')
    return {name: values[0] for name, values in parsed.items()}


class PublicWebHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address,
        handler_class,
        *,
        client: PublicWebRuntimeClient,
        form_origin: str | None = None,
        guest_forms: bool = False,
        webhook_pilot: WebhookPilotClient | None = None,
        bind_and_activate: bool = True,
    ):
        self.client = client
        self.form_origin = form_origin
        self.form_host = public_form_origin_host(form_origin) if form_origin is not None else None
        if guest_forms and form_origin is None:
            raise ValueError('Public guest forms require --form-origin')
        if guest_forms and form_origin.startswith('http://') and server_address[0] not in {'127.0.0.1', 'localhost'}:
            raise ValueError('HTTP guest forms require a loopback listener')
        self.guest_forms = guest_forms
        if webhook_pilot is not None and server_address[0] != '127.0.0.1':
            raise ValueError('Webhook pilot requires an IPv4 loopback listener')
        self.webhook_pilot = webhook_pilot
        self.webhook_slot = threading.BoundedSemaphore(1) if webhook_pilot is not None else None
        self.form_slots = threading.BoundedSemaphore(FORM_CONCURRENT)
        self.form_rate_lock = threading.Lock()
        self.form_window = time.monotonic()
        self.form_total = 0
        self.form_sources: dict[str, int] = {}
        self.last_activity = time.monotonic()
        super().__init__(server_address, handler_class, bind_and_activate=bind_and_activate)

    def process_request(self, request, client_address):  # type: ignore[no-untyped-def]
        self.last_activity = time.monotonic()
        return super().process_request(request, client_address)

    def admit_form(self, source: str) -> bool:
        # Use only the actual socket peer; X-Forwarded-For is untrusted.
        with self.form_rate_lock:
            now = time.monotonic()
            if now - self.form_window >= FORM_WINDOW_SECONDS:
                self.form_window = now
                self.form_total = 0
                self.form_sources.clear()
            count = self.form_sources.get(source, 0)
            if count >= FORM_PER_SOURCE or self.form_total >= FORM_PER_WINDOW:
                return False
            self.form_sources[source] = count + 1
            self.form_total += 1
            return True


class PublicWebRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "3mm-Public-Web/1"
    sys_version = ""
    timeout = 5  # Bound idle I/O on the public listener, including header reads.

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

    def _guest_input(self, path: str) -> dict:
        server = self.public_server
        if (not server.guest_forms or self.command not in ('GET', 'POST')
                or self.headers.get_all('Host', []) != [server.form_host]
                or self.headers.get_all('Origin', []) not in ([], [server.form_origin])
                or self.headers.get_all('Sec-Fetch-Site', []) not in ([], ['same-origin'], ['none'])):
            return {}
        headers = self.headers.get_all('Cookie', [])
        if sum(map(len, headers)) > 8192:
            return {}
        name = guest_cookie_name(server.form_origin, path)
        tokens = []
        for header in headers:
            for cookie in header.split(';'):
                key, separator, value = cookie.strip().partition('=')
                if key.strip() == name:
                    tokens.append(value.strip() if separator else '')
        if len(tokens) > 1:
            return {}
        token = tokens[0] if tokens and GUEST_COOKIE.fullmatch(tokens[0]) else None
        return {'guest': {'origin': server.form_origin, 'cookie': token}}

    def _request(self) -> ApplicationPublicHttpResponseV1 | GuestPage:
        parts = urlsplit(self.path)
        path = _decode_path(parts.path)
        return self.public_server.client.request(
            method=self.command,
            path=path,
            query=_query(parts.query),
            headers=self._request_headers(),
            **(self._guest_input(path) if not parts.query else {}),
        )

    @staticmethod
    def _body(response: ApplicationPublicHttpResponseV1) -> bytes:
        if response.body is not None:
            return response.body.encode("utf-8")
        if response.body_base64 is not None:
            return base64.b64decode(response.body_base64, validate=True)
        return b""

    def _write_response(self, response: ApplicationPublicHttpResponseV1 | GuestPage) -> None:
        cookie = None
        if isinstance(response, GuestPage):
            origin = self.public_server.form_origin
            token = GUEST_COOKIE.fullmatch(response.cookie)
            if token is None or origin is None or not self.public_server.guest_forms:
                return self._write_error(503)
            max_age = min(GUEST_TTL_SECONDS, int(token[2]) - int(time.time()))
            if max_age <= 0:
                return self._write_error(503)
            secure = '; Secure' if origin.startswith('https://') else ''
            if re.fullmatch(r'/[A-Za-z0-9_/-]+', response.path) is None:
                return self._write_error(503)
            cookie_path = '/' if secure else response.path
            cookie = (f'{guest_cookie_name(origin, response.path)}={response.cookie}; Path={cookie_path}; '
                      f'Max-Age={max_age}; HttpOnly; SameSite=Strict{secure}')
            response = response.response
        body = self._body(response)
        self.send_response(response.status)
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie is not None:
            self.send_header('Set-Cookie', cookie)
        if self.command == 'POST':
            self.send_header('Connection', 'close')
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
            403: b"Forbidden\n",
            404: b"Not Found\n",
            405: b"Method Not Allowed\n",
            408: b"Request Timeout\n",
            413: b"Payload Too Large\n",
            415: b"Unsupported Media Type\n",
            417: b"Expectation Failed\n",
            429: b"Too Many Requests\n",
            503: b"Service Unavailable\n",
        }
        status = status if status in messages else 503
        body = messages[status]
        if status == 503 and self.command == 'POST':
            body = b'Form submission was not confirmed. Do not send a new request for the same submission.\n'
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.close_connection = True
        self.send_header('Connection', 'close')
        if status == 405:
            self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _handle_public(self) -> None:
        lengths = self.headers.get_all('Content-Length', [])
        if 'Transfer-Encoding' in self.headers or (lengths and lengths != ['0']):
            return self._write_error(400)
        if self.path=="/__3mm_component__/health":
            from three_mm_runtime.component_identity import component_health
            identity=component_health()
            if identity is not None:
                body=json.dumps(identity,separators=(",", ":")).encode()
                self.send_response(200);self.send_header("Content-Type","application/json")
                self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(body)))
                self.end_headers()
                if self.command!="HEAD":self.wfile.write(body)
                return
        try:
            response = self._request()
        except ValueError:
            self._write_error(400)
            return
        except PublicWebRuntimeError as exc:
            self._write_error(exc.status_code)
            return
        self._write_response(response)

    def do_GET(self) -> None:
        if self._webhook_target():
            return self._write_webhook(404)
        self._handle_public()

    def do_HEAD(self) -> None:
        self.do_GET()

    def _webhook_target(self) -> bool:
        pilot = self.public_server.webhook_pilot
        if pilot is None:
            return False
        try:
            return _decode_path(urlsplit(self.path).path) == pilot.path
        except ValueError:
            return False

    def _write_webhook(self, status: int, receipt: str | None = None) -> None:
        self.close_connection = True
        payload = {'status': 'accepted', 'receipt_id': receipt} if receipt is not None else {'status': 'refused'}
        body = json.dumps(payload, separators=(',', ':')).encode('ascii')
        try:
            self.connection.settimeout(1)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Connection', 'close')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
        except OSError:
            pass  # A lost HTTP reply cannot undo an admission commit.

    def _post_webhook(self) -> None:
        server = self.public_server
        pilot = server.webhook_pilot
        if pilot is None or self.path != pilot.path or self.requestline.split()[1] != pilot.path:
            return self._write_webhook(404)
        if (self.headers.defects or self.headers.get_all('Host', []) != [f'127.0.0.1:{server.server_port}']
                or any(name in self.headers for name in ('Origin', 'Cookie', 'Authorization',
                                                         'Transfer-Encoding', 'Content-Encoding'))):
            return self._write_webhook(400)
        if 'Expect' in self.headers:
            return self._write_webhook(417)
        if self.headers.get_all('Content-Type', []) != ['application/octet-stream']:
            return self._write_webhook(415)
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or not re.fullmatch(r'[1-9][0-9]{0,9}', lengths[0]):
            return self._write_webhook(400)
        length = int(lengths[0])
        if length > MAX_WEBHOOK_BYTES:
            return self._write_webhook(413)
        fields = [self.headers.get_all(name, []) for name in SIGNED_HEADERS]
        if any(len(values) != 1 for values in fields):
            return self._write_webhook(400)
        signed = (fields[0][0], fields[1][0], fields[2][0])
        if not valid_signed_fields(signed):
            return self._write_webhook(400)
        slot = server.webhook_slot
        if slot is None or not slot.acquire(blocking=False):
            return self._write_webhook(429)
        try:
            deadline = time.monotonic() + PILOT_SECONDS
            body = bytearray()
            while len(body) < length:
                self.connection.settimeout(remaining(deadline))
                chunk = self.rfile.read1(length - len(body))
                if not chunk:
                    return self._write_webhook(400)
                body.extend(chunk)
            status, receipt = pilot.submit(signed, bytes(body))
        except TimeoutError:
            return self._write_webhook(408)
        except OSError:
            return self._write_webhook(400)
        finally:
            slot.release()
        self._write_webhook(status, receipt)

    def do_POST(self) -> None:
        self.close_connection = True
        if self._webhook_target():
            return self._post_webhook()
        server = self.public_server
        if server.form_origin is None:
            return self._write_error(405)
        if (self.headers.get_all('Origin', []) != [server.form_origin]
                or self.headers.get_all('Host', []) != [server.form_host]):
            return self._write_error(403)
        if 'Expect' in self.headers:
            return self._write_error(417)
        if 'Transfer-Encoding' in self.headers:
            return self._write_error(400)
        if ('Content-Encoding' in self.headers or
                self.headers.get_all('Content-Type', []) != ['application/x-www-form-urlencoded']):
            return self._write_error(415)
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or not re.fullmatch(r'[1-9][0-9]{0,9}', lengths[0]):
            return self._write_error(400)
        length = int(lengths[0])
        if length > MAX_FORM_BYTES:
            return self._write_error(413)
        if not server.form_slots.acquire(blocking=False):
            return self._write_error(429)
        try:
            if not server.admit_form(self.client_address[0]):
                return self._write_error(429)
            if self.path != self.requestline.split()[1] or '?' in self.path or '#' in self.path:
                raise ValueError('Invalid form target')
            path = _decode_path(self.path)
            deadline = time.monotonic() + FORM_BODY_SECONDS
            body = bytearray()
            while len(body) < length:
                self.connection.settimeout(remaining(deadline))
                chunk = self.rfile.read1(length - len(body))
                if not chunk:
                    raise ValueError('Incomplete form body')
                body.extend(chunk)
            self.connection.settimeout(self.timeout)
            guest = self._guest_input(path)
            result = server.client.request(method='POST', path=path, query={}, headers={},
                                           form=_form_fields(body, allow_guest=server.guest_forms), **guest)
        except TimeoutError:
            return self._write_error(408)
        except ValueError:
            return self._write_error(400)
        except PublicWebRuntimeError as exc:
            return self._write_error(exc.status_code)
        finally:
            server.form_slots.release()
        self._write_response(result)

    def handle_expect_100(self) -> bool:
        if self.command == 'POST':
            if self._webhook_target():
                self._write_webhook(417)
            else:
                self._write_error(417)
            return False
        return super().handle_expect_100()

    def do_PUT(self) -> None:
        self._write_error(405)

    def do_PATCH(self) -> None:
        self._write_error(405)

    def do_DELETE(self) -> None:
        self._write_error(405)

    def do_OPTIONS(self) -> None:
        self._write_error(405)


def create_server(
    runtime_socket: Path,
    host: str = "127.0.0.1",
    port: int = 8081,
    *,
    client: PublicWebRuntimeClient | None = None,
    form_origin: str | None = None,
    guest_forms: bool = False,
    webhook_pilot: WebhookPilotClient | None = None,
) -> PublicWebHTTPServer:
    return PublicWebHTTPServer(
        (host, port),
        PublicWebRequestHandler,
        client=client or PublicWebRuntimeClient(runtime_socket),
        form_origin=form_origin, guest_forms=guest_forms, webhook_pilot=webhook_pilot,
    )


def create_server_from_socket(
    runtime_socket: Path,
    listener: socket.socket,
    *,
    form_origin: str | None = None,
    guest_forms: bool = False,
    webhook_pilot: WebhookPilotClient | None = None,
) -> PublicWebHTTPServer:
    server = PublicWebHTTPServer(
        listener.getsockname(),
        PublicWebRequestHandler,
        client=PublicWebRuntimeClient(runtime_socket),
        form_origin=form_origin, guest_forms=guest_forms, webhook_pilot=webhook_pilot,
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
    parser.add_argument("--runtime-socket", type=Path, required=True)
    parser.add_argument("--systemd-socket", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--idle-seconds", type=int, default=60)
    parser.add_argument('--form-origin', help='Explicit origin for anonymous forms; omitted disables POST')
    parser.add_argument('--guest-forms', action='store_true', help='Allow explicitly declared guest forms on the form origin')
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.systemd_socket:
        listener = inherited_systemd_socket()
        server = create_server_from_socket(arguments.runtime_socket, listener, form_origin=arguments.form_origin,
                                           guest_forms=arguments.guest_forms)
    else:
        server = create_server(arguments.runtime_socket, arguments.host, arguments.port, form_origin=arguments.form_origin,
                               guest_forms=arguments.guest_forms)
    try:
        serve_until_idle(server, arguments.idle_seconds)
    finally:
        server.server_close()
    return 0
