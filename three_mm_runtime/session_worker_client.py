"""Private Core-to-sandbox adapter implementing the public SDK provider contract.

Not discovery, permission admission or a process launcher. Construct only from
an exact installed/reviewed provider artifact, after the M20 source resolver.
No browser data selects the socket, factory, wheel or provider identity.
"""

import asyncio
import base64
import hashlib
import re
import socket
import stat
import struct
from pathlib import Path

from three_mm_runtime.session_worker import (
    MAX_DATA,
    read_packet,
    validate_wheel,
    write_packet,
)

SOCKET_PATH = Path("/run/3mm-sessions/provider.sock")


class SessionChannelProvider:
    """Private bounded request channel; concrete executors prove their own cleanup."""

    def __init__(self):
        self.session_id = None
        self.reader = self.writer = self.receiving = None
        self.pending = {}
        self.sequence = 0
        self.sending = asyncio.Lock()
        self.reading = asyncio.Lock()
        self.closing = None
        self.cgroup = None

    async def _connect(self):
        # Check every ancestor, not a caller-selected path or stale is_socket().
        for path in (SOCKET_PATH, *SOCKET_PATH.parents):
            info = path.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or info.st_uid != 0
                or info.st_mode & 0o002
                or path != SOCKET_PATH
                and info.st_mode & 0o020
            ):
                raise RuntimeError("Session supervisor path is untrusted")
        if not stat.S_ISSOCK(SOCKET_PATH.lstat().st_mode):
            raise RuntimeError("Session supervisor is unavailable")
        reader, writer = await asyncio.open_unix_connection(
            str(SOCKET_PATH), limit=65536
        )
        connection = writer.get_extra_info("socket")
        _pid, uid, _gid = struct.unpack(
            "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        )
        if uid != 0:
            writer.close()
            await writer.wait_closed()
            raise RuntimeError("Session supervisor identity is untrusted")
        return reader, writer

    async def open(self, context):
        if self.session_id is not None:
            raise RuntimeError("Session open was already attempted")
        self.session_id = context["session_id"]  # Spent even on uncertain startup.
        try:
            self.reader, self.writer = await asyncio.wait_for(self._connect(), 3)
            await write_packet(
                self.writer,
                {
                    "version": 1,
                    "size": len(self.wheel),
                    "sha256": self.sha256,
                    "factory": self.factory,
                    "provider_id": self.provider_id,
                    "context": context,
                },
            )
            # Stream the bounded wheel; do not buffer another copy in transport.
            for start in range(0, len(self.wheel), 65536):
                self.writer.write(self.wheel[start : start + 65536])
                await asyncio.wait_for(self.writer.drain(), 5)
            ready = await asyncio.wait_for(read_packet(self.reader), 90)
            if set(ready) != {"ready", "cgroup"} or ready["ready"] is not True:
                raise RuntimeError("Session startup was not confirmed")
            cgroup = ready["cgroup"]
            if (
                type(cgroup) is not str
                or not cgroup.startswith("/system.slice/")
                or ".." in cgroup.split("/")
                or re.fullmatch(
                    r"/system.slice/[A-Za-z0-9_@.\\:/-]+/3mm-session-worker[^/]*@[^/]+\.service",
                    cgroup,
                )
                is None
            ):
                raise RuntimeError("Session cgroup identity is unavailable")
            self.cgroup = cgroup  # Only a validated startup identity can prove cleanup.
            self.receiving = asyncio.create_task(self._receive())
        except BaseException:
            if self.writer is not None:
                self.writer.close()
            raise

    async def _receive(self):
        try:
            while True:
                response = await read_packet(self.reader)
                call_id = response.get("id")
                if type(call_id) is not int or call_id not in self.pending:
                    raise RuntimeError("Unexpected session IPC response")
                future = self.pending.pop(call_id)
                if not future.done():
                    future.set_result(response)
        except BaseException:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(
                        RuntimeError("Session supervisor disconnected")
                    )
            self.pending.clear()
            if self.writer is not None:
                self.writer.close()

    async def _call(self, session_id, op, **values):
        if (
            session_id != self.session_id
            or self.receiving is None
            or self.receiving.done()
        ):
            raise RuntimeError("Session supervisor is unavailable")
        async with self.sending:
            if len(self.pending) >= 3:
                raise RuntimeError("Session IPC capacity is unavailable")
            self.sequence += 1
            call_id = self.sequence
            future = asyncio.get_running_loop().create_future()
            self.pending[call_id] = future
            await write_packet(self.writer, {"id": call_id, "op": op, **values})
        try:
            # Reads are idle until output; owning authority/lifetime monitors
            # remain independent and can close the exact connection.
            response = (
                await future if op == "read" else await asyncio.wait_for(future, 6)
            )
        except BaseException:
            future.cancel()  # Never resend a command whose outcome is uncertain.
            raise
        if set(response) != {
            "id",
            "data" if op in ("read", "input") else "closed" if op == "close" else "ok",
        }:
            raise RuntimeError("Invalid session IPC response")
        return response

    async def read_output(self, session_id):
        async with self.reading:
            response = await self._call(session_id, "read")
            if response["data"] is None:
                return None
            data = base64.b64decode(response["data"], validate=True)
            if not 1 <= len(data) <= MAX_DATA:
                raise RuntimeError("Session output exceeds bounds")
            return data

    async def receive(self, session_id, data):
        if type(data) is not bytes or not 1 <= len(data) <= MAX_DATA:
            raise ValueError("Session input exceeds IPC bounds")
        response = await self._call(
            session_id, "input", data=base64.b64encode(data).decode()
        )
        result = base64.b64decode(response["data"], validate=True)
        if len(result) > MAX_DATA:
            raise RuntimeError("Session response exceeds bounds")
        return result

    async def control(self, session_id, message):
        if (await self._call(session_id, "control", message=message))["ok"] is not True:
            raise RuntimeError("Session control was not confirmed")

    async def close(self, session_id, reason):
        if session_id != self.session_id or self.session_id is None:
            raise RuntimeError("Session cleanup identity is unavailable")
        if self.closing is None:
            self.closing = asyncio.create_task(self._close(session_id))
        await asyncio.shield(self.closing)

    async def _close(self, session_id):
        try:
            if self.receiving is not None and not self.receiving.done():
                try:
                    await self._call(session_id, "close")
                except Exception:
                    # A lost reply is not a cleanup proof. Close the channel,
                    # then require actual OS evidence for the pinned cgroup.
                    # Input/control failures still reach their original caller;
                    # no operation is resent or reported as completed here.
                    pass
        finally:
            if self.writer is not None:
                self.writer.close()
                try:
                    await self.writer.wait_closed()
                except (ConnectionError, OSError):
                    pass  # Kernel cgroup evidence, not IPC EOF, decides cleanup.
            if self.receiving is not None:
                self.receiving.cancel()
                await asyncio.gather(self.receiving, return_exceptions=True)
        await self._wait_empty()

    async def confirm_cleanup(self):
        """Read-only confirmation for an already closed/fenced exact local worker."""
        if self.session_id is None:
            raise RuntimeError("Session cleanup identity is unavailable")
        await self._wait_empty()

    async def _wait_empty(self):
        # A plugin close ACK is not OS cleanup. Escaped child process groups
        # remain owned by the same systemd cgroup and must actually disappear.
        if (
            self.cgroup is None
            or not Path("/sys/fs/cgroup/cgroup.controllers").is_file()
        ):
            raise RuntimeError("Session cgroup cleanup is unconfirmed")
        events = Path("/sys/fs/cgroup") / self.cgroup.lstrip("/") / "cgroup.events"
        for _ in range(80):
            try:
                value = await asyncio.to_thread(events.read_text)
            except FileNotFoundError:
                if not Path("/sys/fs/cgroup/cgroup.controllers").is_file():
                    raise RuntimeError(
                        "Session cgroup cleanup is unconfirmed"
                    ) from None
                return
            if "populated 0" in value.splitlines():
                return
            await asyncio.sleep(0.05)
        raise RuntimeError("Session cgroup cleanup is unconfirmed")


class SandboxedSessionProvider(SessionChannelProvider):
    def __init__(self, *, wheel, factory, provider_id):
        super().__init__()
        self.wheel, self.factory, self.provider_id = wheel, factory, provider_id
        self.sha256 = hashlib.sha256(wheel).hexdigest()
        validate_wheel(wheel, self.sha256)
