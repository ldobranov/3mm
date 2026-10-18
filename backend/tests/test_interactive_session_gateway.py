"""M21 local session gateway tests (WP2 live): service + WebSocket route."""

import asyncio
import json

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.routes.interactive_sessions import router as interactive_sessions_router
from backend.services import interactive_session_gateway as gateway_module
from backend.services.interactive_session_gateway import (
    SessionGateway,
    SessionGatewayError,
)
from three_mm_protocol.interactive_session import (
    decode_session_frame,
    encode_session_frame,
)

DEVICE_ID = "dev_" + "a" * 32
SESSION_ID = "ses_" + "b" * 32
WS_PATH = "/api/v1/interactive-sessions/ws"


def _run(coro):
    return asyncio.run(coro)


def _open_message(request_id="req_1"):
    return json.dumps(
        {
            "op": "open",
            "request": {
                "request_id": request_id,
                "provider_id": "org.3mm.echo",
                "capability_id": "org.3mm.echo",
                "device_id": DEVICE_ID,
                "access_mode": "read",
                "options": {},
            },
        }
    )


def _data_frame(session_id, payload=b"hi", seq=1):
    return encode_session_frame(
        op="data",
        seq=seq,
        session_id=session_id,
        payload=payload,
        payload_kind="binary",
    )


def test_gateway_open_status_control_close():
    gateway = SessionGateway()

    async def scenario():
        opened = json.loads(await gateway.handle_text(7, _open_message()))
        assert opened["op"] == "opened"
        session_id = opened["acceptance"]["session_id"]
        status = json.loads(
            await gateway.handle_text(
                7, json.dumps({"op": "status", "session_id": session_id})
            )
        )
        assert status["status"]["state"] == "active"
        ok = json.loads(
            await gateway.handle_text(
                7,
                json.dumps(
                    {
                        "op": "control",
                        "control": {
                            "session_id": session_id,
                            "control_id": "ctrl_1",
                            "action": "reset",
                            "arguments": {},
                        },
                    }
                ),
            )
        )
        assert ok["op"] == "ok"
        closed = json.loads(
            await gateway.handle_text(
                7, json.dumps({"op": "close", "session_id": session_id})
            )
        )
        assert closed["op"] == "ok"

    _run(scenario())


def test_gateway_binary_data_round_trip():
    gateway = SessionGateway()

    async def scenario():
        opened = json.loads(await gateway.handle_text(7, _open_message()))
        session_id = opened["acceptance"]["session_id"]
        outbound = await gateway.handle_binary(7, _data_frame(session_id))
        header, payload = decode_session_frame(outbound)
        assert header.session_id == session_id
        assert payload == b"echo:hi"

    _run(scenario())


def test_gateway_rejects_unknown_op():
    gateway = SessionGateway()

    async def scenario():
        with pytest.raises(SessionGatewayError):
            await gateway.handle_text(7, json.dumps({"op": "bogus"}))

    _run(scenario())


def test_gateway_rejects_malformed_json():
    gateway = SessionGateway()

    async def scenario():
        with pytest.raises(SessionGatewayError):
            await gateway.handle_text(7, "{not json")

    _run(scenario())


def test_gateway_rejects_foreign_user():
    gateway = SessionGateway()

    async def scenario():
        opened = json.loads(await gateway.handle_text(7, _open_message()))
        session_id = opened["acceptance"]["session_id"]
        with pytest.raises(SessionGatewayError):
            await gateway.handle_text(
                8, json.dumps({"op": "status", "session_id": session_id})
            )

    _run(scenario())


def test_gateway_rejects_non_data_binary_op():
    gateway = SessionGateway()

    async def scenario():
        frame = encode_session_frame(
            op="close", seq=1, session_id=SESSION_ID, payload=b"", payload_kind="binary"
        )
        with pytest.raises(SessionGatewayError):
            await gateway.handle_binary(7, frame)

    _run(scenario())


@pytest.fixture()
def ws_client(monkeypatch):
    monkeypatch.setattr(gateway_module, "_GATEWAY", None)
    app = FastAPI()
    app.include_router(interactive_sessions_router)
    return TestClient(app)


def test_websocket_open_and_echo(ws_client):
    gateway = gateway_module.get_session_gateway()
    ticket = gateway.issue_ticket(7).ticket
    with ws_client.websocket_connect(f"{WS_PATH}?ticket={ticket}") as ws:
        ws.send_text(_open_message())
        opened = json.loads(ws.receive_text())
        assert opened["op"] == "opened"
        session_id = opened["acceptance"]["session_id"]
        ws.send_bytes(_data_frame(session_id))
        _header, payload = decode_session_frame(ws.receive_bytes())
        assert payload == b"echo:hi"


def test_websocket_rejects_missing_ticket(ws_client):
    with pytest.raises(WebSocketDisconnect):
        with ws_client.websocket_connect(WS_PATH) as ws:
            ws.receive_text()


def test_websocket_rejects_replayed_ticket(ws_client):
    gateway = gateway_module.get_session_gateway()
    ticket = gateway.issue_ticket(7).ticket
    with ws_client.websocket_connect(f"{WS_PATH}?ticket={ticket}") as ws:
        ws.send_text(_open_message())
        assert json.loads(ws.receive_text())["op"] == "opened"
    with pytest.raises(WebSocketDisconnect):
        with ws_client.websocket_connect(f"{WS_PATH}?ticket={ticket}") as ws:
            ws.receive_text()


def test_websocket_error_frame_for_bad_op(ws_client):
    gateway = gateway_module.get_session_gateway()
    ticket = gateway.issue_ticket(7).ticket
    with ws_client.websocket_connect(f"{WS_PATH}?ticket={ticket}") as ws:
        ws.send_text(json.dumps({"op": "bogus"}))
        error = json.loads(ws.receive_text())
        assert error["op"] == "error"
