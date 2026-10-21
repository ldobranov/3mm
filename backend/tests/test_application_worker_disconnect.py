"""M20 -> real ASGI/IPC with a failing fixture, never an installed OS worker.

The cgroup observer is an explicit test seam, NOT an OS-isolation proof. No
service, owner key, owner database, shell or hardware is used by this test.
"""

import asyncio
import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from backend.db.audit_log import AuditLog
from backend.services.application_browser_sessions import ReviewedSessionRuntime
from backend.tests.test_application_browser_sessions import (
    browser_app,
    checkpoint_app,
    connect,
    issue,
    managed_installed,
    session_app,
    source_installed,
    source_subject,
)
from backend.tests.test_application_session_authority import CAPABILITY, PROVIDER
from three_mm_protocol.interactive_session import (
    decode_session_frame,
    encode_session_frame,
)
from three_mm_runtime.session_worker import serve
from three_mm_runtime.session_worker_client import SandboxedSessionProvider
from three_mm_runtime.tests.test_session_worker import wheel


@pytest.mark.parametrize(
    "empty_cgroup,crash,audit_failure",
    [
        (True, True, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
def test_worker_stream_and_disconnect_require_confirmed_cleanup(
    browser_app, monkeypatch, empty_cgroup, crash, audit_failure, caplog
):
    s = browser_app
    audit = s.browser._audit
    if not crash:
        # Force the real browser pump to request more output while the prior
        # worker reply is visible to Core but its send task has not returned.
        import three_mm_runtime.session_worker as worker

        original_write, original_read = worker.write_packet, worker.read_packet
        release_reply = None
        reads = 0
        delayed = False

        async def delayed_reply(writer, value):
            nonlocal delayed
            await original_write(writer, value)
            if "data" in value and value["data"] and not delayed:
                delayed = True
                await asyncio.wait_for(release_reply.wait(), 5)

        async def observe_request(reader):
            nonlocal reads
            value = await original_read(reader)
            if value.get("op") == "read":
                reads += 1
                if reads == 2:
                    release_reply.set()
            return value

        monkeypatch.setattr(worker, "write_packet", delayed_reply)
        monkeypatch.setattr(worker, "read_packet", observe_request)

    def record_audit(admitted, module_id, outcome):
        if audit_failure and outcome != "start_requested":
            raise RuntimeError("private audit error must never be logged")
        return audit(admitted, module_id, outcome)

    monkeypatch.setattr(s.browser, "_audit", record_audit)
    source = f"""
import asyncio
class Provider:
    provider_id = {PROVIDER!r}
    contract_version = "1.0"
    capability_ids = ({CAPABILITY!r},)
    control_actions = ("resize",)
    async def open(self, context):
        self.output = asyncio.Queue()
        self.output.put_nowait(b"fixture ready")
    async def read_output(self, sid): return await self.output.get()
    async def receive(self, sid, data):
        if {crash!r}:
            raise RuntimeError("fixture exception must never reach browser/audit")
        self.output.put_nowait(data)
        return b""  # Terminal-style streaming: output is not an input response.
    async def control(self, sid, message): pass
    async def close(self, sid, reason): pass
def create_provider(): return Provider()
"""
    workers = []
    finished = None

    async def start():
        nonlocal finished, release_reply
        finished = asyncio.Event()
        if not crash:
            release_reply = asyncio.Event()

        async def connected(reader, writer):
            workers.append(asyncio.current_task())
            try:
                await serve(
                    reader,
                    writer,
                    cgroup="/system.slice/system-test.slice/3mm-session-worker@fixture.service",
                )
            except (RuntimeError, ConnectionError, asyncio.IncompleteReadError):
                pass
            finally:
                finished.set()

        server = await asyncio.start_server(connected, "127.0.0.1", 0)
        return server, server.sockets[0].getsockname()[1]

    server, port = s.client.portal.call(start)
    provider = SandboxedSessionProvider(
        wheel=wheel(source),
        factory="worker_fixture:create_provider",
        provider_id=PROVIDER,
    )
    monkeypatch.setattr(
        provider, "_connect", lambda: asyncio.open_connection("127.0.0.1", port)
    )
    confirmations = []

    async def confirm_fixture_cleanup():
        await asyncio.wait_for(finished.wait(), 1)
        confirmations.append(provider.cgroup)
        if not empty_cgroup:
            raise RuntimeError("Session cgroup cleanup is unconfirmed")

    monkeypatch.setattr(provider, "_wait_empty", confirm_fixture_cleanup)
    s.browser.runtimes = (
        ReviewedSessionRuntime(
            s.runtime.device_id,
            s.runtime.provider_id,
            s.runtime.provider_version,
            s.runtime.control_revision,
            provider,
        ),
    )

    async def stop():
        server.close()
        await server.wait_closed()
        await asyncio.gather(*workers, return_exceptions=True)

    try:
        ticket = issue(s).json()
        with connect(s, ticket) as ws:
            ws.send_json({"op": "authenticate", "ticket": ticket["ticket"]})
            sid = ws.receive_json()["acceptance"]["session_id"]
            assert decode_session_frame(ws.receive_bytes())[1] == b"fixture ready"
            ws.send_json(
                {
                    "op": "control",
                    "control": {
                        "session_id": sid,
                        "control_id": "initial_fit",
                        "action": "resize",
                        "arguments": {"cols": 101, "rows": 37},
                    },
                }
            )
            assert ws.receive_json()["op"] == "control_ack"
            ws.send_bytes(
                encode_session_frame(
                    op="data",
                    seq=1,
                    session_id=sid,
                    payload=b"fixture_only_sensitive_input",
                    payload_kind="binary",
                )
            )
            if not crash:
                # Streaming output and the input ACK may arrive in either order.
                responses = [ws.receive(), ws.receive()]
                frames = [
                    decode_session_frame(value["bytes"])[1]
                    for value in responses
                    if value.get("bytes") is not None
                ]
                acks = [
                    json.loads(value["text"])["op"]
                    for value in responses
                    if value.get("text") is not None
                ]
                assert frames == [b"fixture_only_sensitive_input"]
                assert acks == ["input_ack"]
                ws.send_json({"op": "close", "session_id": sid})
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()  # A crash must not return an input ACK.
        assert confirmations == [provider.cgroup]
        released = empty_cgroup and not audit_failure
        assert bool(s.browser.owned) is not released
        assert bool(s.browser.leases) is not released
        assert bool(s.browser.reservations) is not released
        # The old request stays spent even when OS cleanup is confirmed.
        assert issue(s).status_code == 403
        replacement = {
            **s.request.model_dump(mode="json"),
            "request_id": "fresh_after_cleanup",
        }
        assert issue(s, request=replacement).status_code == (200 if released else 403)
        with Session(s.engine) as db:
            audits = db.scalars(
                select(AuditLog)
                .where(AuditLog.action == "APPLICATION_SESSION_LIFECYCLE")
                .order_by(AuditLog.id)
            ).all()
            changes = [row.changes for row in audits]
        expected = ["start_requested"]
        if not audit_failure:
            expected.append("closed" if empty_cgroup else "cleanup_unconfirmed")
        assert [value["outcome"] for value in changes] == expected
        assert "fixture_only_sensitive_input" not in json.dumps(changes)
        assert "fixture exception" not in json.dumps(changes)
        assert ("Application session stopped:" in caplog.text) is crash
        assert "fixture_only_sensitive_input" not in caplog.text
        assert "fixture exception" not in caplog.text
        assert "private audit error" not in caplog.text
        assert ("cleanup audit unavailable" in caplog.text) is audit_failure
    finally:
        s.client.portal.call(stop)
        # The worker imports from a wheel only in this fixture interpreter.
        import sys

        sys.modules.pop("worker_fixture", None)
