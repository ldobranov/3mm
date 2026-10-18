"""M21 remote session transport tests (WP3): routing, discovery, revocation."""

import asyncio

import pytest

from backend.services.interactive_session_transport import (
    LoopbackSessionTransport,
    RemoteDeviceSession,
    RemoteSessionError,
    RemoteSessionRouter,
)
from three_mm_protocol.interactive_session import SessionOpenRequestV1

DEVICE_A = "dev_" + "a" * 32
DEVICE_B = "dev_" + "b" * 32
CAPABILITY = "org.3mm.echo"


def _run(coro):
    return asyncio.run(coro)


def open_request(device_id=DEVICE_A, capability_id=CAPABILITY, request_id="req_1"):
    return SessionOpenRequestV1(
        request_id=request_id,
        provider_id="org.3mm.echo",
        capability_id=capability_id,
        device_id=device_id,
        access_mode="read",
        options={},
    )


def device(device_id=DEVICE_A, *, available=True, sessions=(CAPABILITY,), local=False):
    return RemoteDeviceSession(
        device_id=device_id,
        display_name="rasp-3mm",
        sessions=tuple(sessions),
        available=available,
        authority_generation=1,
        local=local,
    )


def test_discovery_lists_registered_devices():
    router = RemoteSessionRouter()
    router.register_device(device(DEVICE_A, local=True))
    router.register_device(device(DEVICE_B))
    discovery = router.discovery()
    assert {t.device_id for t in discovery.targets} == {DEVICE_A, DEVICE_B}


def test_discovery_marks_unavailable_without_transport():
    router = RemoteSessionRouter()
    router.register_device(device(DEVICE_A))
    discovery = router.discovery()
    target = discovery.targets[0]
    assert target.available is False
    assert target.unavailable_reason == "device_unavailable"


def test_discovery_available_after_transport_attach():
    router = RemoteSessionRouter()
    router.register_device(device(DEVICE_A))
    router.attach_transport(LoopbackSessionTransport(DEVICE_A))
    target = router.discovery().targets[0]
    assert target.available is True
    assert target.unavailable_reason is None


def test_open_and_deliver_remote_session():
    router = RemoteSessionRouter()
    router.register_device(device(DEVICE_A))
    router.attach_transport(LoopbackSessionTransport(DEVICE_A))

    async def scenario():
        acceptance = await router.open(open_request())
        assert acceptance.device_id == DEVICE_A
        outbound = await router.deliver(acceptance.session_id, b"hi")
        assert outbound == b"remote:hi"
        await router.close(acceptance.session_id)

    _run(scenario())


def test_open_unknown_device_fails_closed():
    router = RemoteSessionRouter()

    async def scenario():
        with pytest.raises(RemoteSessionError):
            await router.open(open_request())

    _run(scenario())


def test_open_offline_device_fails_closed():
    router = RemoteSessionRouter()
    router.register_device(device(DEVICE_A, available=False))
    router.attach_transport(LoopbackSessionTransport(DEVICE_A))

    async def scenario():
        with pytest.raises(RemoteSessionError):
            await router.open(open_request())

    _run(scenario())


def test_open_missing_capability_fails_closed():
    router = RemoteSessionRouter()
    router.register_device(device(DEVICE_A, sessions=("org.other.thing",)))
    router.attach_transport(LoopbackSessionTransport(DEVICE_A))

    async def scenario():
        with pytest.raises(RemoteSessionError):
            await router.open(open_request())

    _run(scenario())


def test_open_without_transport_fails_closed():
    router = RemoteSessionRouter()
    router.register_device(device(DEVICE_A))

    async def scenario():
        with pytest.raises(RemoteSessionError):
            await router.open(open_request())

    _run(scenario())


def test_multiplex_two_devices():
    router = RemoteSessionRouter()
    router.register_device(device(DEVICE_A))
    router.register_device(device(DEVICE_B))
    router.attach_transport(LoopbackSessionTransport(DEVICE_A))
    router.attach_transport(LoopbackSessionTransport(DEVICE_B))

    async def scenario():
        a = await router.open(open_request(DEVICE_A, request_id="req_a"))
        b = await router.open(open_request(DEVICE_B, request_id="req_b"))
        assert a.session_id != b.session_id
        assert await router.deliver(a.session_id, b"a") == b"remote:a"
        assert await router.deliver(b.session_id, b"b") == b"remote:b"

    _run(scenario())


def test_disconnect_marks_session_unknown():
    router = RemoteSessionRouter()
    router.register_device(device(DEVICE_A))
    router.attach_transport(LoopbackSessionTransport(DEVICE_A))

    async def scenario():
        acceptance = await router.open(open_request())
        router.detach_transport(DEVICE_A)
        with pytest.raises(RemoteSessionError):
            await router.deliver(acceptance.session_id, b"x")

    _run(scenario())


def test_authority_inactive_blocks_deliver():
    router = RemoteSessionRouter()
    router.register_device(device(DEVICE_A))
    router.attach_transport(LoopbackSessionTransport(DEVICE_A))

    async def scenario():
        acceptance = await router.open(open_request())
        router.update_device(device(DEVICE_A, available=False))
        with pytest.raises(RemoteSessionError):
            await router.deliver(acceptance.session_id, b"x")

    _run(scenario())


def test_duplicate_device_registration_rejected():
    router = RemoteSessionRouter()
    router.register_device(device(DEVICE_A))
    with pytest.raises(RemoteSessionError):
        router.register_device(device(DEVICE_A))


def test_transport_for_unregistered_device_rejected():
    router = RemoteSessionRouter()
    with pytest.raises(RemoteSessionError):
        router.attach_transport(LoopbackSessionTransport(DEVICE_A))


def test_status_after_open():
    router = RemoteSessionRouter()
    router.register_device(device(DEVICE_A))
    router.attach_transport(LoopbackSessionTransport(DEVICE_A))

    async def scenario():
        acceptance = await router.open(open_request())
        status = router.status(acceptance.session_id)
        assert status.state == "active"
        assert status.device_id == DEVICE_A

    _run(scenario())


def test_authority_generation_change_blocks_deliver():
    router = RemoteSessionRouter()
    router.register_device(device(DEVICE_A))
    router.attach_transport(LoopbackSessionTransport(DEVICE_A))

    async def scenario():
        acceptance = await router.open(open_request())
        router.update_device(
            RemoteDeviceSession(
                device_id=DEVICE_A,
                display_name="rasp-3mm",
                sessions=(CAPABILITY,),
                available=True,
                authority_generation=2,
            )
        )
        with pytest.raises(RemoteSessionError):
            await router.deliver(acceptance.session_id, b"x")

    _run(scenario())


def test_capability_withdrawal_blocks_deliver():
    router = RemoteSessionRouter()
    router.register_device(device(DEVICE_A))
    router.attach_transport(LoopbackSessionTransport(DEVICE_A))

    async def scenario():
        acceptance = await router.open(open_request())
        router.update_device(
            RemoteDeviceSession(
                device_id=DEVICE_A,
                display_name="rasp-3mm",
                sessions=(),
                available=True,
                authority_generation=1,
            )
        )
        with pytest.raises(RemoteSessionError):
            await router.deliver(acceptance.session_id, b"x")

    _run(scenario())
