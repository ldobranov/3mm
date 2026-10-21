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


def test_next_read_can_arrive_before_previous_reply_finishes_draining(monkeypatch):
    """Receiving bytes does not imply the sender's write task has returned."""
    import three_mm_runtime.session_worker as worker

    async def run():
        release_reply = asyncio.Event()
        next_read_received = asyncio.Event()
        tasks = []
        original_write, original_read = worker.write_packet, worker.read_packet

        async def delayed_reply(writer, value):
            await original_write(writer, value)
            if value.get("id") == 1 and "data" in value:
                await release_reply.wait()

        async def observe_request(reader):
            value = await original_read(reader)
            if value == {"id": 2, "op": "read"}:
                next_read_received.set()
            return value

        monkeypatch.setattr(worker, "write_packet", delayed_reply)
        monkeypatch.setattr(worker, "read_packet", observe_request)

        async def connected(reader, writer):
            tasks.append(asyncio.current_task())
            await serve(
                reader,
                writer,
                cgroup="/system.slice/system-test.slice/3mm-session-worker@fixture.service",
            )

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
            pass  # Protocol scheduling only, not OS cleanup/isolation evidence.

        monkeypatch.setattr(provider, "_wait_empty", fixture_cleanup)
        sid = "ses_" + "f" * 32
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
            first = await provider.read_output(sid)
            second = asyncio.create_task(provider.read_output(sid))
            await next_read_received.wait()
            release_reply.set()
            assert first + await second == (b"ready" * 10000)[: 2 * MAX_DATA]
            # Continued input/control must survive the same stream connection.
            assert await provider.receive(sid, b"next") == b"2"
            await provider.control(sid, {"action": "reset", "arguments": {"value": 8}})
            assert await provider.receive(sid, b"next") == b"9"
            await provider.close(sid, "test")
            await asyncio.gather(*tasks)
        finally:
            release_reply.set()
            await provider.close(sid, "test_cleanup")
            server.close()
            await server.wait_closed()
            await asyncio.gather(*tasks, return_exceptions=True)
            import sys

            sys.modules.pop("worker_fixture", None)

    asyncio.run(asyncio.wait_for(run(), 4))


def test_duplicate_idle_read_is_refused_without_starting_another_provider_read():
    """Only the response-in-flight race is accepted, not queued idle reads."""
    from three_mm_runtime.session_worker import write_packet

    async def run():
        failures = []
        finished = asyncio.Event()
        source = """
import asyncio
class Provider:
    provider_id = "org.example.counter"
    contract_version = "1.0"
    capability_ids = ("example.counter",)
    async def open(self, context): pass
    async def receive(self, sid, data): return b""
    async def control(self, sid, message): pass
    async def close(self, sid, reason): pass
    async def read_output(self, sid): await asyncio.Event().wait()
def create_provider(): return Provider()
"""

        async def connected(reader, writer):
            try:
                await serve(reader, writer, cgroup=None)
            except ValueError as exc:
                failures.append(str(exc))
            finally:
                finished.set()

        server = await asyncio.start_server(connected, "127.0.0.1", 0)
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", server.sockets[0].getsockname()[1]
        )
        artifact = wheel(source)
        try:
            await write_packet(
                writer,
                {
                    "version": 1,
                    "size": len(artifact),
                    "sha256": hashlib.sha256(artifact).hexdigest(),
                    "factory": "worker_fixture:create_provider",
                    "provider_id": "org.example.counter",
                    "context": {
                        "session_id": "ses_" + "a" * 32,
                        "device_id": "dev_" + "a" * 32,
                        "capability_id": "example.counter",
                        "access_mode": "write",
                        "options": {},
                    },
                },
            )
            writer.write(artifact)
            await writer.drain()
            assert (await read_packet(reader))["ready"] is True
            await write_packet(writer, {"id": 1, "op": "read"})
            await write_packet(writer, {"id": 2, "op": "read"})
            await finished.wait()
            assert failures == ["Session read is already pending"]
            assert await reader.read() == b""
        finally:
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            import sys

            sys.modules.pop("worker_fixture", None)

    asyncio.run(asyncio.wait_for(run(), 3))


@pytest.mark.parametrize("empty_cgroup", [True, False])
def test_disconnected_worker_cleanup_requires_os_confirmation(
    monkeypatch, empty_cgroup
):
    """Lost IPC is not a cleanup proof, nor a reason to ignore real OS proof."""

    async def run():
        class ClosedWriter:
            closed = False

            def write(self, _packet):
                assert not self.closed

            async def drain(self):
                pass

            def close(self):
                self.closed = True

            async def wait_closed(self):
                assert self.closed

        provider = SandboxedSessionProvider(
            wheel=wheel(),
            factory="worker_fixture:create_provider",
            provider_id="org.example.counter",
        )
        sid = "ses_" + "b" * 32
        provider.session_id = sid
        provider.cgroup = (
            "/system.slice/system-test.slice/3mm-session-worker@fixture.service"
        )
        provider.reader = asyncio.StreamReader()
        provider.writer = ClosedWriter()
        with pytest.raises(RuntimeError, match="cleanup identity"):
            await provider.close("ses_" + "d" * 32, "foreign")
        assert provider.closing is None and not provider.writer.closed
        provider.receiving = asyncio.create_task(provider._receive())
        reading = asyncio.create_task(provider.read_output(sid))
        # The first pending read has been admitted before the worker disappears.
        await asyncio.sleep(0)
        provider.reader.feed_eof()
        with pytest.raises(RuntimeError):
            await reading
        await provider.receiving
        confirmations = []

        async def confirm_os_cleanup():
            assert provider.writer.closed and provider.receiving.done()
            confirmations.append(provider.cgroup)
            if not empty_cgroup:
                raise RuntimeError("Session cgroup cleanup is unconfirmed")

        monkeypatch.setattr(provider, "_wait_empty", confirm_os_cleanup)
        if empty_cgroup:
            await asyncio.gather(
                provider.close(sid, "lost"), provider.close(sid, "lost")
            )
        else:
            with pytest.raises(RuntimeError, match="cgroup cleanup"):
                await provider.close(sid, "lost")
            with pytest.raises(RuntimeError, match="cgroup cleanup"):
                await provider.close(sid, "lost")
        assert confirmations == [provider.cgroup]
        # Confirmed cleanup never unspends the old session/open attempt.
        with pytest.raises(RuntimeError, match="already attempted"):
            await provider.open({"session_id": sid})

    asyncio.run(asyncio.wait_for(run(), 2))


def test_missing_cgroup_filesystem_is_not_evidence_of_worker_exit(monkeypatch):
    provider = SandboxedSessionProvider(
        wheel=wheel(),
        factory="worker_fixture:create_provider",
        provider_id="org.example.counter",
    )
    provider.cgroup = (
        "/system.slice/system-test.slice/3mm-session-worker@fixture.service"
    )
    from pathlib import Path

    original = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda path: (
            False
            if str(path) == "/sys/fs/cgroup/cgroup.controllers"
            else original(path)
        ),
    )
    with pytest.raises(RuntimeError, match="cgroup cleanup"):
        asyncio.run(provider._wait_empty())


def test_cgroup_mount_disappearing_during_observation_is_not_confirmed(monkeypatch):
    from pathlib import Path

    provider = SandboxedSessionProvider(
        wheel=wheel(),
        factory="worker_fixture:create_provider",
        provider_id="org.example.counter",
    )
    provider.cgroup = (
        "/system.slice/system-test.slice/3mm-session-worker@fixture.service"
    )
    checks = iter((True, False))
    original_is_file, original_read = Path.is_file, Path.read_text

    def is_file(path):
        if str(path) == "/sys/fs/cgroup/cgroup.controllers":
            return next(checks)
        return original_is_file(path)

    def read(path, *args, **kwargs):
        if str(path).endswith("3mm-session-worker@fixture.service/cgroup.events"):
            raise FileNotFoundError
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "is_file", is_file)
    monkeypatch.setattr(Path, "read_text", read)
    with pytest.raises(RuntimeError, match="cgroup cleanup"):
        asyncio.run(provider._wait_empty())


@pytest.mark.parametrize("cgroup", [None, "/tmp/unrelated", "/system.slice/../gone"])
def test_invalid_startup_cgroup_can_never_be_used_as_cleanup_evidence(
    monkeypatch, cgroup
):
    async def run():
        class Writer:
            def write(self, _data):
                pass

            async def drain(self):
                pass

            def close(self):
                pass

            async def wait_closed(self):
                pass

        provider = SandboxedSessionProvider(
            wheel=wheel(),
            factory="worker_fixture:create_provider",
            provider_id="org.example.counter",
        )
        reader = asyncio.StreamReader()
        raw = json.dumps({"ready": True, "cgroup": cgroup}).encode()
        reader.feed_data(struct.pack("!I", len(raw)) + raw)

        async def connect():
            return reader, Writer()

        monkeypatch.setattr(provider, "_connect", connect)
        sid = "ses_" + "e" * 32
        with pytest.raises(RuntimeError, match="cgroup identity"):
            await provider.open({"session_id": sid})
        assert provider.cgroup is None
        with pytest.raises(RuntimeError, match="cgroup cleanup"):
            await provider.close(sid, "invalid_startup")

    asyncio.run(asyncio.wait_for(run(), 2))


def test_disconnected_worker_with_no_cgroup_is_not_confirmed():
    async def run():
        provider = SandboxedSessionProvider(
            wheel=wheel(),
            factory="worker_fixture:create_provider",
            provider_id="org.example.counter",
        )
        # Startup has no trustworthy cgroup identity yet. No false success.
        provider.session_id = "ses_" + "c" * 32
        with pytest.raises(RuntimeError, match="cgroup cleanup"):
            await provider.close(provider.session_id, "startup_failed")

    asyncio.run(asyncio.wait_for(run(), 2))
