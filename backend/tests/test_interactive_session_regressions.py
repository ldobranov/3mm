"""M21 prototype control, frame and device-ticket regressions; no live services."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from agent.session_transport import AgentSessionHost
from backend.routes import interactive_sessions as routes
from backend.services import interactive_session_gateway as gateway_module
from backend.services.interactive_session_acceptance import CounterSessionProvider
from backend.services.interactive_session_agent import (
    AgentSessionError, DeviceTicketStore, MAX_PENDING_DEVICE_TICKETS,
)
from backend.services.interactive_session_gateway import SessionGateway
from backend.utils.device_auth import require_device
from three_mm_protocol.interactive_session import (
    MAX_SESSION_PAYLOAD_BYTES, SessionOpenRequestV1,
    decode_session_frame, encode_session_frame,
)

DEVICE = "dev_" + "a" * 32
NOW = datetime(2026, 10, 18, 10, tzinfo=UTC)


class Clock:
    value = NOW

    def __call__(self):
        return self.value


def request(provider="org.3mm.echo"):
    return SessionOpenRequestV1(request_id="regression_1", provider_id=provider,
        capability_id=provider, device_id=DEVICE)


def test_agent_control_preserves_action_arguments_and_correlation():
    class RecordingCounter(CounterSessionProvider):
        async def control(self, session_id, message):
            self.last_control = message
            await super().control(session_id, message)

    async def scenario():
        provider = RecordingCounter()
        host = AgentSessionHost()
        host.register_provider(provider)
        opened = json.loads(await host.handle_text(json.dumps({"op": "open",
            "request": request(provider.provider_id).model_dump(mode="json")})))
        session_id = opened["acceptance"]["session_id"]
        assert await provider.receive(session_id, b"x") == b"count:1"
        result = json.loads(await host.handle_text(json.dumps({"op": "control",
            "control": {"session_id": session_id, "control_id": "reset_1",
                "action": "reset", "arguments": {"reason": "test"}}})))
        assert result == {"op": "ok", "key": "ctl:reset_1"}
        assert provider.last_control == {"action": "reset", "arguments": {"reason": "test"}}
        assert await provider.receive(session_id, b"x") == b"count:1"

    asyncio.run(scenario())


def test_maximum_echo_response_is_bounded_error_and_websocket_stays_usable(monkeypatch):
    gateway = SessionGateway()
    monkeypatch.setattr(gateway_module, "_GATEWAY", gateway)
    app = FastAPI()
    app.include_router(routes.router)  # Experimental test app, NOT production.
    ticket = gateway.issue_ticket(7).ticket
    with TestClient(app).websocket_connect(
            "/api/v1/interactive-sessions/ws?ticket=" + ticket) as ws:
        ws.send_text(json.dumps({"op": "open", "request": request().model_dump(mode="json")}))
        session_id = json.loads(ws.receive_text())["acceptance"]["session_id"]
        frame = encode_session_frame(op="data", seq=1, session_id=session_id,
            payload=b"x" * MAX_SESSION_PAYLOAD_BYTES, payload_kind="binary")
        ws.send_bytes(frame)
        error = ws.receive_text()
        assert len(error) < 1024 and json.loads(error)["op"] == "error"
        ws.send_bytes(encode_session_frame(op="data", seq=2, session_id=session_id,
            payload=b"ok", payload_kind="binary"))
        header, payload = decode_session_frame(ws.receive_bytes())
        assert header.seq == 2 and payload == b"echo:ok"


def test_maximum_frame_round_trips_when_provider_output_fits(monkeypatch):
    gateway = SessionGateway()

    async def identity(_session_id, data):
        return data

    monkeypatch.setattr(gateway.manager._providers["org.3mm.echo"], "receive", identity)

    async def scenario():
        opened = await gateway.open(7, request())
        data = b"x" * MAX_SESSION_PAYLOAD_BYTES
        frame = encode_session_frame(op="data", seq=1, session_id=opened.session_id,
            payload=data, payload_kind="binary")
        _, payload = decode_session_frame(await gateway.handle_binary(7, frame))
        assert payload == data

    asyncio.run(scenario())


def test_expired_device_tickets_release_capacity_without_restarting():
    clock = Clock()
    store = DeviceTicketStore(now=clock)
    expired = [store.issue(DEVICE) for _ in range(MAX_PENDING_DEVICE_TICKETS)]
    with pytest.raises(AgentSessionError, match="Too many"):
        store.issue(DEVICE)
    clock.value += timedelta(seconds=30)  # Expiry is inclusive.
    fresh = store.issue(DEVICE)
    assert len(store._pending) == 1 and store.redeem(fresh) == DEVICE
    for ticket in (expired[0], expired[-1]):
        with pytest.raises(AgentSessionError):
            store.redeem(ticket)


def test_device_ticket_issue_preserves_string_api_and_single_use():
    clock = Clock()
    store = DeviceTicketStore(now=clock)
    issue = store.issue_with_expiry(DEVICE)
    assert issue.expires_at == NOW + timedelta(seconds=30)
    assert store.redeem(issue.ticket) == DEVICE
    with pytest.raises(AgentSessionError):
        store.redeem(issue.ticket)
    ticket = store.issue(DEVICE)
    assert isinstance(ticket, str)
    clock.value += timedelta(seconds=30)
    with pytest.raises(AgentSessionError):
        store.redeem(ticket)


@pytest.mark.parametrize("updated_at", [None, datetime(2000, 1, 1, tzinfo=UTC)])
def test_device_ticket_http_returns_exact_issue_expiry(monkeypatch, updated_at):
    store = DeviceTicketStore(now=Clock())
    monkeypatch.setattr(routes, "get_device_tickets", lambda: store)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[require_device] = lambda: SimpleNamespace(
        device_id=DEVICE, updated_at=updated_at)
    result = TestClient(app).post(f"/api/v1/devices/{DEVICE}/session-ticket")
    assert result.status_code == 200
    payload = result.json()
    assert datetime.fromisoformat(payload["expires_at"]) == NOW + timedelta(seconds=30)
    assert store._pending[payload["ticket"]][1].isoformat() == payload["expires_at"]


def test_foreign_device_ticket_request_has_no_issue(monkeypatch):
    store = DeviceTicketStore(now=Clock())
    monkeypatch.setattr(routes, "get_device_tickets", lambda: store)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[require_device] = lambda: SimpleNamespace(device_id=DEVICE)
    result = TestClient(app).post("/api/v1/devices/dev_" + "b" * 32 + "/session-ticket")
    assert result.status_code == 403 and not store._pending


def test_concurrent_device_ticket_issues_respect_capacity():
    store = DeviceTicketStore(now=Clock())
    for _ in range(MAX_PENDING_DEVICE_TICKETS - 1):
        store.issue(DEVICE)

    def issue(_index):
        try:
            return store.issue(DEVICE)
        except AgentSessionError:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(issue, range(8)))
    assert sum(item is not None for item in results) == 1
    assert len(store._pending) == MAX_PENDING_DEVICE_TICKETS
