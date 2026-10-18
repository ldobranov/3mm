"""M21 prototypes must not expose unreviewed session access in production."""

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.mark.parametrize("method,path", [
    ("post", "/api/v1/interactive-sessions/ticket"),
    ("get", "/api/v1/interactive-sessions/discovery"),
    ("post", "/api/v1/devices/dev_" + "a" * 32 + "/session-ticket"),
])
def test_production_http_does_not_expose_prototype(method, path):
    from backend.main import app

    # No lifespan: no databases, workers, sockets or live provider startup.
    client = TestClient(app)
    assert getattr(client, method)(path).status_code == 404


@pytest.mark.parametrize("path", [
    "/api/v1/interactive-sessions/ws",
    "/api/v1/devices/dev_" + "a" * 32 + "/session-ws",
])
def test_production_websocket_does_not_expose_prototype(path):
    from backend.main import app

    # Exercise routing itself: FastAPI may retain lazy included-router objects.
    with pytest.raises(WebSocketDisconnect):
        with TestClient(app).websocket_connect(path + "?ticket=not-authority"):
            pytest.fail("Unreviewed M21 transport was accepted")


def test_m20_exports_and_sdk_version_survive_additive_m21_imports():
    from three_mm_application_sdk import SDK_VERSION
    from three_mm_protocol import (
        ApplicationCheckpointV1, ApplicationPeerBindingV1,
        SESSION_CONTRACT, SESSION_PROTOCOL_VERSION, SessionOpenRequestV1,
    )

    assert SDK_VERSION == "1.3"
    assert SESSION_CONTRACT == "interactive-session.v1"
    assert SESSION_PROTOCOL_VERSION == 1
    assert all(value is not None for value in (
        ApplicationCheckpointV1, ApplicationPeerBindingV1, SessionOpenRequestV1))
