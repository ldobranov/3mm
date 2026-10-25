"""Bounded response-only FD relay. Only Core can reserve; no dispatch or keys."""
import json
import re
import threading
import time

from three_mm_platform_wire import peer_identity, receive_authority_frame, read_frame, remaining
from three_mm_platform_runtime.server import PlatformRuntime

CONTRACT = 1
RESPONSE_BYTES = 1024 * 1024
REPLY_BYTES = RESPONSE_BYTES + 1024
SLOTS = 8


def encode(value):
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if len(data) > REPLY_BYTES: raise ValueError("Response relay budget exceeded")
    return data


class ApplicationResponses(PlatformRuntime):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.slots = threading.BoundedSemaphore(SLOTS)

    def _serve(self, connection):
        origin = None
        try:
            with connection:
                # Check the actual peer before reading metadata or accepting FDs.
                if peer_identity(connection)[1] != self.core_uid: return
                hello, origin = receive_authority_frame(connection, time.monotonic() + 1)
                if (origin is not None or set(hello) != {"application_response_contract", "reserve"}
                        or type(hello["application_response_contract"]) is not int
                        or hello["application_response_contract"] != CONTRACT
                        or not isinstance(hello["reserve"], str)
                        or re.fullmatch(r"[0-9a-f]{32}", hello["reserve"]) is None): return
                nonce = hello["reserve"]
                connection.settimeout(1)
                connection.sendall(encode({"application_response_contract": CONTRACT, "reserved": nonce}))
                handoff, origin = receive_authority_frame(connection, time.monotonic() + 3)
                if (origin is None or set(handoff) != {"application_response_contract", "reserved", "timeout_seconds"}
                        or type(handoff["application_response_contract"]) is not int
                        or handoff["application_response_contract"] != CONTRACT or handoff["reserved"] != nonce
                        or type(handoff["timeout_seconds"]) is not int or not 0 < handoff["timeout_seconds"] <= 30): return
                with self.lock: self.connections.add(origin)
                try:
                    response = read_frame(origin, time.monotonic() + handoff["timeout_seconds"], max_bytes=RESPONSE_BYTES)
                    result = {"response": response}
                except TimeoutError: result = {"failure": "deadline_exceeded"}
                except (OSError, ValueError, TypeError, RecursionError): result = {"failure": "response_unconfirmed"}
                connection.settimeout(1)
                connection.sendall(encode({"application_response_contract": CONTRACT, "reserved": nonce, **result}))
        except (OSError, ValueError, TypeError, KeyError, RecursionError): pass
        finally:
            if origin is not None:
                with self.lock: self.connections.discard(origin)
                origin.close()
            connection.close()
            with self.lock:
                self.connections.discard(connection); self.workers.discard(threading.current_thread())
            self.slots.release()
