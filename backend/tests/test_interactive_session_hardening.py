"""M21 hardening tests (WP5): concurrency, volume and boundary edges."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from backend.services.interactive_session_gateway import (
    SessionGateway,
    SessionGatewayError,
)
from backend.services.interactive_sessions import (
    EchoSessionProvider,
    InteractiveSessionError,
    LocalSessionManager,
    SessionTicketStore,
)
from three_mm_protocol.interactive_session import (
    MAX_SESSION_PAYLOAD_BYTES,
    SessionOpenRequestV1,
    decode_session_frame,
    encode_session_frame,
)

DEVICE_ID = "dev_" + "a" * 32


class MutableClock:
    def __init__(self, start):
        self.now_value = start

    def __call__(self):
        return self.now_value

    def advance(self, seconds):
        self.now_value += timedelta(seconds=seconds)


def _open_request(request_id):
    return SessionOpenRequestV1(
        request_id=request_id,
        provider_id="org.3mm.echo",
        capability_id="org.3mm.echo",
        device_id=DEVICE_ID,
        access_mode="read",
        options={},
    )


def test_many_concurrent_opens_respect_limit():
    manager = LocalSessionManager(max_sessions=4)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        results = await asyncio.gather(
            *(manager.open(_open_request(f"r{i}"), user_id=7) for i in range(8)),
            return_exceptions=True,
        )
        opened = [r for r in results if not isinstance(r, Exception)]
        refused = [r for r in results if isinstance(r, Exception)]
        assert len(opened) == 4
        assert len(refused) == 4

    asyncio.run(scenario())


def test_ticket_store_survives_high_volume():
    from backend.services.interactive_sessions import MAX_SEEN_TICKETS

    store = SessionTicketStore(ttl_seconds=300)
    for _ in range(MAX_SEEN_TICKETS + 500):
        issue = store.issue(7)
        assert store.redeem(issue.ticket) == 7
    assert len(store._seen) <= MAX_SEEN_TICKETS
    fresh = store.issue(7)
    assert store.redeem(fresh.ticket) == 7


def test_gateway_rejects_malformed_binary_frames():
    gateway = SessionGateway()

    async def scenario():
        for raw in (b"", b"XXXX", b"3MMS", b"3MMS" + b"\x00" * 40, bytes(128)):
            with pytest.raises(SessionGatewayError):
                await gateway.handle_binary(7, raw)

    asyncio.run(scenario())


def test_gateway_rejects_oversized_control_message():
    gateway = SessionGateway()

    async def scenario():
        huge = '{"op":"open","request":{"padding":"' + "x" * 70000 + '"}}'
        with pytest.raises(SessionGatewayError):
            await gateway.handle_text(7, huge)

    asyncio.run(scenario())


def test_idle_timeout_boundary():
    clock = MutableClock(datetime(2026, 10, 16, 10, 0, tzinfo=UTC))
    manager = LocalSessionManager(max_sessions=4, now=clock)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        acceptance = await manager.open(_open_request("r1"), user_id=7)
        clock.advance(899)
        await manager.deliver(acceptance.session_id, b"x", user_id=7)
        clock.advance(900)
        with pytest.raises(InteractiveSessionError):
            await manager.deliver(acceptance.session_id, b"x", user_id=7)

    asyncio.run(scenario())


def test_lifetime_boundary():
    clock = MutableClock(datetime(2026, 10, 16, 10, 0, tzinfo=UTC))
    manager = LocalSessionManager(max_sessions=4, now=clock)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        acceptance = await manager.open(_open_request("r1"), user_id=7)
        # Keep the session active so only the lifetime bound is exercised.
        for _ in range(17):
            clock.advance(800)
            await manager.deliver(acceptance.session_id, b"x", user_id=7)
        clock.advance(799)
        await manager.status(acceptance.session_id, user_id=7)
        clock.advance(1)
        with pytest.raises(InteractiveSessionError):
            await manager.status(acceptance.session_id, user_id=7)

    asyncio.run(scenario())


def test_payload_boundary():
    manager = LocalSessionManager(max_sessions=4)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        acceptance = await manager.open(_open_request("r1"), user_id=7)
        await manager.deliver(
            acceptance.session_id, b"x" * MAX_SESSION_PAYLOAD_BYTES, user_id=7
        )
        with pytest.raises(InteractiveSessionError):
            await manager.deliver(
                acceptance.session_id,
                b"x" * (MAX_SESSION_PAYLOAD_BYTES + 1),
                user_id=7,
            )

    asyncio.run(scenario())


def test_frame_round_trip_at_boundary():
    session_id = "ses_" + "b" * 32
    frame = encode_session_frame(
        op="data",
        seq=1,
        session_id=session_id,
        payload=b"x" * MAX_SESSION_PAYLOAD_BYTES,
        payload_kind="binary",
    )
    header, payload = decode_session_frame(frame)
    assert header.payload_length == MAX_SESSION_PAYLOAD_BYTES
    assert len(payload) == MAX_SESSION_PAYLOAD_BYTES
