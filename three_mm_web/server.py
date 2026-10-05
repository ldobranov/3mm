"""Serve a built single-page application with history-route fallback."""

from __future__ import annotations

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from threading import Thread
from typing import Sequence
from urllib.parse import quote, unquote, urlsplit


class SPARequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, uploads_directory: Path | None = None, **kwargs):  # type: ignore[no-untyped-def]
        self.uploads_directory = uploads_directory
        super().__init__(*args, **kwargs)

    def send_head(self):  # type: ignore[no-untyped-def]
        decoded_route = unquote(urlsplit(self.path).path)
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
        if not requested_file.exists() and route.suffix == "":
            self.path = "/index.html"
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
    parser = argparse.ArgumentParser(description="Serve a built 3mm web artifact")
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
