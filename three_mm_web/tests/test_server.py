from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from typing import Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from three_mm_web.server import build_parser, create_server


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
