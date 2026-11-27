"""Serve the built administrative interface with history-route fallback."""

from __future__ import annotations

import argparse
import json
import os
from functools import partial
from http.client import HTTPConnection, HTTPException
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path, PurePosixPath
from threading import Lock, Thread
from typing import Sequence
from urllib.parse import quote, unquote, urlsplit

from components.setup.captive_portal import recovery_setup_url


_CORE_PORT = 8887  # Same local Core listener as 3mm-core.service.
_handoff_probe = Lock()


def _core_ready_for_login() -> bool:
    # Only the explicit Setup handoff probe calls Core. Never use the browser's
    # Host, headers, proxy settings or credentials to select the destination.
    if not _handoff_probe.acquire(blocking=False):
        return False
    try:
        connection = HTTPConnection("127.0.0.1", _CORE_PORT, timeout=1)
        try:
            connection.request("GET", "/ready")
            with connection.getresponse() as response:
                if response.status != 200:
                    return False
                payload = response.read(129)
                return len(payload) <= 128 and json.loads(payload) == {"status": "ready"}
        except (OSError, HTTPException, ValueError):
            return False
        finally:
            connection.close()
    finally:
        _handoff_probe.release()


class SPARequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, uploads_directory: Path | None = None, **kwargs):  # type: ignore[no-untyped-def]
        self.uploads_directory = uploads_directory
        super().__init__(*args, **kwargs)

    def send_head(self):  # type: ignore[no-untyped-def]
        setup_url = recovery_setup_url(self.connection.getsockname()[0])
        if setup_url is not None:
            self.send_response(302)
            self.send_header("Location", setup_url)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        decoded_route = unquote(urlsplit(self.path).path)
        if self.command == "HEAD" and self.path == "/.well-known/3mm-admin-ready":
            # A fast web listener may serve the form before Core accepts login.
            try:
                with (Path(self.directory) / "index.html").open("rb") as entry:
                    ready = bool(entry.read(1))
            except OSError:
                ready = False
            ready = ready and _core_ready_for_login()
            self.send_response(204 if ready else 503)
            if not ready:
                self.send_header("Content-Length", "0")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return None
        if decoded_route == "/uploads" or decoded_route.startswith("/uploads/"):
            # Public mutable assets live outside the immutable frontend artifact.
            # Never expose directory listings, traversal or symlink targets.
            parts = decoded_route.removeprefix("/uploads/").split("/")
            if decoded_route == "/uploads" or self.uploads_directory is None or any(
                not part or part in {".", ".."} or any(char in part for char in ("\\", ":", "\x00"))
                for part in parts
            ):
                self.send_error(404, "Asset not found")
                return None
            root = self.uploads_directory.resolve()
            target = root
            for part in parts:
                target = target / part
                if target.is_symlink():
                    self.send_error(404, "Asset not found")
                    return None
            if not target.resolve().is_relative_to(root) or not target.is_file():
                self.send_error(404, "Asset not found")
                return None
            directory, path = self.directory, self.path
            try:
                self.directory = str(root)
                self.path = quote("/" + "/".join(parts), safe="/")
                return super().send_head()
            finally:
                self.directory, self.path = directory, path

        route = PurePosixPath(urlsplit(self.path).path)
        requested_file = Path(self.translate_path(self.path))
        root = Path(self.directory)
        if requested_file in (root, root / "index.html") or (
            not requested_file.exists() and route.suffix == ""
        ):
            # The same URL selects a different shell after update *or rollback*.
            # Old clients can send a newer If-Modified-Since than the current kit.
            # Do not date-validate this small document or leave it in browser caches.
            try:
                entry = (root / "index.html").read_bytes()
            except OSError:
                self.send_error(404, "Interface not found")
                return None
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(entry)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return BytesIO(entry)
        return super().send_head()


def create_server(
    directory: Path,
    host: str = "127.0.0.1",
    port: int = 8080,
    *,
    uploads_directory: Path | None = None,
) -> ThreadingHTTPServer:
    handler = partial(
        SPARequestHandler, directory=str(directory), uploads_directory=uploads_directory
    )
    return ThreadingHTTPServer((host, port), handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve a built administrative web artifact")
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--alias-port", type=int)
    parser.add_argument(
        "--uploads-directory", type=Path,
        default=Path(os.environ["UPLOADS_DIR"]) if os.environ.get("UPLOADS_DIR") else None,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    if not arguments.directory.joinpath("index.html").is_file():
        raise SystemExit("Web artifact directory must contain index.html")
    if arguments.alias_port == arguments.port:
        raise SystemExit("Alias port must differ from the primary port")
    with create_server(
        arguments.directory, arguments.host, arguments.port,
        uploads_directory=arguments.uploads_directory,
    ) as server:
        if arguments.alias_port is None:
            server.serve_forever()
            return
        with create_server(
            arguments.directory,
            arguments.host,
            arguments.alias_port,
            uploads_directory=arguments.uploads_directory,
        ) as alias_server:
            alias_thread = Thread(target=alias_server.serve_forever, daemon=True)
            alias_thread.start()
            try:
                server.serve_forever()
            finally:
                alias_server.shutdown()
                alias_thread.join(timeout=2)
