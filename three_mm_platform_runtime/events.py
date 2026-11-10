"""One bounded event-response worker; no DB, transport keys or grant cache."""
import socket
import threading
import time

from three_mm_platform_wire import (
    read_frame, receive_authority_frame, remaining, send_authority_frame,
)
from three_mm_platform_wire.event_delivery import CLAIM_SECONDS, COMPLETION_SECONDS, lease_remaining
from three_mm_platform_runtime.server import _core_connection


class EventDeliveryWorker:
    def __init__(self, authority_path, *, core_uid):
        self.authority_path=authority_path;self.core_uid=core_uid
        self.stop_event=threading.Event();self.thread=None;self.ready=False
        self.lock=threading.Lock();self.connections=set()

    def start(self):
        self.thread=threading.Thread(target=self.run,name="3mm-event-response",daemon=True)
        self.thread.start()

    def request_stop(self):
        self.stop_event.set()
        with self.lock:connections=list(self.connections)
        for connection in connections:
            try:connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            connection.close()

    def close(self):
        self.request_stop()
        if self.thread is not None and self.thread.ident is not None:self.thread.join(timeout=5)

    def _authority(self, request, deadline):
        upstream,_,_=_core_connection(self.authority_path,self.core_uid,deadline)
        with self.lock:self.connections.add(upstream)
        try:
            with upstream:
                upstream.settimeout(remaining(deadline));send_authority_frame(upstream,request)
                result,origin=receive_authority_frame(upstream,deadline)
            return result,origin
        finally:
            with self.lock:self.connections.discard(upstream)

    def step(self):
        # Admission can include immutable-code verification and current seals.
        # Its finite deadline is shared with Core: an expired/disconnected
        # caller cannot silently create another service dispatch.
        claim_deadline=time.monotonic()+CLAIM_SECONDS
        result,origin=self._authority({"event_delivery_contract":1,"claim":True,
            "claim_deadline_ms":int(claim_deadline*1000)},claim_deadline)
        try:
            if self.stop_event.is_set():return True
            if result.get("event_delivery_contract")!=1 or result.get("ok") is not True:
                raise ValueError("Event authority is unavailable")
            # Readiness is the negotiated queue/I/O boundary, not completion of
            # optional application work (including a cold start with backlog).
            self.ready=True
            if result.get("idle") is True:
                if origin is not None:raise ValueError("Unexpected event connection")
                return True
            timeout=result.get("timeout_seconds")
            if origin is None or type(timeout) not in {int,float} or not 0<timeout<=30:
                raise ValueError("Invalid event handoff")
            receipt=result["receipt"]
            # Start the declared handler wait after the actual FD handoff,
            # never charge Core's preparation against it. Reserve completion
            # time inside the authoritative durable lease, including suspend.
            def lease():
                return lease_remaining(result.get('lease_boot_id'),result.get('lease_deadline_ms'))
            read_seconds=min(timeout,lease()-COMPLETION_SECONDS)
            if read_seconds<=0:
                raise ValueError('Event handoff has no result budget')
            response_deadline=time.monotonic()+read_seconds
            with self.lock:self.connections.add(origin)
            try:
                try:
                    response=read_frame(origin,response_deadline,max_bytes=1024*1024)
                    completion={"response":response}
                except TimeoutError:completion={"failure":"deadline_exceeded"}
                except OSError:completion={"failure":"handler_unavailable"}
                except (ValueError,TypeError,RecursionError):completion={"failure":"response_invalid"}
            finally:
                with self.lock:self.connections.discard(origin)
                origin.close();origin=None
            if self.stop_event.is_set():return True
            completion_deadline=time.monotonic()+min(COMPLETION_SECONDS,lease())
            result,extra=self._authority({"event_delivery_contract":1,"receipt":receipt,**completion},
                completion_deadline)
            if extra is not None:
                extra.close();raise ValueError("Unexpected event result connection")
            if result.get("event_delivery_contract")!=1 or result.get("ok") is not True:
                raise ValueError("Event result was not recorded")
            return False
        finally:
            if origin is not None:origin.close()

    def run(self):
        while not self.stop_event.is_set():
            try:
                idle=self.step();self.ready=True
            except (OSError,ValueError,TypeError,KeyError,RecursionError):
                self.ready=False;idle=True
                # A lost result is never resent. Core's durable lease determines
                # when a fresh, currently authorized attempt may be selected.
            if idle:self.stop_event.wait(1)
