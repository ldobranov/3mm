from __future__ import annotations

import os
import socket
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from components.admin_web.server import build_parser, create_server


@contextmanager
def _server(directory: Path, uploads_directory: Path | None = None) -> Iterator[str]:
    server = create_server(directory, port=0, uploads_directory=uploads_directory)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host = str(server.server_address[0])
        port = int(server.server_address[1])
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def artifact(tmp_path: Path) -> Path:
    tmp_path.joinpath("index.html").write_text("<h1>3mm</h1>", encoding="utf-8")
    tmp_path.joinpath("app.js").write_text("console.log('3mm')", encoding="utf-8")
    return tmp_path


def test_serves_index_and_existing_assets(artifact: Path) -> None:
    with _server(artifact) as base_url:
        assert "3mm" in urlopen(f"{base_url}/", timeout=2).read().decode()
        assert "console.log" in urlopen(f"{base_url}/app.js", timeout=2).read().decode()


def test_history_route_falls_back_to_index(artifact: Path) -> None:
    with _server(artifact) as base_url:
        response = urlopen(f"{base_url}/user/login", timeout=2)

        assert response.status == 200
        assert "3mm" in response.read().decode()


@pytest.fixture
def sign_in_core(monkeypatch):
    state = {"status": 200, "body": b'{"status":"ready"}', "requests": []}

    class Readiness(BaseHTTPRequestHandler):
        def do_GET(self):
            state["requests"].append((self.path, self.headers.get("Cookie"), self.headers.get("Authorization")))
            self.send_response(state["status"])
            self.end_headers()
            self.wfile.write(state["body"])

    with ThreadingHTTPServer(("127.0.0.1", 0), Readiness) as core:
        monkeypatch.setattr("components.admin_web.server._CORE_PORT", core.server_port, raising=False)
        thread = Thread(target=core.serve_forever, daemon=True)
        thread.start()
        try:
            yield state
        finally:
            core.shutdown()
            thread.join(timeout=2)


def test_handoff_probes_only_the_read_only_marker(artifact: Path, sign_in_core) -> None:
    with _server(artifact) as base_url:
        origin = {"Origin": "http://127.0.0.1:8895"}
        with urlopen(Request(base_url + "/.well-known/3mm-admin-ready", method="HEAD", headers=origin), timeout=2) as marker:
            assert marker.status == 204 and marker.read() == b""
            assert marker.headers["Cache-Control"] == "no-store"
            assert marker.headers["Access-Control-Allow-Origin"] == "*"
            assert "Access-Control-Allow-Credentials" not in marker.headers
        with urlopen(Request(base_url + "/user/login", headers=origin), timeout=2) as page:
            assert page.status == 200 and 'Access-Control-Allow-Origin' not in page.headers


def test_handoff_waits_for_the_login_document_not_just_a_listening_port(tmp_path: Path, sign_in_core) -> None:
    with _server(tmp_path) as base_url:
        marker = Request(base_url + "/.well-known/3mm-admin-ready", method="HEAD")
        entry = tmp_path / "index.html"
        for contents in (None, b""):
            if contents is not None:
                entry.write_bytes(contents)
            with pytest.raises(HTTPError) as failure:
                urlopen(marker, timeout=2)
            with failure.value as response:
                assert response.code == 503 and response.read() == b""
                assert response.headers["Cache-Control"] == "no-store"
                assert response.headers["Access-Control-Allow-Origin"] == "*"
        entry.write_text("<h1>Sign in</h1>", encoding="utf-8")
        with urlopen(marker, timeout=2) as ready:
            assert ready.status == 204
        with urlopen(base_url + "/user/login", timeout=2) as login:
            assert b"Sign in" in login.read()
        assert sign_in_core["requests"] == [("/ready", None, None)]


def test_open_login_form_is_not_a_ready_sign_in_service(artifact, sign_in_core):
    with _server(artifact) as base:
        marker = Request(base + "/.well-known/3mm-admin-ready", method="HEAD",
                         headers={"Cookie": "example=unused", "Authorization": "example"})
        assert urlopen(base + "/user/login", timeout=2).status == 200
        assert not sign_in_core["requests"]
        for status, body in ((503, b""), (302, b""), (200, b"not ready"), (200, b" " * 180)):
            sign_in_core.update(status=status, body=body)
            with pytest.raises(HTTPError) as failure:
                urlopen(marker, timeout=2)
            assert failure.value.code == 503 and failure.value.headers["Cache-Control"] == "no-store"
        sign_in_core.update(status=200, body=b'{"status":"ready"}')
        with urlopen(marker, timeout=2) as response:
            assert response.status == 204
        assert sign_in_core["requests"] == [("/ready", None, None)] * 5


def test_cold_core_listener_does_not_release_setup(artifact, monkeypatch):
    with socket.socket() as reserved, _server(artifact) as base:
        reserved.bind(("127.0.0.1", 0))  # Not yet listening: the real cold-start race.
        monkeypatch.setattr("components.admin_web.server._CORE_PORT", reserved.getsockname()[1], raising=False)
        with pytest.raises(HTTPError) as failure:
            urlopen(Request(base + "/.well-known/3mm-admin-ready", method="HEAD"), timeout=2)
        assert failure.value.code == 503
        assert urlopen(base + "/user/login", timeout=2).status == 200


@pytest.mark.parametrize("route", ["/", "/index.html", "/extensions?tab=active", "/app/screen/"])
def test_entry_follows_installed_release_even_when_rolling_back(artifact: Path, route: str) -> None:
    entry = artifact / "index.html"
    # Validator from a previously cached, newer release (including legacy clients).
    headers = {"If-Modified-Since": "Wed, 25 Nov 2026 12:00:00 GMT"}
    with _server(artifact) as base_url:
        for html, timestamp in [(b"new admin", 1_790_000_000), (b"old admin", 1_780_000_000)]:
            entry.write_bytes(html)
            os.utime(entry, (timestamp, timestamp))
            for method in ("GET", "HEAD"):
                request = Request(base_url + route, headers=headers, method=method)
                with urlopen(request, timeout=2) as response:
                    assert response.status == 200
                    assert response.headers["Cache-Control"] == "no-store"
                    assert response.headers["Last-Modified"] is None
                    assert int(response.headers["Content-Length"]) == len(html)
                    assert response.read() == (html if method == "GET" else b"")


def test_versioned_asset_still_supports_conditional_get(artifact: Path) -> None:
    assets = artifact / "assets"
    assets.mkdir()
    (assets / "main-a1b2.js").write_bytes(b"versioned")
    with _server(artifact) as base_url:
        url = base_url + "/assets/main-a1b2.js"
        with urlopen(url, timeout=2) as response:
            modified = response.headers["Last-Modified"]
            assert modified and response.headers["Cache-Control"] != "no-store"
        with pytest.raises(HTTPError) as cached:
            urlopen(Request(url, headers={"If-Modified-Since": modified}), timeout=2)
        assert cached.value.code == 304


@pytest.mark.parametrize('path', ['/generate_204', '/hotspot-detect.html', '/connecttest.txt', '/ncsi.txt', '/'])
def test_recovery_ap_redirects_through_existing_web_listener(artifact, monkeypatch, path):
    import http.client
    from urllib.parse import urlsplit
    import components.admin_web.server as web
    active = [True]
    monkeypatch.setattr(web, 'recovery_setup_url', lambda address:
                        'http://10.42.0.1:8895/setup' if active[0] else None)
    with _server(artifact) as base_url:
        url = urlsplit(base_url)
        connection = http.client.HTTPConnection(url.hostname, url.port, timeout=2)
        connection.request('GET', path, headers={'Host': 'captive.apple.com'})
        response = connection.getresponse()
        response.read()
        assert response.status == 302
        assert response.getheader('Location') == 'http://10.42.0.1:8895/setup'
        connection.close()
        active[0] = False
        assert '3mm' in urlopen(base_url + '/', timeout=2).read().decode()


def test_missing_asset_remains_not_found(artifact: Path) -> None:
    with _server(artifact) as base_url:
        with pytest.raises(HTTPError) as error:
            urlopen(f"{base_url}/assets/missing.js", timeout=2)

        assert error.value.code == 404


def test_cli_accepts_a_distinct_alias_port(artifact: Path) -> None:
    arguments = build_parser().parse_args(
        ["--directory", str(artifact), "--port", "8080", "--alias-port", "80"]
    )

    assert arguments.alias_port == 80


def test_persistent_logo_is_served_on_the_web_origin(artifact: Path, tmp_path: Path) -> None:
    uploads = tmp_path / "persistent-uploads"
    logo = uploads / "settings" / "my logo.png"
    logo.parent.mkdir(parents=True)
    logo.write_bytes(b"\x89PNG\r\n\x1a\n")
    with _server(artifact, uploads) as base_url:
        with urlopen(f"{base_url}/uploads/settings/my%20logo.png?t=123", timeout=2) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "image/png"
            assert response.read() == logo.read_bytes()
        with urlopen(Request(f"{base_url}/uploads/settings/my%20logo.png", method="HEAD"), timeout=2) as response:
            assert response.status == 200
            assert response.read() == b""


@pytest.mark.parametrize("route", [
    "/uploads", "/uploads/", "/uploads/settings/", "/uploads/settings/missing",
    "/uploads/%2e%2e/index.html", "/uploads/settings/%2e%2e/%2e%2e/index.html",
    "/uploads/settings/..%5c..%5cindex.html",
])
def test_upload_routes_do_not_fall_back_to_spa_or_escape_storage(artifact: Path, route: str) -> None:
    with _server(artifact, artifact / "uploads") as base_url:
        with pytest.raises(HTTPError) as error:
            urlopen(base_url + route, timeout=2)
        assert error.value.code == 404


def test_upload_symlink_does_not_expose_private_files(artifact: Path, tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    try:
        (uploads / "private.txt").symlink_to(artifact / "index.html")
    except OSError:
        pytest.skip("Creating symlinks is unavailable")
    with _server(artifact, uploads) as base_url:
        with pytest.raises(HTTPError) as error:
            urlopen(f"{base_url}/uploads/private.txt", timeout=2)
        assert error.value.code == 404


def test_web_uses_the_existing_installer_uploads_environment(monkeypatch, artifact: Path) -> None:
    monkeypatch.setenv("UPLOADS_DIR", str(artifact / "persistent-uploads"))
    arguments = build_parser().parse_args(["--directory", str(artifact)])
    assert arguments.uploads_directory == artifact / "persistent-uploads"
