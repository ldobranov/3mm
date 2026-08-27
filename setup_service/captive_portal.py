"""Small HTTP entry point used by captive-portal network checks."""

from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Iterator
from urllib.parse import urlparse


class _CaptivePortalRedirectHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    setup_url = ""

    def do_GET(self) -> None:  # noqa: N802 - inherited HTTP handler API
        self._redirect()

    def do_HEAD(self) -> None:  # noqa: N802 - inherited HTTP handler API
        self._redirect()

    def _redirect(self) -> None:
        self.send_response(302)
        self.send_header("Location", self.setup_url)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def _handler_for(setup_url: str) -> type[_CaptivePortalRedirectHandler]:
    parsed = urlparse(setup_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Captive portal setup URL must be an absolute HTTP URL")

    class CaptivePortalRedirectHandler(_CaptivePortalRedirectHandler):
        pass

    CaptivePortalRedirectHandler.setup_url = setup_url
    return CaptivePortalRedirectHandler


@contextmanager
def captive_portal_redirect(
    host: str,
    port: int,
    setup_url: str,
) -> Iterator[ThreadingHTTPServer]:
    """Serve redirects while the setup API remains available on its own port."""

    server = ThreadingHTTPServer((host, port), _handler_for(setup_url))
    thread = Thread(
        target=server.serve_forever,
        name="3mm-captive-portal",
        daemon=True,
    )
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
