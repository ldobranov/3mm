"""Separate LOCAL host-account executor, never an isolated-profile fallback.

Only trusted Core connects. The reviewed provider and its descendants run as the
fixed non-login account with normal host-file DAC, no platform groups or sudo.
Root's policy and the exact account identity must stay current for its lifetime.
Systemd owns resource bounds and kills the entire connection cgroup on exit.
"""

from __future__ import annotations

import asyncio
import os
import re
import socket
import struct
import sys
from pathlib import Path

from components.system_runtime.host_session_policy import (
    HOST_SESSION_PROFILE, read_host_session_policy,
)
from components.system_runtime.session_worker import (
    read_packet, start_provider, startup_identity, validate_bootstrap,
    startup_step, SessionStartupError, report_startup_failure,
)


def verify_host_process():
    from packages.application_sdk.session import require_host_account_session_process

    require_host_account_session_process()


def _is_current(expected):
    try:
        return read_host_session_policy().sha256 == expected.sha256
    except (OSError, ValueError, KeyError):
        return False


def _context(value):
    if (type(value) is not dict or set(value) != {
            "session_id", "device_id", "capability_id", "access_mode", "options"}
            or type(value["session_id"]) is not str
            or re.fullmatch(r"ses_[0-9a-f]{32}", value["session_id"]) is None
            or type(value["device_id"]) is not str
            or re.fullmatch(r"dev_[0-9a-f]{32}", value["device_id"]) is None
            or type(value["capability_id"]) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", value["capability_id"]) is None
            or value["access_mode"] not in {"read", "write"}
            or type(value["options"]) is not dict
            or any(name in value["options"] for name in
                   ("account", "user", "username", "uid", "gid", "shell", "command", "executable", "cwd", "home", "env", "environment"))):
        raise ValueError("Invalid host-session context")
    from packages.protocol.node_security import validate_node_json
    validate_node_json(value["options"], max_bytes=8192)
    return value


async def _serve(reader, writer, *, cgroup, policy):
    session_id = None
    try:
        with startup_step('session.opening.bootstrap'):
            hello = await asyncio.wait_for(read_packet(reader), 5)
            if (set(hello) != {'version', 'size', 'sha256', 'factory', 'provider_id', 'context', 'profile', 'policy_sha256'}
                    or hello['profile'] != HOST_SESSION_PROFILE
                    or hello['policy_sha256'] != policy.sha256 or not _is_current(policy)):
                raise ValueError('Host-session policy changed')
            validate_bootstrap({key: value for key, value in hello.items()
                                if key not in {'profile', 'policy_sha256'}})
            context = _context(hello['context'])
        session_id = context['session_id']
        await start_provider(reader, writer, hello, context,
            identity=startup_identity(context, cgroup, profile=HOST_SESSION_PROFILE, policy_sha256=policy.sha256),
            idle_timeout=10, check_current=lambda: _is_current(policy))
    except SessionStartupError as error:
        if session_id is None:
            await report_startup_failure(writer, session_id, error)
        raise
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), 2)
        except (OSError, ConnectionError, TimeoutError):
            pass


async def serve(reader, writer, *, cgroup):
    """Run one exact stream; policy watchdog is independent of pending output."""
    try:
        with startup_step('session.opening.process_guard'):
            policy = read_host_session_policy()
    except SessionStartupError as error:
        await report_startup_failure(writer, None, error)
        writer.close()
        raise
    except BaseException:
        writer.close()
        raise
    serving = asyncio.create_task(_serve(reader, writer, cgroup=cgroup, policy=policy))

    async def policy_watch():
        while True:
            await asyncio.sleep(3)
            if not _is_current(policy):
                raise ValueError("Host-session policy changed")

    watching = asyncio.create_task(policy_watch())
    try:
        done, _ = await asyncio.wait((serving, watching), return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
    finally:
        serving.cancel()
        watching.cancel()
        await asyncio.gather(serving, watching, return_exceptions=True)
        writer.close()


async def main():
    import pwd

    connection = socket.socket(fileno=os.dup(0))
    connection.set_inheritable(False)
    _pid, uid, _gid = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if uid != pwd.getpwnam("3mm").pw_uid:
        raise RuntimeError("Host-session caller is unavailable")
    reader, writer = await asyncio.open_connection(sock=connection)
    try:
        with startup_step('session.opening.process_guard'):
            verify_host_process()
            read_host_session_policy()
            cgroup = next(line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines()
                          if line.startswith('0::'))
    except SessionStartupError as error:
        await report_startup_failure(writer, None, error)
        writer.close()
        raise
    await asyncio.wait_for(serve(reader, writer, cgroup=cgroup), 900)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except BaseException:
        # No terminal bytes, commands or provider exceptions are logged.
        sys.exit(1)
