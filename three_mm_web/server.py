"""Serve a built single-page application with history-route fallback."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
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
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    if not arguments.directory.joinpath("index.html").is_file():
        raise SystemExit("Web artifact directory must contain index.html")
    with create_server(arguments.directory, arguments.host, arguments.port) as server:
        server.serve_forever()
