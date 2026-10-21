"""Generic SDK output over Agent host; no terminal names or live services."""

import asyncio
import json

import pytest

from agent.session_transport import AgentSessionHost, AgentSessionTransportError
from three_mm_application_sdk.session import SessionOutputProvider
from three_mm_protocol.interactive_session import (
    decode_session_frame,
    encode_session_frame,
)
from three_mm_runtime.session_output import (
    SessionOutputCleanupError,
    SessionOutputError,
)


class Provider:
    provider_id = "org.example.stream"
    capability_ids = ("org.example.output",)
    control_actions = ()

    def __init__(self):
        self.output = asyncio.Queue()
        self.closed = []

    async def open(self, context):
        self.session_id = context["session_id"]

    async def read_output(self, session_id):
        return await self.output.get()

    async def receive(self, session_id, data):
        return b""

    async def control(self, session_id, message):
        pass

    async def close(self, session_id, reason):
        self.closed.append(session_id)


async def opened():
    provider = Provider()
    assert isinstance(provider, SessionOutputProvider)
    host = AgentSessionHost()
    host.register_provider(provider)
    reply = json.loads(
        await host.handle_text(
            json.dumps(
                {
                    "op": "open",
                    "request": {
                        "request_id": "stream_test",
                        "provider_id": provider.provider_id,
                        "capability_id": provider.capability_ids[0],
                        "device_id": "dev_" + "a" * 32,
                    },
                }
            )
        )
    )
    return host, provider, reply["acceptance"]["session_id"]


async def allowed():
    return None


def test_sdk_output_and_explicit_close_clean_up_once():
    async def scenario():
        host, provider, session_id = await opened()
        got = asyncio.Event()

        async def send(frame):
            header, output = decode_session_frame(frame)
            assert header.session_id == session_id and output == b"independent"
            got.set()

        pump = asyncio.create_task(
            host.pump_output(session_id, send, authorize=allowed)
        )
        provider.output.put_nowait(b"independent")
        await asyncio.wait_for(got.wait(), 1)
        response = json.loads(
            await host.handle_text(
                json.dumps({"op": "close", "session_id": session_id})
            )
        )
        assert response["op"] == "ok" and pump.cancelled()
        assert provider.closed == [session_id]
        assert not host._sessions and not host._output_tasks

    asyncio.run(scenario())


def test_two_consumers_or_invalid_checker_do_not_destroy_existing_session():
    async def scenario():
        host, provider, session_id = await opened()

        async def send(frame):
            pass

        for kwargs in (
            {"authorize": None},
            {"authorize": allowed, "check_interval": False},
        ):
            with pytest.raises(AgentSessionTransportError):
                await host.pump_output(session_id, send, **kwargs)
            assert session_id in host._sessions and not provider.closed
        running = asyncio.create_task(
            host.pump_output(session_id, send, authorize=allowed)
        )
        await asyncio.sleep(0)
        with pytest.raises(AgentSessionTransportError, match="consumer"):
            await host.pump_output(session_id, send, authorize=allowed)
        await host.handle_text(json.dumps({"op": "close", "session_id": session_id}))
        assert running.cancelled() and provider.closed == [session_id]

    asyncio.run(scenario())


def test_revocation_without_input_removes_session_and_stops_future_use():
    async def scenario():
        host, provider, session_id = await opened()
        revoked = False

        async def authorize():
            if revoked:
                raise PermissionError("revoked")

        async def send(frame):
            pytest.fail("no provider output")

        task = asyncio.create_task(
            host.pump_output(session_id, send, authorize=authorize, check_interval=0.01)
        )
        await asyncio.sleep(0.01)
        revoked = True
        with pytest.raises(SessionOutputError, match="authority"):
            await asyncio.wait_for(task, 1)
        assert provider.closed == [session_id]
        with pytest.raises(AgentSessionTransportError, match="unknown"):
            await host.handle_binary(
                encode_session_frame(op="data", seq=1, session_id=session_id)
            )

    asyncio.run(scenario())


def test_failed_cleanup_is_fenced_and_ownership_is_retained():
    async def scenario():
        host, provider, session_id = await opened()

        async def failed_close(session_id, reason):
            raise RuntimeError("cleanup refused")

        provider.close = failed_close
        provider.output.put_nowait(None)

        async def send(frame):
            pytest.fail("no output expected")

        with pytest.raises(SessionOutputCleanupError):
            await host.pump_output(session_id, send, authorize=allowed)
        assert session_id in host._sessions and session_id in host._unconfirmed_cleanup
        with pytest.raises(AgentSessionTransportError, match="unconfirmed"):
            await host.handle_binary(
                encode_session_frame(op="data", seq=1, session_id=session_id)
            )

    asyncio.run(scenario())


def test_cancelled_close_request_does_not_claim_success_or_abandon_cleanup():
    async def scenario():
        host, provider, session_id = await opened()
        cleaning, release = asyncio.Event(), asyncio.Event()

        async def close(sid, reason):
            cleaning.set()
            await release.wait()
            provider.closed.append(sid)

        provider.close = close

        async def send(frame):
            pytest.fail("no output expected")

        output = asyncio.create_task(
            host.pump_output(session_id, send, authorize=allowed)
        )
        await asyncio.sleep(0)
        closing = asyncio.create_task(
            host.handle_text(json.dumps({"op": "close", "session_id": session_id}))
        )
        await asyncio.wait_for(cleaning.wait(), 1)
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert not output.done() and session_id in host._sessions
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(output, 1)
        assert provider.closed == [session_id] and not host._sessions

    asyncio.run(scenario())
