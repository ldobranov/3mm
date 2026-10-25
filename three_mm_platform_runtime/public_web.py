"""Bounded public response relay. No database, application keys or authority cache."""
import threading
import time

from three_mm_platform_wire import (
    AUTHORITY_CALL_SECONDS, read_frame, receive_authority_frame, remaining, send_authority_frame,
)
from three_mm_platform_runtime.server import PlatformRuntime, _core_connection, _frame

PUBLIC_WEB_MESSAGE_BYTES = 1024 * 1024
PUBLIC_WEB_CONNECTIONS = 8


class PublicWebRuntime(PlatformRuntime):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.slots = threading.BoundedSemaphore(PUBLIC_WEB_CONNECTIONS)

    def _authority(self, request, deadline):
        upstream, _, _ = _core_connection(self.authority_path, self.core_uid, deadline)
        with upstream:
            upstream.settimeout(remaining(deadline))
            send_authority_frame(upstream, request)
            return receive_authority_frame(upstream, deadline)

    def _serve(self, connection):
        origin = None
        request_id = "invalid"
        try:
            with connection:
                deadline = time.monotonic() + 35
                request = read_frame(connection, min(deadline, time.monotonic()+5),
                                     max_bytes=PUBLIC_WEB_MESSAGE_BYTES)
                request_id = request.get("request_id", "invalid")
                begin, origin = self._authority({"public_web_contract": 1, "begin": request},
                    min(deadline, time.monotonic()+AUTHORITY_CALL_SECONDS+1))
                if begin.get("public_web_contract") != 1: raise ValueError("Unsupported public authority")
                if begin.get("ok") is not True:
                    if origin is not None: raise ValueError("Unexpected dispatch socket")
                    result = begin
                else:
                    timeout = begin.get("timeout_seconds")
                    if origin is None or type(timeout) not in {int,float} or not 0 < timeout <= 30:
                        raise ValueError("Invalid public dispatch")
                    # Own this one-shot connected socket, not a transport key.
                    # Closing/killing Runtime cannot replay the admitted invocation.
                    with self.lock: self.connections.add(origin)
                    try:
                        response = read_frame(origin, min(deadline, time.monotonic()+timeout),
                                              max_bytes=PUBLIC_WEB_MESSAGE_BYTES)
                    finally:
                        with self.lock: self.connections.discard(origin)
                        origin.close(); origin = None
                    result, extra = self._authority({"public_web_contract": 1,
                        "receipt": begin["receipt"], "response": response},
                        min(deadline, time.monotonic()+AUTHORITY_CALL_SECONDS+1))
                    if extra is not None:
                        extra.close(); raise ValueError("Unexpected result socket")
                    if result.get("public_web_contract") != 1: raise ValueError("Unsupported public authority")
                response = {"version": 1, "request_id": request_id, "ok": result.get("ok") is True}
                if response["ok"]: response["response"] = result["response"]
                else: response["status"] = result.get("status", 503)
                connection.settimeout(remaining(deadline)); connection.sendall(_frame(response))
        except (OSError,ValueError,TypeError,KeyError,RecursionError):
            # Public client maps incomplete/closed IPC to 503. Never retry.
            pass
        finally:
            if origin is not None:
                with self.lock: self.connections.discard(origin)
                origin.close()
            connection.close()
            with self.lock:
                self.connections.discard(connection); self.workers.discard(threading.current_thread())
            self.slots.release()
