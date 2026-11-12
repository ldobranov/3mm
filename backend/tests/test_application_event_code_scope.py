"""Count real immutable verification per event RPC without caching authority."""
import hashlib
import os
import socket
import time

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.db.device import DeviceEvent
from backend.db.module import ApplicationEventDelivery
from backend.applications.events import broker
from backend.artifacts import packages as module_packages
from backend.tests.test_application_event_authority import (
    events, core_installed, source_subject, source_installed, activate, event, identity,
)
from packages.platform_wire import receive_authority_frame, read_frame


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real POSIX sealed event admission and FD handoff')


def prepare(s, monkeypatch):
    import backend.database as database
    activate(s)
    identifier=event(s)
    with Session(s.engine) as db:
        broker.enqueue_application_event(db,db.get(DeviceEvent,identifier),s.settings,capture_only=True)
    monkeypatch.setattr(database,'SessionLocal',sessionmaker(bind=s.engine))
    # The fixture manager pins 0.3.0; production's implicit and explicit version
    # policies agree. Distinct version policies must not share a cached parse.
    monkeypatch.setattr(module_packages,'actual_core_version',lambda:s.manager.core_version)


def exchange(s, request):
    left,right=socket.socketpair()
    try:
        broker.handle_event_delivery(left,request,key_root=s.settings.key_root,runtime_generation='code-scope-test')
        return receive_authority_frame(right,time.monotonic()+1)
    finally:left.close();right.close()


def claim(s):
    return exchange(s,{'event_delivery_contract':1,'claim':True,
        'claim_deadline_ms':int((time.monotonic()+10)*1000)})


def test_claim_verifies_real_zip_once_but_rechecks_grant_and_completion_reloads(events,monkeypatch):
    s=events;prepare(s,monkeypatch)
    parses=[];checks=[]
    validate=module_packages.validate_module_package
    require=s.manager._require_grant
    def counted_package(blob,**kwargs):
        parses.append((hashlib.sha256(blob).hexdigest(),kwargs.get('core_version')))
        return validate(blob,**kwargs)
    def counted_grant(*args,**kwargs):
        checks.append(1)
        return require(*args,**kwargs)
    monkeypatch.setattr(module_packages,'validate_module_package',counted_package)
    monkeypatch.setattr(s.manager,'_require_grant',counted_grant)
    result,origin=claim(s)
    assert result['ok'] and not result['idle'] and origin is not None
    try:response=read_frame(origin,time.monotonic()+1)
    finally:origin.close()
    assert parses==[(s.validated.sha256,s.manager.core_version)]
    assert len(checks)==2  # Preliminary resource check AND final durable admission.
    assert len(s.calls)==1
    completed,origin=exchange(s,{'event_delivery_contract':1,'receipt':result['receipt'],'response':response})
    assert completed['status']=='acknowledged' and origin is None
    assert parses==[(s.validated.sha256,s.manager.core_version)]*2
    # The completion is a different RPC and must re-open/re-validate immutable
    # input. A duplicate outcome does not repeat the handler or its cursor update.
    again,origin=exchange(s,{'event_delivery_contract':1,'receipt':result['receipt'],'response':response})
    assert again==completed and origin is None and len(s.calls)==1
    assert len(parses)==2


@pytest.mark.parametrize('change',['replace','bytes_same_mtime','permissions'])
def test_package_drift_after_preparation_poisoned_within_claim(events,monkeypatch,change):
    s=events;prepare(s,monkeypatch)
    original=broker.prepare_application_invocation
    def change_code(*args,**kwargs):
        result=original(*args,**kwargs)
        blob=s.archive.read_bytes();before=s.archive.stat()
        if change=='replace':
            s.archive.unlink();s.archive.write_bytes(blob)
        elif change=='permissions':
            s.archive.chmod(0o666)
        else:
            s.archive.write_bytes(blob[:-1]+bytes([blob[-1]^1]))
            os.utime(s.archive,ns=(before.st_atime_ns,before.st_mtime_ns))
        return result
    monkeypatch.setattr(broker,'prepare_application_invocation',change_code)
    result,origin=claim(s)
    assert result['ok'] and result['idle'] and origin is None and not s.calls
    with Session(s.engine) as db:
        row=db.scalar(select(ApplicationEventDelivery))
        assert row.status=='dead_letter' and row.attempts==0


def test_revocation_after_preparation_remains_a_fresh_final_admission(events,monkeypatch):
    s=events;prepare(s,monkeypatch)
    revision=s.manager.inspect(1)['grant_record_revision']
    original=broker.prepare_application_invocation
    def revoke(*args,**kwargs):
        result=original(*args,**kwargs)
        s.manager.revoke(1,actor_token=s.token,request_id=identity(),expected_revision=revision)
        return result
    monkeypatch.setattr(broker,'prepare_application_invocation',revoke)
    result,origin=claim(s)
    assert result['ok'] and result['idle'] and origin is None and not s.calls
    with Session(s.engine) as db:
        row=db.scalar(select(ApplicationEventDelivery))
        assert row.status=='dead_letter' and row.attempts==0
