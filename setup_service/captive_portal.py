"""Small HTTP entry point used by captive-portal network checks."""

from __future__ import annotations

from contextlib import contextmanager
import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Iterator
from urllib.parse import urlparse

AP_ADDRESS = "10.42.0.1"
AP_SETUP_URL = "http://10.42.0.1:8895/setup"


def recovery_setup_url(local_address: str) -> str | None:
    """Only requests arriving at the active recovery AP enter its portal."""
    if local_address != AP_ADDRESS:
        return None
    from three_mm_provisioning.recovery_access_point import read_status
    from three_mm_provisioning import FileNetworkRecoveryMarker

    if (read_status()["state"] == "active" and FileNetworkRecoveryMarker(
            Path("/var/lib/3mm/provisioning/network-recovery.json")).is_active()):
        return AP_SETUP_URL
    return None


class _CaptivePortalRedirectHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    setup_url = ""
    recovery_only = False

    def do_GET(self) -> None:  # noqa: N802 - inherited HTTP handler API
        self._redirect()

    def do_HEAD(self) -> None:  # noqa: N802 - inherited HTTP handler API
        self._redirect()

    def _redirect(self) -> None:
        target = recovery_setup_url(self.connection.getsockname()[0]) if self.recovery_only else self.setup_url
        if target is None:
            self.send_error(404)
            return
        self.send_response(302)
        self.send_header("Location", target)
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
    *,
    recovery_only: bool = False,
    optional: bool = False,
) -> Iterator[ThreadingHTTPServer | None]:
    """Serve redirects while the setup API remains available on its own port."""

    handler = _handler_for(setup_url)
    handler.recovery_only = recovery_only
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        if not optional or exc.errno != errno.EADDRINUSE:
            raise
        # Full profiles already serve port 80 through three_mm_web, which
        # performs the same AP-only redirect. Node profiles use this listener.
        yield None
        return
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
