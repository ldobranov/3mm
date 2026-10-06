from __future__ import annotations

import socket

import pytest

from backend.config import ApplicationRuntimeSettings
from backend.services.application_public_web import ApplicationPublicWebError
from backend.services.application_public_web_transport import PublicWebGatewayServer
from three_mm_protocol import ApplicationPublicHttpResponseV1
from three_mm_public_web.server import PublicWebCoreClient, PublicWebCoreError


pytestmark = pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"),
    reason="Public web Core transport uses a local Unix socket on the Linux target",
)


class FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_public_web_gateway_round_trip_is_read_only_and_bounded(tmp_path):
    sessions = []
    captured = {}

    def session_factory():
        session = FakeSession()
        sessions.append(session)
        return session

    def dispatcher(db, settings, **request):
        captured.update(db=db, settings=settings, request=request)
        return ApplicationPublicHttpResponseV1.model_validate(
            {
                "status": 200,
                "content_type": "text/html; charset=utf-8",
                "headers": {"Cache-Control": "public, max-age=60"},
                "body": "<h1>Public</h1>",
            }
        )

    settings = ApplicationRuntimeSettings(
        root=tmp_path / "apps",
        key_root=tmp_path / "keys",
        helper_socket=tmp_path / "helper.sock",
    )
    socket_path = tmp_path / "public-web.sock"
    gateway = PublicWebGatewayServer(
        socket_path,
        settings,
        session_factory=session_factory,
        dispatcher=dispatcher,
    )
    gateway.start()
    try:
        response = PublicWebCoreClient(socket_path, timeout_seconds=2).request(
            method="GET",
            path="/items/example",
            query={"page": ["1"]},
            headers={"accept-language": "bg-BG"},
        )
    finally:
        gateway.stop()

    assert response.body == "<h1>Public</h1>"
    assert captured["request"] == {
        "method": "GET",
        "path": "/items/example",
        "query": {"page": ["1"]},
        "headers": {"accept-language": "bg-BG"},
    }
    assert sessions and sessions[0].closed is True


def test_public_web_gateway_does_not_leak_core_error_details(tmp_path):
    def unavailable(*_args, **_kwargs):
        raise ApplicationPublicWebError("sensitive internal detail", status_code=404)

    settings = ApplicationRuntimeSettings(
        root=tmp_path / "apps",
        key_root=tmp_path / "keys",
        helper_socket=tmp_path / "helper.sock",
    )
    socket_path = tmp_path / "public-web.sock"
    gateway = PublicWebGatewayServer(
        socket_path,
        settings,
        session_factory=FakeSession,
        dispatcher=unavailable,
    )
    gateway.start()
    try:
        with pytest.raises(PublicWebCoreError) as error:
            PublicWebCoreClient(socket_path, timeout_seconds=2).request(
                method="GET", path="/missing", query={}, headers={}
            )
    finally:
        gateway.stop()
    assert error.value.status_code == 404
    assert "sensitive" not in str(error.value)
