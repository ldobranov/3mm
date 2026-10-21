"""Independent M21 output, bounded buffering and explicit checker semantics."""

import asyncio

import pytest

from three_mm_protocol.interactive_session import (
    MAX_SESSION_PAYLOAD_BYTES,
    decode_session_frame,
)
from three_mm_runtime.session_output import SessionOutputError, pump_session_output

SESSION = "ses_" + "1" * 32


class OutputProvider:
    def __init__(self, outputs=()):
        self.outputs = asyncio.Queue()
        for output in outputs:
            self.outputs.put_nowait(output)
        self.reads = 0
        self.closed = []

    async def read_output(self, session_id):
        assert session_id == SESSION
        self.reads += 1
        return await self.outputs.get()

    async def close(self, session_id, reason):
        self.closed.append((session_id, reason))


async def allowed():
    return None


def test_independent_output_is_framed_without_input_or_routing_modes():
    async def scenario():
        provider = OutputProvider((b"prompt> ", b"background output\n", None))
        sent = []

        async def send(frame):
            sent.append(decode_session_frame(frame))

        await pump_session_output(provider, SESSION, send, authorize=allowed)
        assert [payload for _, payload in sent] == [b"prompt> ", b"background output\n"]
        assert [header.seq for header, _ in sent] == [1, 2]
        assert all(header.session_id == SESSION for header, _ in sent)
        assert provider.closed == [(SESSION, "output_eof")]

    asyncio.run(scenario())


def test_slow_transport_applies_backpressure_before_next_read():
    async def scenario():
        provider = OutputProvider((b"a", b"b", None))
        sending, release = asyncio.Event(), asyncio.Event()

        async def send(frame):
            sending.set()
            await release.wait()

        task = asyncio.create_task(
            pump_session_output(provider, SESSION, send, authorize=allowed)
        )
        await asyncio.wait_for(sending.wait(), 1)
        assert provider.reads == 1
        release.set()
        await asyncio.wait_for(task, 1)
        assert provider.reads == 3

    asyncio.run(scenario())


@pytest.mark.parametrize("waiting", ["read", "send"])
def test_revocation_while_idle_or_transport_waits_closes_without_replay(waiting):
    async def scenario():
        provider = OutputProvider((b"a",) if waiting == "send" else ())
        checked, pending = asyncio.Event(), asyncio.Event()
        revoked = False
        sends = []

        async def authorize():
            checked.set()
            if revoked:
                raise PermissionError("revoked")

        async def send(frame):
            sends.append(frame)
            pending.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(
            pump_session_output(
                provider, SESSION, send, authorize=authorize, check_interval=0.01
            )
        )
        await asyncio.wait_for(checked.wait(), 1)
        if waiting == "send":
            await asyncio.wait_for(pending.wait(), 1)
        revoked = True
        with pytest.raises(SessionOutputError, match="authority"):
            await asyncio.wait_for(task, 1)
        assert len(sends) == (1 if waiting == "send" else 0)
        assert len(provider.closed) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "output",
    [b"", bytearray(b"a"), "text", b"a" * (MAX_SESSION_PAYLOAD_BYTES + 1)],
    ids=["empty", "mutable", "text", "oversized"],
)
def test_invalid_or_oversized_provider_output_is_not_sent(output):
    async def scenario():
        provider = OutputProvider((output,))

        async def send(frame):
            pytest.fail("invalid output was sent")

        with pytest.raises(SessionOutputError, match="output is invalid"):
            await pump_session_output(provider, SESSION, send, authorize=allowed)
        assert len(provider.closed) == 1

    asyncio.run(scenario())


def test_pending_read_is_cancelled_and_provider_closed_on_disconnect():
    async def scenario():
        provider = OutputProvider()

        async def send(frame):
            pytest.fail("no output expected")

        task = asyncio.create_task(
            pump_session_output(provider, SESSION, send, authorize=allowed)
        )
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert provider.closed == [(SESSION, "output_cancelled")]

    asyncio.run(scenario())


@pytest.mark.parametrize("result", [True, False, "allowed"])
def test_checker_must_confirm_by_returning_none_not_a_truthy_claim(result):
    async def scenario():
        provider = OutputProvider((b"a",))

        async def authorize():
            return result

        async def send(frame):
            pytest.fail("unconfirmed authority sent data")

        with pytest.raises(SessionOutputError, match="authority"):
            await pump_session_output(provider, SESSION, send, authorize=authorize)
        assert provider.reads == 0
        assert len(provider.closed) == 1

    asyncio.run(scenario())


def test_transport_timeout_and_cleanup_failure_are_visible():
    async def scenario():
        provider = OutputProvider((b"a",))

        async def send(frame):
            await asyncio.Event().wait()

        with pytest.raises(SessionOutputError, match="timed out"):
            await pump_session_output(
                provider, SESSION, send, authorize=allowed, send_timeout=0.01
            )
        assert len(provider.closed) == 1

        async def failed_close(session_id, reason):
            raise RuntimeError("cleanup failure")

        provider.close = failed_close
        provider.outputs.put_nowait(None)
        with pytest.raises(SessionOutputError, match="cleanup is unconfirmed"):
            await pump_session_output(provider, SESSION, send, authorize=allowed)

    asyncio.run(scenario())


def test_repeated_disconnect_does_not_cancel_in_progress_cleanup():
    async def scenario():
        provider = OutputProvider()
        cleaning, finish = asyncio.Event(), asyncio.Event()

        async def close(session_id, reason):
            cleaning.set()
            await finish.wait()
            provider.closed.append((session_id, reason))

        provider.close = close

        async def send(frame):
            pytest.fail("no output expected")

        task = asyncio.create_task(
            pump_session_output(provider, SESSION, send, authorize=allowed)
        )
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.wait_for(cleaning.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert len(provider.closed) == 1

    asyncio.run(scenario())


def test_revocation_during_read_discards_completed_output():
    async def scenario():
        provider = OutputProvider()
        revoked = False

        async def authorize():
            if revoked:
                raise PermissionError("binding changed during read")

        async def read(session_id):
            nonlocal revoked
            revoked = True
            return b"private output"

        provider.read_output = read

        async def send(frame):
            pytest.fail("output completed after revoke must not be disclosed")

        with pytest.raises(SessionOutputError, match="authority"):
            await pump_session_output(provider, SESSION, send, authorize=authorize)
        assert len(provider.closed) == 1

    asyncio.run(scenario())


def test_uncertain_send_is_not_repeated_and_next_output_is_not_read():
    async def scenario():
        provider = OutputProvider((b"first", b"next", None))
        sends = 0

        async def send(frame):
            nonlocal sends
            sends += 1
            raise BrokenPipeError("transport lost after possible send")

        with pytest.raises(BrokenPipeError):
            await pump_session_output(provider, SESSION, send, authorize=allowed)
        assert sends == 1 and provider.reads == 1
        assert len(provider.closed) == 1

    asyncio.run(scenario())
