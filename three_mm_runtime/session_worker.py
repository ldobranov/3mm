"""One socket-activated, sandboxed SDK provider; never an authority issuer.

Only the trusted Core UID can connect. It supplies the exact reviewed pure-Python
wheel, factory and context AFTER M20 admission. No path, shell, UID or environment
can be selected over IPC. Each connection has its own systemd cgroup and ephemeral
identity. This executable refuses to run outside the installed sandbox profile.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib
import io
import json
import os
import re
import socket
import stat
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

MAX_PACKET = 65536
MAX_DATA = 16384
MAX_WHEEL = 10 * 1024 * 1024
PROFILE = "isolated_session_v1"


async def read_packet(reader):
    size = struct.unpack("!I", await reader.readexactly(4))[0]
    if not 1 <= size <= MAX_PACKET:
        raise ValueError("Invalid session IPC size")
    raw = await reader.readexactly(size)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate session IPC field")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=unique)
    if type(value) is not dict:
        raise ValueError("Invalid session IPC object")
    return value


async def write_packet(writer, value):
    raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    if not 1 <= len(raw) <= MAX_PACKET:
        raise ValueError("Invalid session IPC size")
    writer.write(struct.pack("!I", len(raw)) + raw)
    await asyncio.wait_for(writer.drain(), 5)


def validate_wheel(data, expected_sha256):
    if (
        not 1 <= len(data) <= MAX_WHEEL
        or hashlib.sha256(data).hexdigest() != expected_sha256
    ):
        raise ValueError("Session artifact mismatch")
    with zipfile.ZipFile(io.BytesIO(data)) as wheel:
        entries = wheel.infolist()
        if (
            not entries
            or len(entries) > 2048
            or sum(i.file_size for i in entries) > 40 * 1024 * 1024
        ):
            raise ValueError("Session wheel exceeds bounds")
        names = set()
        for item in entries:
            name = item.filename
            if (
                name in names
                or name.startswith("/")
                or "\\" in name
                or any(part in ("", ".", "..") for part in name.rstrip("/").split("/"))
                or stat.S_ISLNK(item.external_attr >> 16)
                or name.endswith((".so", ".pyd", ".pth"))
            ):
                raise ValueError("Session wheel is not a safe pure-Python artifact")
            names.add(name)
        metadata = [i for i in entries if i.filename.endswith(".dist-info/WHEEL")]
        if len(metadata) != 1 or b"Root-Is-Purelib: true" not in wheel.read(
            metadata[0]
        ):
            raise ValueError("A pure-Python session wheel is required")


def verify_sandbox():
    """Fail closed without the per-connection OS boundary; env alone is no proof."""
    from three_mm_application_sdk.session import require_isolated_session_process

    require_isolated_session_process()


async def serve(reader, writer, *, cgroup=None):
    """Internal bounded IPC. No retries, queues of input, or reconnect semantics."""
    provider = None
    reading = None
    session_id = None
    send_lock = asyncio.Lock()
    remainder = b""

    async def send(value):
        async with send_lock:
            await write_packet(writer, value)

    async def reply_read(call_id):
        nonlocal remainder
        data = remainder or await provider.read_output(session_id)
        if data is not None and (
            type(data) is not bytes or not 1 <= len(data) <= 65278
        ):
            raise ValueError("Provider output exceeds bounds")
        if data is not None:
            data, remainder = data[:MAX_DATA], data[MAX_DATA:]
        await send(
            {
                "id": call_id,
                "data": None if data is None else base64.b64encode(data).decode(),
            }
        )

    try:
        hello = await asyncio.wait_for(read_packet(reader), 5)
        if (
            set(hello)
            != {"version", "size", "sha256", "factory", "provider_id", "context"}
            or type(hello["version"]) is not int
            or hello["version"] != 1
        ):
            raise ValueError("Invalid session bootstrap")
        if type(hello["size"]) is not int or not 1 <= hello["size"] <= MAX_WHEEL:
            raise ValueError("Invalid session artifact size")
        if (
            type(hello["factory"]) is not str
            or re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*", hello["factory"]
            )
            is None
        ):
            raise ValueError("Invalid session factory")
        context = hello["context"]
        if type(context) is not dict or set(context) != {
            "session_id",
            "device_id",
            "capability_id",
            "access_mode",
            "options",
        }:
            raise ValueError("Invalid session context")
        session_id = context["session_id"]
        if (
            type(session_id) is not str
            or re.fullmatch(r"ses_[0-9a-f]{32}", session_id) is None
        ):
            raise ValueError("Invalid session identity")
        data = await asyncio.wait_for(reader.readexactly(hello["size"]), 10)
        validate_wheel(data, hello["sha256"])
        with tempfile.TemporaryDirectory(prefix="3mm-session-") as directory:
            wheel = Path(directory) / "provider.whl"
            wheel.write_bytes(data)
            del data
            sys.path.insert(0, str(wheel))
            try:
                module, factory = hello["factory"].split(":")
                provider = getattr(importlib.import_module(module), factory)()
                if (
                    getattr(provider, "provider_id", None) != hello["provider_id"]
                    or getattr(provider, "contract_version", None) != "1.0"
                    or context["capability_id"]
                    not in getattr(provider, "capability_ids", ())
                    or not all(
                        callable(getattr(provider, name, None))
                        for name in (
                            "open",
                            "receive",
                            "read_output",
                            "control",
                            "close",
                        )
                    )
                ):
                    raise ValueError("Session provider differs from declaration")
                await asyncio.wait_for(provider.open(context), 5)
                await send({"ready": True, "cgroup": cgroup})
                last_id = 0
                while True:
                    call = await read_packet(reader)
                    call_id, op = call.get("id"), call.get("op")
                    if (
                        type(call_id) is not int
                        or call_id != last_id + 1
                        or call_id > 65536
                    ):
                        raise ValueError("Invalid session IPC sequence")
                    last_id = call_id
                    if reading is not None and reading.done():
                        await reading
                        reading = None
                    if op == "read" and set(call) == {"id", "op"} and reading is None:
                        reading = asyncio.create_task(reply_read(call_id))
                        # Consume failures even while awaiting the next request.
                        reading.add_done_callback(
                            lambda task: (
                                writer.close()
                                if not task.cancelled() and task.exception()
                                else None
                            )
                        )
                        continue
                    if op == "input" and set(call) == {"id", "op", "data"}:
                        data = base64.b64decode(call["data"], validate=True)
                        if (
                            not 1 <= len(data) <= MAX_DATA
                            or context["access_mode"] != "write"
                        ):
                            raise ValueError("Invalid session input")
                        result = await asyncio.wait_for(
                            provider.receive(session_id, data), 5
                        )
                        if type(result) is not bytes or len(result) > MAX_DATA:
                            raise ValueError("Invalid session response")
                        await send(
                            {"id": call_id, "data": base64.b64encode(result).decode()}
                        )
                    elif op == "control" and set(call) == {"id", "op", "message"}:
                        message = call["message"]
                        if (
                            type(message) is not dict
                            or set(message) != {"action", "arguments"}
                            or message["action"] not in provider.control_actions
                        ):
                            raise ValueError("Invalid session control")
                        await asyncio.wait_for(provider.control(session_id, message), 5)
                        await send({"id": call_id, "ok": True})
                    elif op == "close" and set(call) == {"id", "op"}:
                        if reading is not None:
                            reading.cancel()
                            await asyncio.gather(reading, return_exceptions=True)
                        await asyncio.wait_for(
                            provider.close(session_id, "core_closed"), 4
                        )
                        provider = None
                        await send({"id": call_id, "closed": True})
                        return
                    else:
                        raise ValueError("Unsupported session IPC operation")
            finally:
                sys.path.remove(str(wheel))
    finally:
        if reading is not None:
            reading.cancel()
            await asyncio.gather(reading, return_exceptions=True)
        if provider is not None:
            await asyncio.wait_for(provider.close(session_id, "link_closed"), 4)
        writer.close()
        await writer.wait_closed()


async def main():
    verify_sandbox()
    import pwd

    connection = socket.socket(fileno=os.dup(0))
    connection.set_inheritable(False)
    _pid, uid, _gid = struct.unpack(
        "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    )
    if uid != pwd.getpwnam("3mm").pw_uid:
        raise RuntimeError("Session caller is unavailable")
    reader, writer = await asyncio.open_connection(sock=connection)
    cgroup = next(
        line[3:]
        for line in Path("/proc/self/cgroup").read_text().splitlines()
        if line.startswith("0::")
    )
    await asyncio.wait_for(serve(reader, writer, cgroup=cgroup), 900)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except BaseException:
        # No provider error/terminal data in logs. systemd tears down the cgroup.
        sys.exit(1)
