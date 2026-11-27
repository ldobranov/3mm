"""Small HTTP entry point used by captive-portal network checks."""

from __future__ import annotations

from contextlib import contextmanager
import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Callable, Iterator
from urllib.parse import urlparse

AP_ADDRESS = "10.42.0.1"
AP_SETUP_URL = "http://10.42.0.1:8895/setup"


def recovery_setup_url(local_address: str) -> str | None:
    """Only requests arriving at the active recovery AP enter its portal."""
    if local_address != AP_ADDRESS:
        return None
    from packages.provisioning.recovery_access_point import read_status
    from packages.provisioning import FileNetworkRecoveryMarker

    if (read_status()["state"] == "active" and FileNetworkRecoveryMarker(
            Path("/var/lib/3mm/provisioning/network-recovery.json")).is_active()):
        return AP_SETUP_URL
    return None


class _CaptivePortalRedirectHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    setup_url = ""
    recovery_only = False
    login_handoff: Callable[[], bool] = staticmethod(lambda: False)

    def do_GET(self) -> None:  # noqa: N802 - inherited HTTP handler API
        self._redirect()

    def do_HEAD(self) -> None:  # noqa: N802 - inherited HTTP handler API
        self._redirect()

    def _redirect(self) -> None:
        target = recovery_setup_url(self.connection.getsockname()[0]) if self.recovery_only else self.setup_url
        if target is None:
            if self.path == "/user/login" and self.login_handoff():
                # The local Setup process still owns port 80. Never serve a
                # password form here; this page only waits for admin_web.
                from components.setup.product import load_product_metadata, render_setup_page
                template = Path(__file__).with_name("static").joinpath("setup.html").read_text(encoding="utf-8")
                page = render_setup_page(template, load_product_metadata(), read_only=True, handoff_only=True).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; "
                                 "style-src 'unsafe-inline'; connect-src 'self'; form-action 'none'; frame-ancestors 'none'")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(page)
                return
            if self.command == "HEAD" and self.path == "/.well-known/3mm-admin-ready":
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                return
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
    login_handoff: Callable[[], bool] = lambda: False,
) -> Iterator[ThreadingHTTPServer | None]:
    """Serve redirects while the setup API remains available on its own port."""

    handler = _handler_for(setup_url)
    handler.recovery_only = recovery_only
    handler.login_handoff = staticmethod(login_handoff)
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        if not optional or exc.errno != errno.EADDRINUSE:
            raise
        # Full profiles already serve port 80 through components.admin_web, which
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
