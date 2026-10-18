"""M21 remote session transport and multiplexing (WP3).

A separate, optional ``SessionTransport`` boundary alongside the existing C10
``DeviceTransport``. The C10 command/report contract is unchanged. This layer
routes interactive sessions to local or remote devices, multiplexes independent
sessions, refuses devices without the capability, and re-checks authority on
every use. It performs no OS isolation and no process execution.

Cloud relay is a later, separately approved transport stage; it is not modeled
here and must not become a second command authority over a Node.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Mapping, Protocol

from three_mm_protocol.interactive_session import (
    SessionDiscoveryV1,
    SessionOpenAcceptanceV1,
    SessionOpenRequestV1,
    SessionStatusV1,
    SessionTargetV1,
)


class RemoteSessionError(RuntimeError):
    """A remote session cannot be routed, authorized or delivered."""


@dataclass(frozen=True, slots=True)
class RemoteDeviceSession:
    """One device's advertised interactive capability and reachability.

    ``available`` is separate from ``sessions``: a device may advertise a
    provider yet be offline. ``authority_generation`` is re-checked on use so a
    revoked or re-enrolled device cannot keep an old session alive.
    """

    device_id: str
    display_name: str
    sessions: tuple[str, ...]
    available: bool
    authority_generation: int
    local: bool = False
    unavailable_reason: str | None = None


class SessionTransport(Protocol):
    """Per-device bidirectional session transport (local Agent or Hub↔Node).

    Implementations authenticate the device and carry bounded frames. They do
    not decide authorization; the router does, before and during use.
    """

    device_id: str

    async def open(self, request: SessionOpenRequestV1) -> SessionOpenAcceptanceV1: ...

    async def deliver(self, session_id: str, data: bytes) -> bytes: ...

    async def control(
        self, session_id: str, message: Mapping[str, object]
    ) -> None: ...

    async def close(self, session_id: str, reason: str) -> None: ...


class RemoteSessionRouter:
    """Multiplexes sessions across devices with authority re-checks.

    Deny-by-default: unknown device, offline device, missing capability, stale
    authority generation and revoked transport all fail closed. A disconnect
    marks affected sessions ``error`` and never silently reopens them; reconnect
    requires a fresh ``open`` (re-authentication), never replay.
    """

    def __init__(self, *, now: datetime | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self._devices: dict[str, RemoteDeviceSession] = {}
        self._transports: dict[str, SessionTransport] = {}
        # session_id -> (device_id, authority_generation, capability_id)
        self._sessions: dict[str, tuple[str, int, str]] = {}

    def register_device(self, device: RemoteDeviceSession) -> None:
        if device.device_id in self._devices:
            raise RemoteSessionError("Device is already registered")
        self._devices[device.device_id] = device

    def update_device(self, device: RemoteDeviceSession) -> None:
        if device.device_id not in self._devices:
            raise RemoteSessionError("Device is not registered")
        self._devices[device.device_id] = device

    def attach_transport(self, transport: SessionTransport) -> None:
        if transport.device_id not in self._devices:
            raise RemoteSessionError("Transport device is not registered")
        self._transports[transport.device_id] = transport

    def detach_transport(self, device_id: str) -> None:
        """A lost link marks affected sessions error; it never reopens them."""
        self._transports.pop(device_id, None)
        for session_id, (owner, _gen, _cap) in list(self._sessions.items()):
            if owner == device_id:
                self._sessions.pop(session_id, None)

    def discovery(self) -> SessionDiscoveryV1:
        targets = [
            SessionTargetV1(
                device_id=device.device_id,
                display_name=device.display_name,
                local=device.local,
                sessions=device.sessions,
                available=device.available and device.device_id in self._transports,
                unavailable_reason=(
                    None
                    if device.available and device.device_id in self._transports
                    else device.unavailable_reason or "device_unavailable"
                ),
            )
            for device in sorted(
                self._devices.values(), key=lambda item: item.device_id
            )
        ]
        return SessionDiscoveryV1(schema_version=1, targets=tuple(targets))

    def offers(self, device_id: str, capability_id: str) -> bool:
        """True when a connected device currently offers the capability."""
        try:
            self._authorized_device(device_id, capability_id)
        except RemoteSessionError:
            return False
        return True

    def has_session(self, session_id: str) -> bool:
        return session_id in self._sessions

    def _authorized_device(
        self, device_id: str, capability_id: str
    ) -> tuple[RemoteDeviceSession, SessionTransport]:
        device = self._devices.get(device_id)
        if device is None:
            raise RemoteSessionError("Session device is unknown")
        if not device.available:
            raise RemoteSessionError("Session device is unavailable")
        if capability_id not in device.sessions:
            raise RemoteSessionError("Device does not offer this session capability")
        transport = self._transports.get(device_id)
        if transport is None:
            raise RemoteSessionError("Session transport is not connected")
        return device, transport

    async def open(self, request: SessionOpenRequestV1) -> SessionOpenAcceptanceV1:
        device, transport = self._authorized_device(
            request.device_id, request.capability_id
        )
        acceptance = await transport.open(request)
        if acceptance.device_id != device.device_id:
            raise RemoteSessionError("Session acceptance device does not match")
        self._sessions[acceptance.session_id] = (
            device.device_id,
            device.authority_generation,
            request.capability_id,
        )
        return acceptance

    def _route(self, session_id: str) -> tuple[RemoteDeviceSession, SessionTransport]:
        binding = self._sessions.get(session_id)
        if binding is None:
            raise RemoteSessionError("Session is unknown or was disconnected")
        device_id, opened_generation, capability_id = binding
        device = self._devices.get(device_id)
        transport = self._transports.get(device_id)
        if device is None or transport is None:
            raise RemoteSessionError("Session device is no longer connected")
        if not device.available:
            raise RemoteSessionError("Session device authority is inactive")
        # Re-check authority on every use: a re-enrolled/revoked device or a
        # withdrawn capability must not keep an old session alive.
        if device.authority_generation != opened_generation:
            self._sessions.pop(session_id, None)
            raise RemoteSessionError("Session device authority has changed")
        if capability_id not in device.sessions:
            self._sessions.pop(session_id, None)
            raise RemoteSessionError("Session capability was withdrawn")
        return device, transport

    async def deliver(self, session_id: str, data: bytes) -> bytes:
        _device, transport = self._route(session_id)
        return await transport.deliver(session_id, data)

    async def control(
        self, session_id: str, message: Mapping[str, object]
    ) -> None:
        _device, transport = self._route(session_id)
        await transport.control(session_id, message)

    async def close(self, session_id: str, reason: str = "closed") -> None:
        _device, transport = self._route(session_id)
        await transport.close(session_id, reason)
        self._sessions.pop(session_id, None)

    def status(self, session_id: str) -> SessionStatusV1:
        device, _transport = self._route(session_id)
        now = self._now()
        return SessionStatusV1(
            session_id=session_id,
            state="active",
            device_id=device.device_id,
            provider_id="org.3mm.remote",
            created_at=now,
            expires_at=now + timedelta(seconds=1),
        )


@dataclass(slots=True)
class _LoopbackSession:
    device_id: str
    capability_id: str
    active: bool = True


class LoopbackSessionTransport:
    """In-process reference transport for tests and the local Agent boundary.

    It echoes bounded bytes and binds no process. It exists to prove the router
    and discovery work end to end without a live Hub↔Node link.
    """

    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self._sessions: dict[str, _LoopbackSession] = {}
        self._counter = 0

    async def open(self, request: SessionOpenRequestV1) -> SessionOpenAcceptanceV1:
        self._counter += 1
        # Session ids must be unique across devices, not just per transport.
        seed = f"{self.device_id}:{self._counter}".encode("utf-8")
        session_id = "ses_" + hashlib.sha256(seed).hexdigest()[:32]
        now = datetime.now(UTC)
        self._sessions[session_id] = _LoopbackSession(
            device_id=self.device_id, capability_id=request.capability_id
        )
        return SessionOpenAcceptanceV1(
            session_request_version=1,
            request_id=request.request_id,
            session_id=session_id,
            state="active",
            provider_id=request.provider_id,
            capability_id=request.capability_id,
            device_id=self.device_id,
            created_at=now,
            expires_at=now.replace(year=now.year + 1),
        )

    async def deliver(self, session_id: str, data: bytes) -> bytes:
        session = self._sessions.get(session_id)
        if session is None or not session.active:
            raise RemoteSessionError("Loopback session is unavailable")
        return b"remote:" + data

    async def control(
        self, session_id: str, message: Mapping[str, object]
    ) -> None:
        if session_id not in self._sessions:
            raise RemoteSessionError("Loopback session is unavailable")

    async def close(self, session_id: str, reason: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is not None:
            session.active = False


__all__ = [
    "RemoteSessionError",
    "RemoteDeviceSession",
    "SessionTransport",
    "RemoteSessionRouter",
    "LoopbackSessionTransport",
]
