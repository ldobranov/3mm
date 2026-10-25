"""Policy-test response peer; real Runtime/FD/deadline behavior has process tests.

Retain each existing test's service mock or actual signed peer. Only emulate the
Runtime return channel; Core still executes fresh admission and result checking.
"""
import time
from backend.services import application_invocation_relay as relay
from backend.services import application_extensions as gateway
from three_mm_runtime.application_transport import sign_message


def install_response_transport(monkeypatch):
    class Waiter:
        handoff_deadline=0
        timeout_seconds=10
        def close(self):pass
        async def receive(self):return self.response
    def reserve(settings):
        waiter=Waiter();waiter.handoff_deadline=time.monotonic()+2;return waiter
    def send(waiter,prepared,request_id):
        client=gateway.ApplicationServiceClient(prepared.socket_path,prepared.secret,prepared.timeout_seconds)
        result=client.invoke(prepared.operation_id,prepared.payload,prepared.context,
            **({'relational_invocation':prepared.relational_invocation} if prepared.relational_invocation is not None else {}))
        waiter.response=sign_message({'version':1,'timestamp':int(time.time()),'request_id':request_id,'ok':True,'result':result},prepared.secret)
    monkeypatch.setattr(relay,'_reserve',reserve);monkeypatch.setattr(relay,'_send',send)
