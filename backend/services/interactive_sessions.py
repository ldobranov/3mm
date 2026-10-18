"""M21 local session gateway core: ticket bootstrap and bounded session manager.

Pure, transport-neutral services. There is no WebSocket, device routing or OS
isolation here; the ASGI/WebSocket endpoint is a separate layer. The one-time
ticket is how a browser bridges its existing JWT login to a WebSocket without
putting the token in a URL or trusting ``session_id`` alone.

The manager tracks local sessions and forwards bounded data/control to a provider
adapter. Providers are runtime adapters around the public extension
``SessionProvider`` contract; the echo reference below proves a second,
terminal-independent provider works end to end without Core changes.
"""

from __future__ import annotations

import asyncio
import secrets
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Mapping, Protocol

from three_mm_protocol.interactive_session import (
    DEFAULT_SESSION_MAX_LIFETIME_SECONDS,
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    MAX_SESSION_PAYLOAD_BYTES,
    SessionOpenAcceptanceV1,
    SessionOpenRequestV1,
    SessionStatusV1,
    advance_session_state,
    is_terminal_session_state,
)

# Bounded memory: pending tickets, redeemed-ticket tombstones and retained
# terminal sessions are all capped so a long-running Core cannot grow forever.
MAX_PENDING_TICKETS = 1024
MAX_SEEN_TICKETS = 4096
MAX_RETAINED_TERMINAL_SESSIONS = 256


class InteractiveSessionError(RuntimeError):
    """A local session request cannot be satisfied or is unauthorized."""


@dataclass(frozen=True, slots=True)
class SessionTicketIssue:
    ticket: str
    user_id: int
    issued_at: datetime
    expires_at: datetime


class SessionTicketStore:
    """Single-use, short-lived tickets bridging JWT login to a WebSocket.

    The HTTP layer validates the existing user JWT and issues a ticket here; the
    WebSocket layer redeems exactly one ticket. Guessing a ``session_id`` grants
    nothing because session operations re-check the resolved ``user_id``.

    Memory is bounded: expired pending tickets are pruned on issue, the pending
    set is capped, and redeemed-ticket tombstones are evicted oldest-first.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = 30,
        now: datetime | None = None,
    ) -> None:
        if not 5 <= ttl_seconds <= 300:
            raise InteractiveSessionError("Session ticket TTL is outside bounds")
        self.ttl_seconds = ttl_seconds
        self._pending: dict[str, tuple[int, datetime]] = {}
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._now = now or (lambda: datetime.now(UTC))

    def _prune(self) -> None:
        now = self._now()
        for ticket in [t for t, (_u, exp) in self._pending.items() if exp <= now]:
            self._pending.pop(ticket, None)

    def issue(self, user_id: int) -> SessionTicketIssue:
        if type(user_id) is not int or isinstance(user_id, bool) or user_id < 1:
            raise InteractiveSessionError("Session ticket user is invalid")
        self._prune()
        if len(self._pending) >= MAX_PENDING_TICKETS:
            raise InteractiveSessionError("Too many pending session tickets")
        nonce = secrets.token_hex(16)
        ticket = f"stk_{nonce}"
        issued_at = self._now()
        expires_at = issued_at + timedelta(seconds=self.ttl_seconds)
        self._pending[ticket] = (user_id, expires_at)
        return SessionTicketIssue(
            ticket=ticket, user_id=user_id, issued_at=issued_at, expires_at=expires_at
        )

    def redeem(self, ticket: str) -> int:
        """Return the bound user id exactly once, or raise. No replay."""
        if not isinstance(ticket, str) or not ticket.startswith("stk_"):
            raise InteractiveSessionError("Session ticket is invalid")
        if ticket in self._seen:
            raise InteractiveSessionError("Session ticket has already been used")
        entry = self._pending.get(ticket)
        if entry is None:
            raise InteractiveSessionError("Session ticket is unknown or expired")
        user_id, expires_at = entry
        self._pending.pop(ticket, None)
        self._seen[ticket] = None
        while len(self._seen) > MAX_SEEN_TICKETS:
            self._seen.popitem(last=False)
        if expires_at <= self._now():
            raise InteractiveSessionError("Session ticket has expired")
        return user_id

    def revoke_user(self, user_id: int) -> None:
        for ticket in list(self._pending):
            bound_user, _expires_at = self._pending[ticket]
            if bound_user == user_id:
                self._pending.pop(ticket, None)


@dataclass(frozen=True, slots=True)
class SessionProviderLimits:
    max_sessions: int = 1
    max_buffer_bytes: int = 65536
    idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS
    max_lifetime_seconds: int = DEFAULT_SESSION_MAX_LIFETIME_SECONDS


class SessionProviderAdapter(Protocol):
    """Runtime adapter around an extension SessionProvider.

    Structurally identical to the public SDK ``SessionProvider`` so a provider
    written against the SDK works here without Core changes. Inbound bytes are
    delivered through ``receive``; the returned bytes are the provider's outbound
    output.
    """

    provider_id: str
    capability_ids: tuple[str, ...]

    async def open(self, context: Mapping[str, object]) -> None: ...

    async def receive(self, session_id: str, data: bytes) -> bytes: ...

    async def control(self, session_id: str, message: Mapping[str, object]) -> None: ...

    async def close(self, session_id: str, reason: str) -> None: ...


class EchoSessionProvider:
    """Reference session provider: binds no process, echoes bounded bytes back."""

    provider_id = "org.3mm.echo"
    capability_ids = ("org.3mm.echo",)
    control_actions = ("reset",)

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, object]] = {}
        self._limits = SessionProviderLimits(max_sessions=4, max_buffer_bytes=65536)

    async def open(self, context: Mapping[str, object]) -> None:
        session_id = context["session_id"]
        if len(self._sessions) >= self._limits.max_sessions:
            raise InteractiveSessionError("Echo provider session limit reached")
        self._sessions[session_id] = {"count": 0, "active": True}

    async def receive(self, session_id: str, data: bytes) -> bytes:
        state = self._sessions.get(session_id)
        if state is None or not state["active"]:
            raise InteractiveSessionError("Echo session is unavailable")
        if len(data) > self._limits.max_buffer_bytes:
            raise InteractiveSessionError("Echo input exceeds the buffer bound")
        state["count"] = int(state["count"]) + 1
        return b"echo:" + data

    async def control(self, session_id: str, message: Mapping[str, object]) -> None:
        if message.get("action") == "reset":
            state = self._sessions.get(session_id)
            if state is not None:
                state["count"] = 0

    async def close(self, session_id: str, reason: str) -> None:
        state = self._sessions.pop(session_id, None)
        if state is not None:
            state["active"] = False


@dataclass(slots=True)
class _LocalSession:
    session_id: str
    state: str
    user_id: int
    device_id: str
    provider_id: str
    capability_id: str
    created_at: datetime
    expires_at: datetime
    last_activity_at: datetime
    outbound_seq: int = 0


class LocalSessionManager:
    """Authorized local session lifecycle and bounded data forwarding.

    No terminal/bash/xterm knowledge. Deny-by-default: unknown session id,
    wrong user, expired lifetime, exceeded idle timeout, terminal state and
    revoked providers all fail closed. ``open`` is serialized so the session
    limit cannot be exceeded by concurrent requests. Terminal sessions are
    retained only up to a bound.
    """

    def __init__(
        self,
        *,
        max_sessions: int = 4,
        now: datetime | None = None,
    ) -> None:
        if not 1 <= max_sessions <= 64:
            raise InteractiveSessionError("Local session limit is outside bounds")
        self.max_sessions = max_sessions
        self._now = now or (lambda: datetime.now(UTC))
        self._providers: dict[str, SessionProviderAdapter] = {}
        self._sessions: dict[str, _LocalSession] = {}
        self._open_lock = asyncio.Lock()

    def register_provider(self, provider: SessionProviderAdapter) -> None:
        if provider.provider_id in self._providers:
            raise InteractiveSessionError("Session provider is already registered")
        self._providers[provider.provider_id] = provider

    @property
    def session_capability_ids(self) -> set[str]:
        """Capability ids offered by the registered local providers."""
        return {
            capability_id
            for provider in self._providers.values()
            for capability_id in provider.capability_ids
        }

    def revoke_provider(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)
        for session in list(self._sessions.values()):
            if session.provider_id == provider_id:
                session.state = "terminated"

    def _prune_terminal(self) -> None:
        terminal = [
            item
            for item in self._sessions.values()
            if is_terminal_session_state(item.state)
        ]
        if len(terminal) <= MAX_RETAINED_TERMINAL_SESSIONS:
            return
        terminal.sort(key=lambda item: item.last_activity_at)
        for item in terminal[: len(terminal) - MAX_RETAINED_TERMINAL_SESSIONS]:
            self._sessions.pop(item.session_id, None)

    def _require_open(self, session: _LocalSession) -> None:
        if is_terminal_session_state(session.state):
            raise InteractiveSessionError("Session is no longer active")
        now = self._now()
        if session.expires_at <= now:
            session.state = "error"
            raise InteractiveSessionError("Session lifetime has expired")
        idle_limit = timedelta(seconds=DEFAULT_IDLE_TIMEOUT_SECONDS)
        if session.last_activity_at + idle_limit <= now and session.state == "active":
            session.state = "error"
            raise InteractiveSessionError("Session idle timeout exceeded")

    async def open(
        self, request: SessionOpenRequestV1, *, user_id: int
    ) -> SessionOpenAcceptanceV1:
        if type(user_id) is not int or isinstance(user_id, bool) or user_id < 1:
            raise InteractiveSessionError("Session user is invalid")
        provider = self._providers.get(request.provider_id)
        if provider is None or request.capability_id not in provider.capability_ids:
            raise InteractiveSessionError("Session provider is unavailable")
        async with self._open_lock:
            active = [
                item
                for item in self._sessions.values()
                if not is_terminal_session_state(item.state)
            ]
            if len(active) >= self.max_sessions:
                raise InteractiveSessionError("Local session limit reached")
            now = self._now()
            session_id = "ses_" + secrets.token_hex(16)
            session = _LocalSession(
                session_id=session_id,
                state=advance_session_state("requested", "open_accepted"),
                user_id=user_id,
                device_id=request.device_id,
                provider_id=request.provider_id,
                capability_id=request.capability_id,
                created_at=now,
                expires_at=now
                + timedelta(seconds=DEFAULT_SESSION_MAX_LIFETIME_SECONDS),
                last_activity_at=now,
            )
            await provider.open(
                {
                    "session_id": session_id,
                    "device_id": request.device_id,
                    "capability_id": request.capability_id,
                    "access_mode": request.access_mode,
                    "options": request.options,
                }
            )
            self._sessions[session_id] = session
            self._prune_terminal()
        return SessionOpenAcceptanceV1(
            session_request_version=1,
            request_id=request.request_id,
            session_id=session_id,
            state="active",
            provider_id=request.provider_id,
            capability_id=request.capability_id,
            device_id=request.device_id,
            created_at=now,
            expires_at=session.expires_at,
        )

    def _session(self, session_id: str, user_id: int) -> _LocalSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise InteractiveSessionError("Session is unknown")
        if session.user_id != user_id:
            raise InteractiveSessionError("Session does not belong to this user")
        return session

    async def status(self, session_id: str, *, user_id: int) -> SessionStatusV1:
        session = self._session(session_id, user_id)
        self._require_open(session)
        return SessionStatusV1(
            session_id=session.session_id,
            state=session.state,
            device_id=session.device_id,
            provider_id=session.provider_id,
            created_at=session.created_at,
            expires_at=session.expires_at,
        )

    async def deliver(self, session_id: str, data: bytes, *, user_id: int) -> bytes:
        session = self._session(session_id, user_id)
        self._require_open(session)
        if session.state != "active":
            raise InteractiveSessionError("Session is not attached")
        if len(data) > MAX_SESSION_PAYLOAD_BYTES:
            raise InteractiveSessionError("Session data exceeds the bound")
        provider = self._providers.get(session.provider_id)
        if provider is None:
            raise InteractiveSessionError("Session provider was revoked")
        outbound = await provider.receive(session_id, data)
        session.last_activity_at = self._now()
        session.outbound_seq += 1
        return outbound

    async def control(
        self, session_id: str, message: Mapping[str, object], *, user_id: int
    ) -> None:
        session = self._session(session_id, user_id)
        self._require_open(session)
        if session.state != "active":
            raise InteractiveSessionError("Session is not attached")
        provider = self._providers.get(session.provider_id)
        if provider is None:
            raise InteractiveSessionError("Session provider was revoked")
        await provider.control(session_id, message)
        session.last_activity_at = self._now()

    async def detach(self, session_id: str, *, user_id: int) -> None:
        session = self._session(session_id, user_id)
        self._require_open(session)
        session.state = advance_session_state(session.state, "detach")

    async def attach(self, session_id: str, *, user_id: int) -> None:
        session = self._session(session_id, user_id)
        self._require_open(session)
        session.state = advance_session_state(session.state, "attach")

    async def close(self, session_id: str, *, user_id: int) -> None:
        session = self._session(session_id, user_id)
        if is_terminal_session_state(session.state):
            raise InteractiveSessionError("Session is already closed")
        provider = self._providers.get(session.provider_id)
        if provider is not None:
            await provider.close(session_id, "closed")
        session.state = advance_session_state(session.state, "close")
        session.last_activity_at = self._now()
        self._prune_terminal()

    async def terminate(self, session_id: str, *, user_id: int) -> None:
        session = self._session(session_id, user_id)
        if is_terminal_session_state(session.state):
            raise InteractiveSessionError("Session is already terminated")
        provider = self._providers.get(session.provider_id)
        if provider is not None:
            await provider.close(session_id, "terminated")
        session.state = advance_session_state(session.state, "terminate")
        session.last_activity_at = self._now()
        self._prune_terminal()
