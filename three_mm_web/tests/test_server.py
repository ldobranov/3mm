from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from typing import Iterator
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from three_mm_web.server import create_server


@contextmanager
def _server(directory: Path) -> Iterator[str]:
    server = create_server(directory, port=0)
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
