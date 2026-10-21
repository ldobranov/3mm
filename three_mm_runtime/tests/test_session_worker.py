"""Bounded private IPC, independently of optional systemd acceptance."""

import asyncio
import hashlib
import io
import json
import struct
import zipfile

import pytest

from three_mm_runtime.session_worker import (
    MAX_DATA,
    MAX_PACKET,
    read_packet,
    serve,
    validate_wheel,
    verify_sandbox,
)
from three_mm_runtime.session_worker_client import SandboxedSessionProvider


def wheel(source=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "worker_fixture.py",
            source
            or """
class Provider:
    provider_id = "org.example.counter"
    contract_version = "1.0"
    capability_ids = ("example.counter",)
    control_actions = ("reset",)
    async def open(self, context): self.count = 0
    async def read_output(self, sid):
        if self.count == 0:
            self.count = 1
            return b"ready" * 10000
        import asyncio
        await asyncio.Event().wait()
    async def receive(self, sid, data):
        self.count += 1
        return str(self.count).encode()
    async def control(self, sid, message):
        assert set(message) == {"action", "arguments"}
        self.count = message["arguments"]["value"]
    async def close(self, sid, reason): pass
def create_provider(): return Provider()
""",
        )
        archive.writestr(
            "fixture-1.0.dist-info/WHEEL", "Root-Is-Purelib: true\nTag: py3-none-any\n"
        )
    return stream.getvalue()


def test_artifact_checks_reject_tampering_native_wheels_and_unsafe_paths():
    data = wheel()
    validate_wheel(data, hashlib.sha256(data).hexdigest())
    with pytest.raises(ValueError):
        validate_wheel(data, "0" * 64)
    for name in ("../secret", "/secret", "lib/native.so", "injection.pth"):
        stream = io.BytesIO(data)
        with zipfile.ZipFile(stream, "a") as archive:
            archive.writestr(name, "invalid")
        changed = stream.getvalue()
        with pytest.raises(ValueError):
            validate_wheel(changed, hashlib.sha256(changed).hexdigest())


def test_packet_limits_and_duplicate_fields():
    async def run():
        for raw in (b'{"id":1,"id":2}', b"[]"):
            reader = asyncio.StreamReader()
            reader.feed_data(struct.pack("!I", len(raw)) + raw)
            with pytest.raises(ValueError):
                await read_packet(reader)
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack("!I", MAX_PACKET + 1))
        with pytest.raises(ValueError):
            await read_packet(reader)

    asyncio.run(run())


def test_direct_worker_start_without_os_sandbox_is_refused():
    with pytest.raises(RuntimeError):
        verify_sandbox()


def test_sdk_ipc_independent_output_input_control_bounds_and_cleanup(monkeypatch):
    async def run():
        tasks = []

        async def connected(reader, writer):
            task = asyncio.current_task()
            tasks.append(task)
            try:
                await serve(
                    reader,
                    writer,
                    cgroup="/system.slice/system-test.slice/3mm-session-worker@fixture.service",
                )
            except (ConnectionError, asyncio.IncompleteReadError):
                pass

        server = await asyncio.start_server(connected, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        provider = SandboxedSessionProvider(
            wheel=wheel(),
            factory="worker_fixture:create_provider",
            provider_id="org.example.counter",
        )
        monkeypatch.setattr(
            provider, "_connect", lambda: asyncio.open_connection("127.0.0.1", port)
        )

        async def fixture_cleanup():
            pass  # OS cleanup is proved by the separate opt-in systemd test.

        monkeypatch.setattr(provider, "_wait_empty", fixture_cleanup)
        sid = "ses_" + "a" * 32
        try:
            await provider.open(
                {
                    "session_id": sid,
                    "device_id": "dev_" + "a" * 32,
                    "capability_id": "example.counter",
                    "access_mode": "write",
                    "options": {},
                }
            )
            output = b"".join([await provider.read_output(sid) for _ in range(4)])
            assert output == b"ready" * 10000  # Split; no unbounded queued output.
            assert await provider.receive(sid, b"next") == b"2"
            await provider.control(sid, {"action": "reset", "arguments": {"value": 10}})
            assert await provider.receive(sid, b"next") == b"11"
            waiting = asyncio.create_task(provider.read_output(sid))
            await asyncio.sleep(0.01)
            with pytest.raises(ValueError):
                await provider.receive(sid, b"x" * (MAX_DATA + 1))
            await provider.close(sid, "test")
            await asyncio.gather(waiting, return_exceptions=True)
            await asyncio.gather(*tasks)
            with pytest.raises(RuntimeError):
                await provider.open({"session_id": sid})
        finally:
            server.close()
            await server.wait_closed()
            # Do not contaminate later factory imports in this test interpreter.
            import sys

            sys.modules.pop("worker_fixture", None)

    asyncio.run(asyncio.wait_for(run(), 8))
