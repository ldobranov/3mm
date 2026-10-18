"""M21 local session gateway core tests (WP2): tickets and session manager."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from backend.services.interactive_sessions import (
    EchoSessionProvider,
    InteractiveSessionError,
    LocalSessionManager,
    SessionTicketStore,
)
from three_mm_protocol.interactive_session import (
    MAX_SESSION_PAYLOAD_BYTES,
    SessionOpenRequestV1,
)

DEVICE_ID = "dev_" + "a" * 32


class MutableClock:
    def __init__(self, start: datetime) -> None:
        self.now_value = start

    def __call__(self) -> datetime:
        return self.now_value

    def advance(self, seconds: int) -> None:
        self.now_value += timedelta(seconds=seconds)


def open_request(
    provider_id="org.3mm.echo",
    capability_id="org.3mm.echo",
    request_id="echo_req_1",
):
    return SessionOpenRequestV1(
        request_id=request_id,
        provider_id=provider_id,
        capability_id=capability_id,
        device_id=DEVICE_ID,
        access_mode="read",
        options={},
    )


def test_ticket_issue_and_single_redeem():
    store = SessionTicketStore(ttl_seconds=30)
    issue = store.issue(7)
    assert issue.user_id == 7
    assert issue.ticket.startswith("stk_")
    assert store.redeem(issue.ticket) == 7


def test_ticket_cannot_be_replayed():
    store = SessionTicketStore(ttl_seconds=30)
    issue = store.issue(7)
    assert store.redeem(issue.ticket) == 7
    with pytest.raises(InteractiveSessionError):
        store.redeem(issue.ticket)


def test_ticket_unknown_is_rejected():
    store = SessionTicketStore(ttl_seconds=30)
    with pytest.raises(InteractiveSessionError):
        store.redeem("stk_missing")


def test_ticket_expiry():
    clock = MutableClock(datetime(2026, 10, 12, 10, 0, tzinfo=UTC))
    store = SessionTicketStore(ttl_seconds=30, now=clock)
    issue = store.issue(7)
    clock.advance(31)
    with pytest.raises(InteractiveSessionError):
        store.redeem(issue.ticket)


def test_ticket_revoke_user():
    store = SessionTicketStore(ttl_seconds=30)
    issue = store.issue(7)
    store.revoke_user(7)
    with pytest.raises(InteractiveSessionError):
        store.redeem(issue.ticket)


def test_ttl_bounds():
    with pytest.raises(InteractiveSessionError):
        SessionTicketStore(ttl_seconds=1)


def _run(coro):
    return asyncio.run(coro)


def test_echo_open_status_deliver_close():
    manager = LocalSessionManager(max_sessions=4)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        acceptance = await manager.open(open_request(), user_id=7)
        session_id = acceptance.session_id
        status = await manager.status(session_id, user_id=7)
        assert status.state == "active"
        outbound = await manager.deliver(session_id, b"hi", user_id=7)
        assert outbound == b"echo:hi"
        await manager.close(session_id, user_id=7)

    _run(scenario())


def test_session_belongs_to_user():
    manager = LocalSessionManager(max_sessions=4)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        acceptance = await manager.open(open_request(), user_id=7)
        with pytest.raises(InteractiveSessionError):
            await manager.deliver(acceptance.session_id, b"x", user_id=8)

    _run(scenario())


def test_unknown_provider_fails_closed():
    manager = LocalSessionManager(max_sessions=4)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        with pytest.raises(InteractiveSessionError):
            await manager.open(
                open_request(provider_id="org.example.missing"), user_id=7
            )

    _run(scenario())


def test_session_limit():
    manager = LocalSessionManager(max_sessions=1)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        await manager.open(open_request(), user_id=7)
        with pytest.raises(InteractiveSessionError):
            await manager.open(
                open_request(request_id="echo_req_2"), user_id=7
            )

    _run(scenario())


def test_deliver_after_detach_fails():
    manager = LocalSessionManager(max_sessions=4)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        acceptance = await manager.open(open_request(), user_id=7)
        await manager.detach(acceptance.session_id, user_id=7)
        with pytest.raises(InteractiveSessionError):
            await manager.deliver(acceptance.session_id, b"x", user_id=7)

    _run(scenario())


def test_attach_after_detach():
    manager = LocalSessionManager(max_sessions=4)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        acceptance = await manager.open(open_request(), user_id=7)
        await manager.detach(acceptance.session_id, user_id=7)
        await manager.attach(acceptance.session_id, user_id=7)
        outbound = await manager.deliver(acceptance.session_id, b"ok", user_id=7)
        assert outbound == b"echo:ok"

    _run(scenario())


def test_provider_revocation_terminates_session():
    manager = LocalSessionManager(max_sessions=4)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        acceptance = await manager.open(open_request(), user_id=7)
        manager.revoke_provider("org.3mm.echo")
        with pytest.raises(InteractiveSessionError):
            await manager.deliver(acceptance.session_id, b"x", user_id=7)

    _run(scenario())


def test_oversized_deliver_fails():
    manager = LocalSessionManager(max_sessions=4)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        acceptance = await manager.open(open_request(), user_id=7)
        with pytest.raises(InteractiveSessionError):
            await manager.deliver(
                acceptance.session_id,
                b"x" * (MAX_SESSION_PAYLOAD_BYTES + 1),
                user_id=7,
            )

    _run(scenario())


def test_idle_timeout_fails_deliver():
    clock = MutableClock(datetime(2026, 10, 12, 10, 0, tzinfo=UTC))
    manager = LocalSessionManager(max_sessions=4, now=clock)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        acceptance = await manager.open(open_request(), user_id=7)
        clock.advance(901)
        with pytest.raises(InteractiveSessionError):
            await manager.deliver(acceptance.session_id, b"x", user_id=7)

    _run(scenario())


def test_lifetime_expiry_fails_status():
    clock = MutableClock(datetime(2026, 10, 12, 10, 0, tzinfo=UTC))
    manager = LocalSessionManager(max_sessions=4, now=clock)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        acceptance = await manager.open(open_request(), user_id=7)
        clock.advance(14401)
        with pytest.raises(InteractiveSessionError):
            await manager.status(acceptance.session_id, user_id=7)

    _run(scenario())


def test_concurrent_open_cannot_exceed_limit():
    manager = LocalSessionManager(max_sessions=1)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        results = await asyncio.gather(
            manager.open(open_request(request_id="r1"), user_id=7),
            manager.open(open_request(request_id="r2"), user_id=7),
            return_exceptions=True,
        )
        opened = [item for item in results if not isinstance(item, Exception)]
        refused = [item for item in results if isinstance(item, Exception)]
        assert len(opened) == 1
        assert len(refused) == 1

    _run(scenario())


def test_control_after_close_fails():
    manager = LocalSessionManager(max_sessions=4)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        acceptance = await manager.open(open_request(), user_id=7)
        await manager.close(acceptance.session_id, user_id=7)
        with pytest.raises(InteractiveSessionError):
            await manager.control(
                acceptance.session_id, {"action": "reset"}, user_id=7
            )

    _run(scenario())


def test_deliver_after_close_fails():
    manager = LocalSessionManager(max_sessions=4)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        acceptance = await manager.open(open_request(), user_id=7)
        await manager.close(acceptance.session_id, user_id=7)
        with pytest.raises(InteractiveSessionError):
            await manager.deliver(acceptance.session_id, b"x", user_id=7)

    _run(scenario())


def test_close_twice_fails():
    manager = LocalSessionManager(max_sessions=4)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        acceptance = await manager.open(open_request(), user_id=7)
        await manager.close(acceptance.session_id, user_id=7)
        with pytest.raises(InteractiveSessionError):
            await manager.close(acceptance.session_id, user_id=7)

    _run(scenario())


def test_terminal_sessions_are_pruned():
    from backend.services.interactive_sessions import MAX_RETAINED_TERMINAL_SESSIONS

    manager = LocalSessionManager(max_sessions=4)
    manager.register_provider(EchoSessionProvider())

    async def scenario():
        for index in range(MAX_RETAINED_TERMINAL_SESSIONS + 20):
            acceptance = await manager.open(
                open_request(request_id=f"r{index}"), user_id=7
            )
            await manager.close(acceptance.session_id, user_id=7)
        assert len(manager._sessions) <= MAX_RETAINED_TERMINAL_SESSIONS

    _run(scenario())


def test_ticket_store_bounds_seen_tombstones():
    from backend.services.interactive_sessions import MAX_SEEN_TICKETS

    store = SessionTicketStore(ttl_seconds=300)
    for _ in range(MAX_SEEN_TICKETS + 50):
        issue = store.issue(7)
        store.redeem(issue.ticket)
    assert len(store._seen) <= MAX_SEEN_TICKETS
