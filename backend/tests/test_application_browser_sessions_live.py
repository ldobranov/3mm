"""Real bounded TCP WebSocket with deployed uvicorn driver, actual M20 fixtures.

Separate from OS sandbox acceptance. No installed Core/services or credentials.
"""

import json
import socket
import threading
import time

import pytest
import uvicorn
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from backend.tests.test_application_browser_sessions import (
    ORIGIN,
    browser_app,
    checkpoint_app,
    issue,
    managed_installed,
    session_app,
    source_installed,
    source_subject,
)
from three_mm_protocol.interactive_session import (
    decode_session_frame,
    encode_session_frame,
)


@pytest.mark.parametrize("oversized", [False, True])
def test_real_uvicorn_websocket_bounded_stream_and_owned_close(browser_app, oversized):
    s = browser_app
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            s.client.app,
            log_level="error",
            lifespan="off",
            ws="websockets-sansio",
            ws_max_size=65536,
            ws_max_queue=4,
            ws_per_message_deflate=False,
        )
    )
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [listener]}, daemon=True
    )
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        ticket = issue(s).json()
        with connect(
            f"ws://127.0.0.1:{port}" + s.base + "/ws",
            origin=ORIGIN,
            open_timeout=5,
            close_timeout=5,
            max_size=65536,
            compression=None,
        ) as ws:
            ws.send(json.dumps({"op": "authenticate", "ticket": ticket["ticket"]}))
            sid = json.loads(ws.recv(timeout=5))["acceptance"]["session_id"]
            assert decode_session_frame(ws.recv(timeout=5))[1] == b"ready\r\n"
            if oversized:
                ws.send(b"x" * 65537)
                with pytest.raises(ConnectionClosed) as closed:
                    ws.recv(timeout=5)
                assert closed.value.rcvd.code == 1009
                assert not s.provider.inputs
            else:
                ws.send(
                    encode_session_frame(
                        op="data",
                        seq=1,
                        session_id=sid,
                        payload=b"hello",
                        payload_kind="binary",
                    )
                )
                assert decode_session_frame(ws.recv(timeout=5))[1] == b"reply:hello"
                assert json.loads(ws.recv(timeout=5))["op"] == "input_ack"
                ws.send(json.dumps({"op": "close", "session_id": sid}))
                with pytest.raises(ConnectionClosed):
                    ws.recv(timeout=5)
        deadline = time.monotonic() + 3
        while s.browser.owned and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(s.provider.closed) == 1 and not s.browser.owned
    finally:
        server.should_exit = True
        thread.join(8)
        listener.close()
        assert not thread.is_alive()
