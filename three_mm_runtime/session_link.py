"""Optional TLS session executor link using the same bounded SDK/IPC channel.

Only platform composition constructs the client. The Node endpoint requires the
pinned existing Hub's TLS certificate and a fixed reviewed provider; no browser
can send a wheel/factory/path or choose an OS user. Cleanup acknowledgement is
sent only after the Node's platform provider confirms OS cleanup.
"""
from __future__ import annotations
import asyncio
import hashlib
import re
import secrets
import ssl

from three_mm_runtime.session_worker import read_packet, write_packet, serve_provider_calls
from three_mm_runtime.session_worker_client import SessionChannelProvider


class RemoteSessionProvider(SessionChannelProvider):
    def __init__(self, *, host, port, device_id, provider_id, provider_version,
                 capability_id, artifact_sha256, peer_sha256, tls, current):
        super().__init__()
        self.host, self.port, self.tls = host, port, tls
        self.device_id, self.provider_id = device_id, provider_id
        self.provider_version, self.capability_id = provider_version, capability_id
        self.artifact_sha256, self.peer_sha256 = artifact_sha256, peer_sha256
        self.current = current
        self.lease = None
        self.confirmed_empty = False
        self.peer_generation = None
        self.execution_id = None
        self.bootstrap_sent = False
        self.opening = False

    def is_current(self):
        return self.current() is True and (self.session_id is None or self.opening or (
            self.receiving is not None and not self.receiving.done()
            and self.writer is not None and not self.writer.is_closing()))

    async def open(self, context):
        if self.session_id is not None or not self.current():
            raise RuntimeError("Session link open unavailable")
        self.session_id = context["session_id"]  # Never retried on an uncertain handshake.
        self.opening = True
        try:
            self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(
                self.host, self.port, ssl=self.tls, server_hostname=self.device_id,
                ssl_handshake_timeout=5, limit=65536), 6)
            certificate = self.writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
            if hashlib.sha256(certificate).hexdigest() != self.peer_sha256:
                raise RuntimeError("Session link peer changed")
            self.bootstrap_sent = True  # Any partial hello is an uncertain open.
            await write_packet(self.writer, {
                "session_link_version": 1, "provider_id": self.provider_id,
                "provider_version": self.provider_version,
                "artifact_sha256": self.artifact_sha256, "context": context,
            })
            ready = await asyncio.wait_for(read_packet(self.reader), 100)
            if (set(ready) != {"ready", "generation", "execution_id"} or ready["ready"] is not True
                    or type(ready["generation"]) is not str
                    or re.fullmatch(r"[0-9a-f]{32}", ready["generation"]) is None
                    or not valid_execution_id(ready["execution_id"])):
                raise RuntimeError("Session link startup unconfirmed")
            self.peer_generation = ready["generation"]
            self.execution_id = ready["execution_id"]
            self.receiving = asyncio.create_task(self._receive())
            self.lease = asyncio.create_task(self._keepalive())
        except BaseException:
            if self.writer is not None:
                self.writer.close()
            raise
        finally:
            self.opening = False

    async def _keepalive(self):
        try:
            while True:
                await asyncio.sleep(2)
                if not self.current():
                    raise RuntimeError("Session link authority changed")
                if (await self._call(self.session_id, "lease"))["ok"] is not True:
                    raise RuntimeError("Session link lease unavailable")
        except asyncio.CancelledError:
            raise  # Planned close stops lease renewal before its cleanup RPC.
        except Exception:
            if self.writer is not None:
                self.writer.close()

    async def _close(self, session_id):
        if self.lease is not None:
            self.lease.cancel()
            await asyncio.gather(self.lease, return_exceptions=True)
        try:
            if not self.bootstrap_sent:
                self.confirmed_empty = True  # No execution request crossed the authenticated channel.
            elif self.receiving is not None and not self.receiving.done():
                result = await self._call(session_id, "close")
                self.confirmed_empty = result.get("closed") is True
        finally:
            if self.writer is not None:
                self.writer.close()
                try:
                    await asyncio.wait_for(self.writer.wait_closed(), 2)
                except (OSError, ConnectionError, TimeoutError):
                    pass
            if self.receiving is not None:
                self.receiving.cancel()
                await asyncio.gather(self.receiving, return_exceptions=True)
        if not self.confirmed_empty:
            raise RuntimeError("Remote session OS cleanup is unconfirmed")


    async def confirm_cleanup(self):
        """Explicit read-only OS-status reconciliation; never repeat open/input/close."""
        if self.session_id is None:
            raise RuntimeError("Remote cleanup identity is unavailable")
        if not self.bootstrap_sent:
            self.confirmed_empty = True
            return
        if self.execution_id is not None and not valid_execution_id(self.execution_id):
            raise RuntimeError("Remote cleanup identity is unavailable")
        writer = None
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(
                self.host, self.port, ssl=self.tls, server_hostname=self.device_id,
                ssl_handshake_timeout=3, limit=65536), 4)
            certificate = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
            if hashlib.sha256(certificate).hexdigest() != self.peer_sha256:
                raise RuntimeError("Remote cleanup peer changed")
            request = {"session_cleanup_version": 1, "session_id": self.session_id,
                       "execution_id": self.execution_id}
            await write_packet(writer, request)
            result = await asyncio.wait_for(read_packet(reader), 2)
            if result != {**request, "empty": True}:
                raise RuntimeError("Remote OS cleanup is unconfirmed")
            self.confirmed_empty = True
        finally:
            if writer is not None:
                writer.close()
                try:
                    await asyncio.wait_for(writer.wait_closed(), 1)
                except (ConnectionError, OSError, TimeoutError):
                    pass


def valid_execution_id(value):
    return (type(value) is str and len(value) <= 512 and '..' not in value.split('/')
            and re.fullmatch(r'/system.slice/[A-Za-z0-9_@.\\:/-]+/3mm-session-worker-node@[^/]+\.service', value) is not None)


def node_execution_empty(execution_id):
    """OS evidence only, scoped to this optional Node worker profile."""
    from pathlib import Path
    root = Path('/sys/fs/cgroup/system.slice')
    if not Path('/sys/fs/cgroup/cgroup.controllers').is_file() or not root.is_dir():
        return False
    if execution_id is None:
        import os
        def fail(error):
            raise error
        try:
            count = 0
            for directory, _children, _files in os.walk(root, onerror=fail):
                count += 1
                if count > 4096:
                    return False
                group = Path(directory)
                if (group.name.startswith('3mm-session-worker-node@') and group.name.endswith('.service')
                        and 'populated 0' not in (group/'cgroup.events').read_text().splitlines()):
                    return False
            return True
        except OSError:
            return False
    if not valid_execution_id(execution_id):
        return False
    events = Path('/sys/fs/cgroup') / execution_id.lstrip('/') / 'cgroup.events'
    try:
        return 'populated 0' in events.read_text().splitlines()
    except FileNotFoundError:
        return Path('/sys/fs/cgroup/cgroup.controllers').is_file()
    except OSError:
        return False


class _CleanupWitness:
    def __init__(self, provider, confirmed):
        self.provider, self.confirmed = provider, False
        self.on_confirmed = confirmed

    def __getattr__(self, name):
        return getattr(self.provider, name)

    async def close(self, session_id, reason):
        await self.provider.close(session_id, reason)
        self.confirmed = True
        self.on_confirmed()


class SessionLinkServer:
    """One Node/low-memory slot, authenticated before this handler runs.

    ``provider_factory`` is platform-owned and must return an isolated provider
    whose close waits for actual cgroup emptiness. TLS is mandatory here; a relay
    is only a byte pipe and holds neither the Hub key nor Node execution rights.
    """
    def __init__(self, *, device_id, provider_id, provider_version, capability_id,
                 artifact_sha256, access_modes, control_actions,
                 provider_factory, check_current, cleanup_status, generation=None):
        self.device_id, self.provider_id = device_id, provider_id
        self.provider_version, self.capability_id = provider_version, capability_id
        self.artifact_sha256, self.access_modes = artifact_sha256, tuple(access_modes)
        self.control_actions = tuple(control_actions)
        self.provider_factory, self.check_current = provider_factory, check_current
        self.cleanup_status = cleanup_status
        self.generation = generation or secrets.token_hex(16)
        self._owner = None
        self._owner_session = self._owner_execution = None
        self._fenced = False
        self.tasks = set()
        self.spent = set()
        self.closed = []  # Bounded metadata only; never terminal data or tokens.

    @property
    def active(self):
        return self._owner is not None

    async def _open_current(self, provider, context, reader):
        """Stop cold startup on pre-ready EOF, premature input or Node drift."""
        async def watch():
            # No legitimate Hub packet precedes our ready reply. Cancel this
            # reader completely before handing the channel to the call loop.
            incoming = asyncio.create_task(reader.read(1))
            try:
                while True:
                    if self.check_current() is not True:
                        raise ValueError("Node session identity changed during startup")
                    done, _ = await asyncio.wait((incoming,), timeout=1)
                    if incoming in done:
                        await incoming
                        raise ValueError("Session link ended or sent input before ready")
            finally:
                if not incoming.done():
                    incoming.cancel()
                await asyncio.gather(incoming, return_exceptions=True)

        opening = asyncio.create_task(provider.open(context))
        watcher = asyncio.create_task(watch())
        async def guarded():
            done, _ = await asyncio.wait((opening, watcher), return_when=asyncio.FIRST_COMPLETED)
            if watcher in done:
                await watcher  # EOF/currentness failure wins simultaneous completion.
            await opening
            if self.check_current() is not True:
                raise ValueError("Node session identity changed during startup")
        try:
            await asyncio.wait_for(guarded(), 95)
        finally:
            for task in (watcher, opening):
                if not task.done():
                    task.cancel()
            # Neither startup nor its pre-ready reader may outlive cleanup.
            await asyncio.gather(watcher, opening, return_exceptions=True)

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        provider = None
        context = None
        owns_slot = False
        owner = object()
        def release():
            if self._owner is owner:
                self._owner = None
                self._owner_session = self._owner_execution = None
                self._fenced = False
        try:
            if writer.get_extra_info("ssl_object") is None or self.check_current() is not True:
                raise ValueError("An authenticated current session link is required")
            if len(self.tasks) > 4:
                raise ValueError("Session link capacity unavailable")
            hello = await asyncio.wait_for(read_packet(reader), 5)
            if set(hello) == {"session_cleanup_version", "session_id", "execution_id"}:
                if (type(hello["session_cleanup_version"]) is not int or hello["session_cleanup_version"] != 1
                    or type(hello["session_id"]) is not str or re.fullmatch(r"ses_[0-9a-f]{32}", hello["session_id"]) is None
                    or hello["execution_id"] is not None and not valid_execution_id(hello["execution_id"])):
                    raise ValueError("Invalid cleanup identity")
                sid, execution = hello["session_id"], hello["execution_id"]
                # A cleanup proof is also a terminal barrier for this exact SID.
                # Install it BEFORE I/O: a hello buffered on another connection
                # must never start a worker after an empty observation succeeds.
                if sid not in self.spent and len(self.spent) >= 1024:
                    await write_packet(writer, {**hello, "empty": False})
                    return
                self.spent.add(sid)
                cleanup_owner = self._owner
                same_owner = self._owner_session == sid
                if (same_owner and not self._fenced
                        or execution is None and self.active and not same_owner):
                    # The original handler can still create/use its worker.
                    await write_packet(writer, {**hello, "empty": False})
                    return
                if same_owner and self._fenced:
                    if self._owner_execution is None:
                        # An uncertain local socket startup can still have a
                        # queued systemd job, before any cgroup exists. Restart
                        # this optional Node component to end that generation;
                        # instantaneous cgroup absence cannot clear its fence.
                        await write_packet(writer, {**hello, "empty": False})
                        return
                    if execution not in (None, self._owner_execution):
                        await write_packet(writer, {**hello, "empty": False})
                        return
                    execution = self._owner_execution
                empty = await asyncio.wait_for(asyncio.to_thread(self.cleanup_status, execution), 1)
                if type(empty) is not bool:
                    raise ValueError("Cleanup observation unavailable")
                if (empty and same_owner and self._fenced and self._owner is cleanup_owner
                        and self._owner_session == sid and self._owner_execution == execution):
                    self._owner = None
                    self._owner_session = self._owner_execution = None
                    self._fenced = False
                await write_packet(writer, {**hello, "empty": empty})
                return
            if self.active:
                raise ValueError("Session execution capacity unavailable")
            self._owner = owner
            owns_slot = True
            if (set(hello) != {"session_link_version", "provider_id", "provider_version", "artifact_sha256", "context"}
                or type(hello["session_link_version"]) is not int or hello["session_link_version"] != 1
                or (hello["provider_id"], hello["provider_version"], hello["artifact_sha256"])
                   != (self.provider_id, self.provider_version, self.artifact_sha256)):
                raise ValueError("Session link provider differs from reviewed configuration")
            context = hello["context"]
            if (type(context) is not dict or set(context) != {"session_id", "device_id", "capability_id", "access_mode", "options"}
                or type(context["session_id"]) is not str or re.fullmatch(r"ses_[0-9a-f]{32}", context["session_id"]) is None
                or context["device_id"] != self.device_id or context["capability_id"] != self.capability_id
                or context["access_mode"] not in self.access_modes or type(context["options"]) is not dict):
                raise ValueError("Session link target differs from reviewed configuration")
            if context["session_id"] in self.spent or len(self.spent) >= 1024:
                raise ValueError("Session identity is already spent or ledger is full")
            self.spent.add(context["session_id"])
            self._owner_session = context["session_id"]
            provider = self.provider_factory()
            provider.control_actions = self.control_actions
            await self._open_current(provider, context, reader)
            self._owner_execution = provider.cgroup
            owned, provider = _CleanupWitness(provider, release), None
            try:
                await asyncio.wait_for(serve_provider_calls(
                    reader, writer, owned, context,
                    ready={"ready": True, "generation": self.generation, "execution_id": owned.cgroup},
                    idle_timeout=10, check_current=self.check_current), 900)
            finally:
                # A provider-close failure keeps this process's capacity fenced.
                if not owned.confirmed:
                    owns_slot = False
                    if self._owner is owner:
                        self._fenced = True
                self.closed.append({"session_id": context["session_id"], "cleanup_confirmed": owned.confirmed})
                self.closed[:] = self.closed[-64:]
        except BaseException:
            if provider is not None and context is not None:
                try:
                    await asyncio.wait_for(provider.close(context["session_id"], "link_failed"), 5)
                except BaseException:
                    owns_slot = False  # Preserve the occupied/fenced slot.
                    if self._owner is owner:
                        self._owner_execution = getattr(provider, "cgroup", None)
                        self._fenced = True
        finally:
            self.tasks.discard(task)
            if owns_slot:
                release()
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 2)
            except (ConnectionError, OSError, TimeoutError):
                pass

    async def close(self):
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
