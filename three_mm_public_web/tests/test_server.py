from __future__ import annotations

import base64
from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from three_mm_protocol import ApplicationPublicHttpResponseV1
from three_mm_public_web.server import (
    PublicWebCoreError,
    create_server,
)


class FakeClient:
    def __init__(self):
        self.requests = []
        self.response = ApplicationPublicHttpResponseV1.model_validate(
            {
                "status": 200,
                "content_type": "text/html; charset=utf-8",
                "headers": {"Cache-Control": "public, max-age=60"},
                "body": "<h1>Hello</h1>",
            }
        )
        self.error = None

    def request(self, **request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


@contextmanager
def running(client):
    server = create_server(Path("unused"), port=0, client=client)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_public_http_adapter_decodes_path_filters_credentials_and_supports_head():
    client = FakeClient()
    with running(client) as base:
        request = Request(
            base + "/caf%C3%A9?q=one&q=two",
            headers={
                "Accept-Language": "bg-BG",
                "Authorization": "Bearer private",
                "Cookie": "admin=session",
            },
        )
        with urlopen(request, timeout=2) as response:
            assert response.status == 200
            assert response.read() == b"<h1>Hello</h1>"
            assert response.headers["Cache-Control"] == "public, max-age=60"
            assert response.headers["X-Content-Type-Options"] == "nosniff"

        with urlopen(Request(base + "/caf%C3%A9", method="HEAD"), timeout=2) as response:
            assert response.status == 200
            assert response.read() == b""
            assert response.headers["Content-Length"] == str(len(b"<h1>Hello</h1>"))

    assert client.requests[0]["path"] == "/café"
    assert client.requests[0]["query"] == {"q": ["one", "two"]}
    assert client.requests[0]["headers"] == {"accept-language": "bg-BG"}
    assert "authorization" not in client.requests[0]["headers"]


def test_public_http_adapter_writes_binary_assets_and_redirects():
    client = FakeClient()
    payload = b"\x89PNG\r\n\x1a\n"
    client.response = ApplicationPublicHttpResponseV1.model_validate(
        {
            "status": 200,
            "content_type": "image/png",
            "headers": {"ETag": '"logo-v1"'},
            "body_base64": base64.b64encode(payload).decode("ascii"),
        }
    )
    with running(client) as base:
        with urlopen(base + "/logo.png", timeout=2) as response:
            assert response.read() == payload
            assert response.headers["Content-Type"] == "image/png"

    client.response = ApplicationPublicHttpResponseV1.model_validate(
        {"status": 301, "headers": {}, "location": "/new"}
    )
    with running(client) as base:
        opener = __import__("urllib.request", fromlist=["build_opener"]).build_opener(
            __import__("urllib.request", fromlist=["HTTPRedirectHandler"]).HTTPRedirectHandler()
        )
        client.error = PublicWebCoreError(404)
        # Directly verify the adapter-generated public error after the redirect target.
        with pytest.raises(HTTPError) as error:
            opener.open(base + "/old", timeout=2)
        assert error.value.code == 404


def test_public_http_adapter_returns_closed_errors_for_methods_and_core_failure():
    client = FakeClient()
    with running(client) as base:
        with pytest.raises(HTTPError) as method:
            urlopen(Request(base + "/", method="POST", data=b"x"), timeout=2)
        assert method.value.code == 405
        assert method.value.headers["Allow"] == "GET, HEAD"

        client.error = PublicWebCoreError(503)
        with pytest.raises(HTTPError) as unavailable:
            urlopen(base + "/", timeout=2)
        assert unavailable.value.code == 503
        assert unavailable.value.read() == b"Service Unavailable\n"


@pytest.mark.parametrize("path", ["/bad%2", "/bad%GG", "/%FF"])
def test_public_http_adapter_rejects_invalid_url_encoding(path):
    client = FakeClient()
    with running(client) as base:
        with pytest.raises(HTTPError) as error:
            urlopen(base + path, timeout=2)
        assert error.value.code == 400
