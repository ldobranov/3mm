"""M21 local Agent session transport (WP2 live remainder).

The local Agent hosts session providers. It connects to Core over a
device-authenticated WebSocket: Core issues a single-use device ticket through
the existing device credential (``require_device``), the Agent redeems it at
connect time, declares its providers, and then serves session operations.

``AgentSessionTransport`` implements the WP3 ``SessionTransport`` protocol by
bridging each operation to the Agent WebSocket and awaiting the correlated
response. Every Agent response carries its correlation ``key`` (binary frames
derive it from the frame header), so responses cannot be confused or replayed.

This module performs no OS isolation and starts no process; the Agent-side
handler lives in ``agent/session_transport.py``.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Callable, Mapping

from three_mm_protocol.interactive_session import (
    SessionControlV1,
    SessionOpenAcceptanceV1,
    SessionOpenRequestV1,
    decode_session_frame,
    encode_session_frame,
)

MAX_PENDING_DEVICE_TICKETS = 1024
MAX_SEEN_DEVICE_TICKETS = 4096


class AgentSessionError(RuntimeError):
    """An Agent session transport request failed or is unauthorized."""


@dataclass(frozen=True, slots=True)
class DeviceTicketIssue:
    ticket: str
    expires_at: datetime


class DeviceTicketStore:
    """Single-use, short-lived tickets binding a device credential to the WS."""

    def __init__(self, *, ttl_seconds: int = 30,
                 now: Callable[[], datetime] | None = None) -> None:
        if not 5 <= ttl_seconds <= 300:
            raise AgentSessionError("Device ticket TTL is outside bounds")
        self.ttl_seconds = ttl_seconds
        self._pending: dict[str, tuple[str, datetime]] = {}
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._now = now or (lambda: datetime.now(UTC))
        self._lock = Lock()

    def issue(self, device_id: str) -> str:
        """Preserve the existing internal string-ticket API."""
        return self.issue_with_expiry(device_id).ticket

    def issue_with_expiry(self, device_id: str) -> DeviceTicketIssue:
        """Return the ticket's exact stored expiry, never device metadata."""
        if not isinstance(device_id, str) or not device_id:
            raise AgentSessionError("Device ticket device is invalid")
        with self._lock:
            now = self._now()
            for expired in [ticket for ticket, (_, expiry) in self._pending.items()
                            if expiry <= now]:
                self._pending.pop(expired, None)
            if len(self._pending) >= MAX_PENDING_DEVICE_TICKETS:
                raise AgentSessionError("Too many pending device tickets")
            ticket = f"dvt_{secrets.token_hex(16)}"
            expiry = now + timedelta(seconds=self.ttl_seconds)
            self._pending[ticket] = (device_id, expiry)
            return DeviceTicketIssue(ticket, expiry)

    def redeem(self, ticket: str) -> str:
        """Return the bound device id exactly once, or raise. No replay."""
        if not isinstance(ticket, str) or not ticket.startswith("dvt_"):
            raise AgentSessionError("Device ticket is invalid")
        with self._lock:
            if ticket in self._seen:
                raise AgentSessionError("Device ticket has already been used")
            entry = self._pending.pop(ticket, None)
            if entry is None:
                raise AgentSessionError("Device ticket is unknown or expired")
            device_id, expires_at = entry
            self._seen[ticket] = None
            while len(self._seen) > MAX_SEEN_DEVICE_TICKETS:
                self._seen.popitem(last=False)
            if expires_at <= self._now():
                raise AgentSessionError("Device ticket has expired")
            return device_id


class AgentSessionTransport:
    """WP3 ``SessionTransport`` bridging Core operations to the Agent WS."""

    device_id: str

    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self.capability_ids: tuple[str, ...] = ()
        self._websocket = None
        self._pending: dict[str, asyncio.Future] = {}
        self._data_seq = 0

    def attach(self, websocket) -> None:
        self._websocket = websocket

    def declare(self, capability_ids) -> None:
        self.capability_ids = tuple(dict.fromkeys(capability_ids))

    def detach(self) -> None:
        self._websocket = None
        for future in self._pending.values():
            if not future.done():
                future.set_exception(
                    AgentSessionError("Agent session transport detached")
                )
        self._pending.clear()

    async def _roundtrip(self, key: str, send) -> object:
        if self._websocket is None:
            raise AgentSessionError("Agent session transport is not attached")
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[key] = future
        try:
            await send()
            return await future
        finally:
            self._pending.pop(key, None)

    async def open(self, request: SessionOpenRequestV1) -> SessionOpenAcceptanceV1:

        async def send() -> None:
            await self._websocket.send_text(
                json.dumps(
                    {
                        "op": "open",
                        "request": request.model_dump(mode="json"),
                    }
                )
            )

        message = await self._roundtrip(f"open:{request.request_id}", send)
        return SessionOpenAcceptanceV1.model_validate(message["acceptance"])

    async def deliver(self, session_id: str, data: bytes) -> bytes:
        self._data_seq += 1
        seq = self._data_seq
        frame = encode_session_frame(
            op="data",
            seq=seq,
            session_id=session_id,
            payload=data,
            payload_kind="binary",
        )

        async def send() -> None:
            await self._websocket.send_bytes(frame)

        raw = await self._roundtrip(f"data:{session_id}:{seq}", send)
        _header, payload = decode_session_frame(raw)
        return payload

    async def control(self, session_id: str, message: Mapping[str, object]) -> None:
        control = SessionControlV1(
            session_id=session_id,
            control_id=f"ctl_{secrets.token_hex(8)}",
            action=str(message.get("action", "")),
            arguments=dict(message.get("arguments", {})),
        )

        async def send() -> None:
            await self._websocket.send_text(
                json.dumps(
                    {"op": "control", "control": control.model_dump(mode="json")}
                )
            )

        await self._roundtrip(f"ctl:{control.control_id}", send)

    async def close(self, session_id: str, reason: str) -> None:

        async def send() -> None:
            await self._websocket.send_text(
                json.dumps(
                    {"op": "close", "session_id": session_id, "reason": reason}
                )
            )

        await self._roundtrip(f"close:{session_id}", send)

    def resolve_text(self, raw: str) -> None:
        """Resolve one Agent JSON response to its pending operation."""
        try:
            message = json.loads(raw)
        except (ValueError, TypeError):
            return
        if not isinstance(message, dict):
            return
        key = message.get("key")
        future = self._pending.get(key) if isinstance(key, str) else None
        if future is None or future.done():
            return
        if message.get("op") == "error":
            future.set_exception(
                AgentSessionError(str(message.get("detail") or "Agent error"))
            )
        else:
            future.set_result(message)

    def resolve_bytes(self, raw: bytes) -> None:
        """Resolve one Agent binary data frame to its pending operation."""
        try:
            header, _payload = decode_session_frame(raw)
        except ValueError:
            return
        future = self._pending.get(f"data:{header.session_id}:{header.seq}")
        if future is not None and not future.done():
            future.set_result(raw)


_DEVICE_TICKETS: DeviceTicketStore | None = None


def get_device_tickets() -> DeviceTicketStore:
    global _DEVICE_TICKETS
    if _DEVICE_TICKETS is None:
        _DEVICE_TICKETS = DeviceTicketStore()
    return _DEVICE_TICKETS


__all__ = [
    "AgentSessionError",
    "AgentSessionTransport",
    "DeviceTicketStore",
    "DeviceTicketIssue",
    "get_device_tickets",
]
