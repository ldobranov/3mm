"""M21 local Agent session transport tests (WP2 live remainder)."""

import asyncio
import json

import anyio
import pytest
from fastapi import FastAPI, WebSocket
from starlette.testclient import TestClient

from agent.session_transport import AgentSessionHost
from backend.routes.interactive_sessions import router as interactive_sessions_router
from backend.services import interactive_session_agent as agent_module
from backend.services import interactive_session_gateway as gateway_module
from backend.services.interactive_session_agent import (
    AgentSessionError,
    DeviceTicketStore,
)
from three_mm_protocol.interactive_session import (
    decode_session_frame,
    encode_session_frame,
)

AGENT_DEVICE = "dev_" + "a" * 32
AGENT_CAP = "org.3mm.agent.echo"
WS_USER = "/api/v1/interactive-sessions/ws"
WS_AGENT = f"/api/v1/devices/{AGENT_DEVICE}/session-ws"


def _bounded_app(app, *, timeout=5):
    """A missing WebSocket response must fail, not stall the entire suite."""

    async def bounded(scope, receive, send):
        if scope["type"] == "websocket":
            with anyio.fail_after(timeout):
                await app(scope, receive, send)
        else:
            await app(scope, receive, send)

    return bounded


def _wait_for_agent(client, gateway, *, available=True):
    async def ready():
        with anyio.fail_after(5):
            while gateway.router.offers(AGENT_DEVICE, AGENT_CAP) != available:
                await anyio.sleep(0.001)

    client.portal.call(ready)


def _run(coro):
    return asyncio.run(coro)


class AgentEchoProvider:
    provider_id = "org.3mm.agent.echo"
    capability_ids = (AGENT_CAP,)

    def __init__(self):
        self.sessions = set()

    async def open(self, context):
        self.sessions.add(context["session_id"])

    async def receive(self, session_id, data):
        if session_id not in self.sessions:
            raise AgentSessionError("Agent session is unavailable")
        return b"agent-echo:" + data

    async def control(self, session_id, message):
        pass

    async def close(self, session_id, reason):
        self.sessions.discard(session_id)


def _data_frame(session_id, payload=b"hi", seq=1):
    return encode_session_frame(
        op="data",
        seq=seq,
        session_id=session_id,
        payload=payload,
        payload_kind="binary",
    )


def _open_message(request_id="req_1"):
    return json.dumps(
        {
            "op": "open",
            "request": {
                "request_id": request_id,
                "provider_id": "org.3mm.agent.echo",
                "capability_id": AGENT_CAP,
                "device_id": AGENT_DEVICE,
                "access_mode": "read",
                "options": {},
            },
        }
    )


def test_device_ticket_store_single_use():
    store = DeviceTicketStore(ttl_seconds=30)
    ticket = store.issue(AGENT_DEVICE)
    assert store.redeem(ticket) == AGENT_DEVICE
    with pytest.raises(AgentSessionError):
        store.redeem(ticket)


def test_device_ticket_store_rejects_unknown():
    store = DeviceTicketStore(ttl_seconds=30)
    with pytest.raises(AgentSessionError):
        store.redeem("dvt_missing")


def test_agent_host_open_data_close():
    host = AgentSessionHost()
    host.register_provider(AgentEchoProvider())

    async def scenario():
        opened = json.loads(await host.handle_text(_open_message()))
        assert opened["op"] == "opened"
        assert opened["key"] == "open:req_1"
        session_id = opened["acceptance"]["session_id"]
        outbound = await host.handle_binary(_data_frame(session_id))
        _header, payload = decode_session_frame(outbound)
        assert payload == b"agent-echo:hi"
        closed = json.loads(
            await host.handle_text(
                json.dumps({"op": "close", "session_id": session_id})
            )
        )
        assert closed["op"] == "ok"
        assert closed["key"] == f"close:{session_id}"

    _run(scenario())


def test_agent_host_rejects_unknown_provider():
    host = AgentSessionHost()

    async def scenario():
        response = json.loads(await host.handle_text(_open_message()))
        assert response["op"] == "error"

    _run(scenario())


@pytest.fixture()
def app_client(monkeypatch):
    monkeypatch.setattr(gateway_module, "_GATEWAY", None)
    monkeypatch.setattr(agent_module, "_DEVICE_TICKETS", None)
    app = FastAPI()
    app.include_router(interactive_sessions_router)
    # Without this context each WebSocket gets a DIFFERENT AnyIO portal/loop.
    # The Agent resolves futures created by the browser connection: both must
    # run on the same application loop, just as on the actual ASGI server.
    with TestClient(_bounded_app(app)) as client:
        yield client


def test_websocket_deadline_fails_instead_of_waiting_forever():
    app = FastAPI()

    @app.websocket("/silent")
    async def silent(websocket: WebSocket):
        await websocket.accept()
        await anyio.sleep_forever()

    with pytest.raises(TimeoutError):
        with TestClient(_bounded_app(app, timeout=0.05)) as client:
            with client.websocket_connect("/silent") as ws:
                ws.receive_text()


def test_open_before_agent_hello_is_refused_without_waiting(app_client):
    gateway = gateway_module.get_session_gateway()
    host = AgentSessionHost()
    host.register_provider(AgentEchoProvider())
    device_ticket = agent_module.get_device_tickets().issue(AGENT_DEVICE)
    user_ticket = gateway.issue_ticket(7).ticket

    with app_client.websocket_connect(f"{WS_AGENT}?ticket={device_ticket}") as agent_ws:
        # WS acceptance alone is NOT an application/provider readiness signal.
        with app_client.websocket_connect(f"{WS_USER}?ticket={user_ticket}") as ws:
            assert app_client.portal is agent_ws.portal is ws.portal
            ws.send_text(_open_message())
            assert json.loads(ws.receive_text())["op"] == "error"
            assert not gateway.router.offers(AGENT_DEVICE, AGENT_CAP)

            agent_ws.send_text(host.hello("rasp-3mm-agent"))
            _wait_for_agent(app_client, gateway)
            ws.send_text(_open_message(request_id="req_after_hello"))
            agent_ws.send_text(_run(host.handle_text(agent_ws.receive_text())))
            assert json.loads(ws.receive_text())["op"] == "opened"


def test_end_to_end_browser_session_via_agent(app_client):
    gateway = gateway_module.get_session_gateway()
    host = AgentSessionHost()
    host.register_provider(AgentEchoProvider())
    device_ticket = agent_module.get_device_tickets().issue(AGENT_DEVICE)
    user_ticket = gateway.issue_ticket(7).ticket

    with app_client.websocket_connect(f"{WS_AGENT}?ticket={device_ticket}") as agent_ws:
        agent_ws.send_text(host.hello("rasp-3mm-agent"))
        _wait_for_agent(app_client, gateway)
        with app_client.websocket_connect(f"{WS_USER}?ticket={user_ticket}") as ws:
            assert app_client.portal is agent_ws.portal is ws.portal
            ws.send_text(_open_message())
            raw = agent_ws.receive_text()
            agent_ws.send_text(_run(host.handle_text(raw)))
            opened = json.loads(ws.receive_text())
            assert opened["op"] == "opened"
            session_id = opened["acceptance"]["session_id"]
            assert opened["acceptance"]["device_id"] == AGENT_DEVICE

            ws.send_bytes(_data_frame(session_id))
            raw = agent_ws.receive_bytes()
            agent_ws.send_bytes(_run(host.handle_binary(raw)))
            _header, payload = decode_session_frame(ws.receive_bytes())
            assert payload == b"agent-echo:hi"

            ws.send_text(json.dumps({"op": "close", "session_id": session_id}))
            raw = agent_ws.receive_text()
            agent_ws.send_text(_run(host.handle_text(raw)))
            assert json.loads(ws.receive_text())["op"] == "ok"


def test_end_to_end_agent_disconnect_terminates_session(app_client):
    gateway = gateway_module.get_session_gateway()
    host = AgentSessionHost()
    host.register_provider(AgentEchoProvider())
    device_ticket = agent_module.get_device_tickets().issue(AGENT_DEVICE)
    user_ticket = gateway.issue_ticket(7).ticket

    with app_client.websocket_connect(f"{WS_AGENT}?ticket={device_ticket}") as agent_ws:
        agent_ws.send_text(host.hello("rasp-3mm-agent"))
        _wait_for_agent(app_client, gateway)
        with app_client.websocket_connect(f"{WS_USER}?ticket={user_ticket}") as ws:
            assert app_client.portal is agent_ws.portal is ws.portal
            ws.send_text(_open_message())
            raw = agent_ws.receive_text()
            agent_ws.send_text(_run(host.handle_text(raw)))
            opened = json.loads(ws.receive_text())
            session_id = opened["acceptance"]["session_id"]
    # The agent link is gone; the routed session must fail closed.
    _wait_for_agent(app_client, gateway, available=False)
    ticket = gateway.issue_ticket(7).ticket
    with app_client.websocket_connect(f"{WS_USER}?ticket={ticket}") as ws:
        ws.send_bytes(_data_frame(session_id, payload=b"x"))
        error = json.loads(ws.receive_text())
        assert error["op"] == "error"
