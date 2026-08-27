"""Serve a built single-page application with history-route fallback."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from threading import Thread
from typing import Sequence
from urllib.parse import urlsplit


class SPARequestHandler(SimpleHTTPRequestHandler):
    def send_head(self):  # type: ignore[no-untyped-def]
        route = PurePosixPath(urlsplit(self.path).path)
        requested_file = Path(self.translate_path(self.path))
        if not requested_file.exists() and route.suffix == "":
            self.path = "/index.html"
        return super().send_head()


def create_server(
    directory: Path,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> ThreadingHTTPServer:
    handler = partial(SPARequestHandler, directory=str(directory))
    return ThreadingHTTPServer((host, port), handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve a built 3mm web artifact")
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--alias-port", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    if not arguments.directory.joinpath("index.html").is_file():
        raise SystemExit("Web artifact directory must contain index.html")
    if arguments.alias_port == arguments.port:
        raise SystemExit("Alias port must differ from the primary port")
    with create_server(arguments.directory, arguments.host, arguments.port) as server:
        if arguments.alias_port is None:
            server.serve_forever()
            return
        with create_server(
            arguments.directory,
            arguments.host,
            arguments.alias_port,
        ) as alias_server:
            alias_thread = Thread(target=alias_server.serve_forever, daemon=True)
            alias_thread.start()
            try:
                server.serve_forever()
            finally:
                alias_server.shutdown()
                alias_thread.join(timeout=2)
