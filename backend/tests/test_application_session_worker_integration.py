"""Explicit disposable systemd integration: REAL M20 -> UI WS -> sandbox SDK.

The independent counter wheel proves Core is not coupled to a concrete terminal.
The Terminal shell is exercised separately by the same root acceptance harness.
"""

import io
import os
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import delete
from starlette.websockets import WebSocketDisconnect

from backend.db.module import ApplicationPermissionGrant
from backend.services.application_session_runtimes import ReviewedSessionRuntime
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
from three_mm_runtime import session_worker_client as ipc

pytestmark = pytest.mark.skipif(
    os.getenv("THREE_MM_TEST_SESSION_SOCKET") is None,
    reason="Run only through disposable root systemd acceptance harness",
)


@pytest.mark.parametrize("revoked", ["human", "service"])
def test_real_m20_browser_to_independent_sandbox_provider_and_idle_revoke(
    browser_app, monkeypatch, revoked
):
    s = browser_app
    # Same bounded pre-admission wait as the configured production coordinator;
    # the admin write is NOT artificially serialized against the idle reader.
    s.manager.keys._lock_wait_seconds = 0.25
    endpoint = Path(os.environ["THREE_MM_TEST_SESSION_SOCKET"])
    assert endpoint.parent.parent == Path("/opt") and endpoint.parent.name.startswith(
        "3mm-m21-session-"
    )
    monkeypatch.setattr(ipc, "SOCKET_PATH", endpoint)
    source = f"""
import asyncio
class Provider:
    provider_id = {PROVIDER!r}
    contract_version = "1.0"
    capability_ids = ({CAPABILITY!r},)
    control_actions = ("resize",)
    async def open(self, context):
        self.output = asyncio.Queue(maxsize=1)
        self.output.put_nowait(b"independent sandbox ready")
    async def receive(self, sid, data): return b"counter:" + data
    async def read_output(self, sid): return await self.output.get()
    async def control(self, sid, message):
        assert set(message) == {{"action", "arguments"}}
    async def close(self, sid, reason): pass
def create_provider(): return Provider()
"""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("independent_provider.py", source)
        archive.writestr(
            "independent-0.dist-info/WHEEL",
            "Root-Is-Purelib: true\nTag: py3-none-any\n",
        )
    provider = ipc.SandboxedSessionProvider(
        wheel=stream.getvalue(),
        factory="independent_provider:create_provider",
        provider_id=PROVIDER,
    )
    s.browser.runtimes = (
        ReviewedSessionRuntime(
            s.runtime.device_id,
            s.runtime.provider_id,
            s.runtime.provider_version,
            s.runtime.control_revision,
            provider,
            lambda: True,  # Explicit fixture generation.
        ),
    )
    ticket = issue(s).json()
    with connect(s, ticket) as ws:
        ws.send_json({"op": "authenticate", "ticket": ticket["ticket"]})
        sid = ws.receive_json()["acceptance"]["session_id"]
        assert (
            decode_session_frame(ws.receive_bytes())[1] == b"independent sandbox ready"
        )
        ws.send_bytes(
            encode_session_frame(
                op="data", seq=1, session_id=sid, payload=b"one", payload_kind="binary"
            )
        )
        assert decode_session_frame(ws.receive_bytes())[1] == b"counter:one"
        assert ws.receive_json()["op"] == "input_ack"
        ws.send_json(
            {
                "op": "control",
                "control": {
                    "session_id": sid,
                    "control_id": "resize_1",
                    "action": "resize",
                    "arguments": {"cols": 90, "rows": 30},
                },
            }
        )
        assert ws.receive_json()["op"] == "control_ack"
        # No further input: current human revocation must stop the OS worker.
        if revoked == "human":
            with s.engine.begin() as db:
                db.execute(delete(ApplicationPermissionGrant))
        else:
            from backend.tests.test_application_authority_management import identity

            s.manager.revoke(
                1,
                actor_token=s.token,
                request_id=identity(),
                expected_revision=s.grant_record_revision,
            )
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert provider.closing is not None and provider.closing.done()
    assert provider.closing.exception() is None
    assert not s.browser.owned and not s.browser.leases
