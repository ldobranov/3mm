#!/usr/bin/env python3
"""Deterministic HTTP fixture for Stage 7 connector acceptance."""

from __future__ import annotations

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from urllib.parse import urlsplit


STATE = {"mode": "normal", "accepted": {}}


class Handler(BaseHTTPRequestHandler):
    server_version = "3mm-reference-connector/1"

    def _json(self, status, value):
        payload = json.dumps(value, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _authorized(self):
        expected = base64.b64encode(
            f"{os.environ.get('REFERENCE_USERNAME', 'reference')}:{os.environ.get('REFERENCE_PASSWORD', 'acceptance-only')}".encode()
        ).decode()
        if self.headers.get("Authorization") == f"Basic {expected}":
            return True
        self._json(401, {"error": "unauthorized"})
        return False

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/control/status" and self.client_address[0] in {"127.0.0.1", "::1"}:
            self._json(200, {"mode": STATE["mode"], "accepted": len(STATE["accepted"])})
            return
        if not self._authorized():
            return
        if path.startswith("/api/catalog/page/"):
            try:
                page = int(path.rsplit("/", 1)[-1])
            except ValueError:
                self._json(404, {"error": "not_found"})
                return
            if STATE["mode"] == "fail_catalog_2" and page == 2:
                self._json(503, {"error": "catalog_unavailable"})
                return
            if page not in {1, 2}:
                self._json(200, {"items": [], "next_page": None})
                return
            self._json(
                200,
                {
                    "items": [{"id": f"reference-{page}", "label": f"Reference {page}"}],
                    "next_page": 2 if page == 1 else None,
                },
            )
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path.startswith("/control/") and self.client_address[0] in {"127.0.0.1", "::1"}:
            mode = path.rsplit("/", 1)[-1]
            if mode not in {"normal", "unavailable", "ambiguous", "fail_catalog_2"}:
                self._json(422, {"error": "invalid_mode"})
                return
            STATE["mode"] = mode
            self._json(200, {"mode": mode})
            return
        if not self._authorized():
            return
        if path != "/api/finalize":
            self._json(404, {"error": "not_found"})
            return
        if STATE["mode"] == "unavailable":
            self._json(503, {"error": "temporarily_unavailable"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length))
        except (UnicodeError, ValueError):
            self._json(400, {"error": "invalid_json"})
            return
        key = self.headers.get("Idempotency-Key")
        if not key:
            self._json(400, {"error": "idempotency_required"})
            return
        duplicate = key in STATE["accepted"]
        STATE["accepted"][key] = body
        if STATE["mode"] == "ambiguous":
            self.close_connection = True
            return
        self._json(200, {"accepted": True, "duplicate": duplicate})

    def log_message(self, _format, *_args):
        return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9911)
    arguments = parser.parse_args()
    ThreadingHTTPServer((arguments.host, arguments.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
