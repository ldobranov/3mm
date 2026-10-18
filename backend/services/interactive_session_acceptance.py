"""M21 local acceptance harness (WP5).

Deterministic, in-process acceptance over the public M21 contracts. It proves
the Definition of Done — a *second, independent* interactive provider works
without Core changes — and exercises the negative security scenarios. It binds
no process, opens no socket and performs no OS isolation; live Standalone/Hub/
Zero W acceptance remains a separate, explicitly approved step.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Mapping

from backend.services.interactive_session_transport import (
    LoopbackSessionTransport,
    RemoteDeviceSession,
    RemoteSessionError,
    RemoteSessionRouter,
)
from backend.services.interactive_sessions import (
    EchoSessionProvider,
    InteractiveSessionError,
    LocalSessionManager,
    SessionTicketStore,
)
from three_mm_application_sdk.session import (
    SessionProvider,
    validate_session_provider_metadata,
)
from three_mm_protocol.interactive_session import (
    MAX_SESSION_PAYLOAD_BYTES,
    SessionOpenRequestV1,
)

DEVICE_LOCAL = "dev_" + "1" * 32
DEVICE_REMOTE = "dev_" + "2" * 32
DEVICE_NO_CAP = "dev_" + "3" * 32
ECHO_CAPABILITY = "org.3mm.echo"
COUNTER_CAPABILITY = "org.3mm.counter"


@dataclass(frozen=True, slots=True)
class AcceptanceCriterion:
    criterion_id: str
    description: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class AcceptanceReport:
    criteria: tuple[AcceptanceCriterion, ...]

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.criteria)

    def failed(self) -> tuple[AcceptanceCriterion, ...]:
        return tuple(item for item in self.criteria if not item.passed)


class CounterSessionProvider:
    """Second, independent provider: returns an incrementing counter.

    Deliberately not an echo and not a terminal. It implements only the public
    provider contract, proving a new interactive provider needs no Core change
    (the M21 Definition of Done).
    """

    provider_id = "org.3mm.counter"
    capability_ids = (COUNTER_CAPABILITY,)
    control_actions = ("reset",)

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    async def open(self, context: Mapping[str, object]) -> None:
        self._counts[str(context["session_id"])] = 0

    async def receive(self, session_id: str, data: bytes) -> bytes:
        if session_id not in self._counts:
            raise InteractiveSessionError("Counter session is unavailable")
        self._counts[session_id] += 1
        return f"count:{self._counts[session_id]}".encode("ascii")

    async def control(self, session_id: str, message: Mapping[str, object]) -> None:
        if message.get("action") == "reset" and session_id in self._counts:
            self._counts[session_id] = 0

    async def close(self, session_id: str, reason: str) -> None:
        self._counts.pop(session_id, None)


def _public_sdk_contract_criteria() -> list[AcceptanceCriterion]:
    """Prove the reference providers satisfy the *public* SDK contract.

    The Core runtime adapter is structurally identical to the SDK
    ``SessionProvider`` protocol, so a provider written against the SDK works
    without Core changes. This is the Definition of Done, checked explicitly.
    """
    criteria: list[AcceptanceCriterion] = []
    counter = CounterSessionProvider()
    echo = EchoSessionProvider()
    criteria.append(
        _criterion(
            "public_sdk_protocol",
            "Reference providers satisfy the public SDK SessionProvider protocol",
            isinstance(counter, SessionProvider) and isinstance(echo, SessionProvider),
        )
    )
    metadata_ok = True
    try:
        validate_session_provider_metadata(
            provider_id=counter.provider_id,
            contract_version="1.0",
            capability_ids=counter.capability_ids,
            control_actions=counter.control_actions,
        )
    except Exception:  # noqa: BLE001 - any failure means the contract is unmet
        metadata_ok = False
    criteria.append(
        _criterion(
            "public_sdk_metadata",
            "Reference provider metadata validates against the public SDK",
            metadata_ok,
        )
    )
    return criteria


def _request(provider_id, capability_id, device_id, request_id):
    return SessionOpenRequestV1(
        request_id=request_id,
        provider_id=provider_id,
        capability_id=capability_id,
        device_id=device_id,
        access_mode="read",
        options={},
    )


def _criterion(criterion_id, description, passed, detail=""):
    return AcceptanceCriterion(criterion_id, description, passed, detail)


async def _local_scenarios() -> list[AcceptanceCriterion]:
    criteria: list[AcceptanceCriterion] = []
    manager = LocalSessionManager(max_sessions=4)
    manager.register_provider(EchoSessionProvider())
    manager.register_provider(CounterSessionProvider())

    acceptance = await manager.open(
        _request("org.3mm.counter", COUNTER_CAPABILITY, DEVICE_LOCAL, "counter_1"),
        user_id=7,
    )
    first = await manager.deliver(acceptance.session_id, b"x", user_id=7)
    second = await manager.deliver(acceptance.session_id, b"x", user_id=7)
    criteria.append(
        _criterion(
            "second_provider",
            "A second independent provider works without Core changes",
            first == b"count:1" and second == b"count:2",
            f"first={first!r} second={second!r}",
        )
    )

    denied = False
    try:
        await manager.deliver(acceptance.session_id, b"x", user_id=8)
    except InteractiveSessionError:
        denied = True
    criteria.append(
        _criterion(
            "cross_user_denied",
            "A session cannot be used by another user",
            denied,
        )
    )

    oversized = False
    try:
        await manager.deliver(
            acceptance.session_id, b"x" * (MAX_SESSION_PAYLOAD_BYTES + 1), user_id=7
        )
    except InteractiveSessionError:
        oversized = True
    criteria.append(
        _criterion(
            "oversized_refused",
            "Payloads above the bound are refused",
            oversized,
        )
    )

    manager.revoke_provider("org.3mm.counter")
    revoked = False
    try:
        await manager.deliver(acceptance.session_id, b"x", user_id=7)
    except InteractiveSessionError:
        revoked = True
    criteria.append(
        _criterion(
            "revocation_terminates",
            "Revoking a provider terminates active access",
            revoked,
        )
    )

    store = SessionTicketStore(ttl_seconds=30)
    issue = store.issue(7)
    store.redeem(issue.ticket)
    replay_denied = False
    try:
        store.redeem(issue.ticket)
    except InteractiveSessionError:
        replay_denied = True
    criteria.append(
        _criterion(
            "ticket_single_use",
            "A session ticket cannot be replayed",
            replay_denied,
        )
    )

    return criteria


async def _remote_scenarios() -> list[AcceptanceCriterion]:
    criteria: list[AcceptanceCriterion] = []
    router = RemoteSessionRouter()
    router.register_device(
        RemoteDeviceSession(
            device_id=DEVICE_LOCAL,
            display_name="rasp-3mm",
            sessions=(ECHO_CAPABILITY,),
            available=True,
            authority_generation=1,
            local=True,
        )
    )
    router.register_device(
        RemoteDeviceSession(
            device_id=DEVICE_REMOTE,
            display_name="rasp-3mmw",
            sessions=(ECHO_CAPABILITY,),
            available=True,
            authority_generation=1,
        )
    )
    router.attach_transport(LoopbackSessionTransport(DEVICE_LOCAL))
    router.attach_transport(LoopbackSessionTransport(DEVICE_REMOTE))

    discovery = router.discovery()
    both_available = len(discovery.targets) == 2 and all(
        target.available for target in discovery.targets
    )
    criteria.append(
        _criterion(
            "discovery_local_and_remote",
            "Discovery lists local and remote devices as available",
            both_available,
        )
    )

    local = await router.open(
        _request("org.3mm.echo", ECHO_CAPABILITY, DEVICE_LOCAL, "local_1")
    )
    remote = await router.open(
        _request("org.3mm.echo", ECHO_CAPABILITY, DEVICE_REMOTE, "remote_1")
    )
    local_out = await router.deliver(local.session_id, b"a")
    remote_out = await router.deliver(remote.session_id, b"b")
    criteria.append(
        _criterion(
            "multiplex_independent",
            "Two devices carry independent sessions",
            local.session_id != remote.session_id
            and local_out == b"remote:a"
            and remote_out == b"remote:b",
        )
    )

    router.register_device(
        RemoteDeviceSession(
            device_id=DEVICE_NO_CAP,
            display_name="no-session",
            sessions=(),
            available=True,
            authority_generation=1,
        )
    )
    router.attach_transport(LoopbackSessionTransport(DEVICE_NO_CAP))
    refused = False
    try:
        await router.open(
            _request("org.3mm.echo", ECHO_CAPABILITY, DEVICE_NO_CAP, "no_cap")
        )
    except RemoteSessionError:
        refused = True
    criteria.append(
        _criterion(
            "missing_capability_refused",
            "A device without the capability cannot start a session",
            refused,
        )
    )

    router.detach_transport(DEVICE_REMOTE)
    disconnected = False
    try:
        await router.deliver(remote.session_id, b"x")
    except RemoteSessionError:
        disconnected = True
    criteria.append(
        _criterion(
            "disconnect_no_replay",
            "A lost link does not silently reopen a session",
            disconnected,
        )
    )

    return criteria


def run_local_session_acceptance() -> AcceptanceReport:
    """Run the deterministic local acceptance and return a structured report."""
    criteria = _public_sdk_contract_criteria()
    criteria += asyncio.run(_local_scenarios())
    criteria += asyncio.run(_remote_scenarios())
    return AcceptanceReport(criteria=tuple(criteria))


__all__ = [
    "AcceptanceCriterion",
    "AcceptanceReport",
    "CounterSessionProvider",
    "run_local_session_acceptance",
]
