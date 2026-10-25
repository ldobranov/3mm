"""Response-only capability boundary, framing, FD ownership and result integrity."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
import socket
import threading
import time
from types import SimpleNamespace
import uuid

import pytest
from backend.services.application_response_relay import ResponseWaiter
from backend.services.application_status_probe import StatusProbe,snapshot,finish_status_probe
from three_mm_platform_runtime.responses import ApplicationResponses
from three_mm_platform_wire import send_authority_frame,read_frame
from three_mm_runtime.application_transport import sign_message

pytestmark=pytest.mark.skipif(os.name!='posix' or os.geteuid()==0,reason='Unprivileged Linux functional lab; distinct-UID proof is separate')


@contextmanager
def relay(tmp_path,*,core_uid=None):
    server=ApplicationResponses(tmp_path/'response.sock',tmp_path/'unused.sock',core_uid=core_uid or os.geteuid())
    server.start();thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield server
    finally:server.close();thread.join(timeout=2)


def wait_empty(server):
    until=time.monotonic()+2
    while server.connections:
        assert time.monotonic()<until
        time.sleep(.005)


def test_relay_reads_one_original_frame_and_does_not_dispatch(tmp_path):
    with relay(tmp_path) as server:
        waiter=ResponseWaiter.reserve(server.path,os.geteuid())
        origin,peer=socket.socketpair()
        with peer:
            waiter.handoff(origin)
            with pytest.raises(BrokenPipeError):origin.send(b"must-not-dispatch")
            origin.close()
            peer.sendall(b'{"unicode":"test"}\n')
            assert asyncio.run(waiter.receive())=={'unicode':'test'}
            peer.settimeout(.05)
            assert peer.recv(1024)==b''  # Runtime wrote no request bytes to this FD.
        waiter.close();wait_empty(server)


@pytest.mark.parametrize('phase',['reserve_fd','handoff_missing_fd','handoff_version','handoff_nonce','handoff_timeout'])
def test_rejected_handoff_closes_every_received_fd_and_slot(tmp_path,phase):
    with relay(tmp_path) as server:
        before=len(list(Path('/proc/self/fd').iterdir()))
        for _ in range(12):
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
                connection.settimeout(1);connection.connect(str(server.path));nonce=uuid.uuid4().hex
                origin,peer=socket.socketpair()
                with origin,peer:
                    hello={'application_response_contract':1,'reserve':nonce}
                    send_authority_frame(connection,hello,origin=origin if phase=='reserve_fd' else None)
                    if phase!='reserve_fd':
                        assert read_frame(connection,time.monotonic()+1)['reserved']==nonce
                        value={'application_response_contract':1,'reserved':nonce,'timeout_seconds':1}
                        if phase=='handoff_version':value['application_response_contract']=True
                        if phase=='handoff_nonce':value['reserved']='wrong'
                        if phase=='handoff_timeout':value['timeout_seconds']=31
                        send_authority_frame(connection,value,origin=None if phase=='handoff_missing_fd' else origin)
                    assert connection.recv(1024)==b''
            wait_empty(server)
        assert len(list(Path('/proc/self/fd').iterdir()))<=before+1


def test_wrong_runtime_identity_fails_before_fd_handoff(tmp_path):
    with relay(tmp_path) as server:
        with pytest.raises(ValueError,match='principal'):ResponseWaiter.reserve(server.path,os.geteuid()+1)
        wait_empty(server)


def test_foreign_core_is_rejected_before_receiving_metadata(tmp_path):
    with relay(tmp_path,core_uid=os.geteuid()+1) as server:
        with pytest.raises((OSError,ValueError)):ResponseWaiter.reserve(server.path,os.geteuid())
        wait_empty(server)


def test_expired_reservation_cannot_handoff_an_app_socket(tmp_path):
    with relay(tmp_path) as server:
        waiter=ResponseWaiter.reserve(server.path,os.geteuid());waiter.handoff_deadline=0
        origin,peer=socket.socketpair()
        with origin,peer:
            with pytest.raises(TimeoutError):waiter.handoff(origin)
        waiter.close();wait_empty(server)


def test_no_fd_or_slot_survives_runtime_shutdown(tmp_path):
    with relay(tmp_path) as server:
        waiter=ResponseWaiter.reserve(server.path,os.geteuid());origin,peer=socket.socketpair()
        waiter.handoff(origin);origin.close()
        server.close()
        with pytest.raises((OSError,ValueError)):asyncio.run(waiter.receive())
        peer.close();waiter.close()


@pytest.fixture
def admitted_status(tmp_path):
    app=SimpleNamespace(id=1,instance_id='a'*24,authority_incarnation='b'*32,authority_epoch='c'*32,
        module_package_id=1,enabled=True,status='active')
    package=SimpleNamespace(sha256='d'*64)
    settings=SimpleNamespace(key_root=tmp_path);(tmp_path/(app.instance_id+'.key')).write_bytes(b's'*32)
    probe=StatusProbe(1,snapshot(app,package),b's'*32,uuid.uuid4().hex)
    result={'revision':'0001','outbox':{'pending':2},'outbox_inspected':True}
    def finish(result=result,*,request_id=None,secret=b's'*32):
        response=sign_message({'version':1,'request_id':request_id or probe.request_id,'timestamp':int(time.time()),
            'ok':True,'result':result},secret)
        return finish_status_probe(probe,response,app,package,settings)
    return app,package,settings,probe,result,finish


def test_current_signed_status_is_observation_only(admitted_status):
    app,package,settings,probe,result,finish=admitted_status
    assert finish()==result
    assert app.authority_epoch=='c'*32
    relational={'revision':'0001','outbox':{},'outbox_inspected':False}
    assert finish(relational)==relational


@pytest.mark.parametrize('damage',['instance','incarnation','epoch','package','disabled','key','signature','request'])
def test_stale_foreign_or_unverifiable_status_cannot_be_disclosed(admitted_status,damage):
    app,package,settings,probe,result,finish=admitted_status
    if damage=='instance':app.instance_id='e'*24
    elif damage=='incarnation':app.authority_incarnation='e'*32
    elif damage=='epoch':app.authority_epoch='e'*32
    elif damage=='package':package.sha256='e'*64
    elif damage=='disabled':app.enabled=False
    elif damage=='key':(settings.key_root/(app.instance_id+'.key')).write_bytes(b'z'*32)
    elif damage=='signature':assert finish(secret=b'x'*32) is None;return
    else:assert finish(request_id='foreign') is None;return
    assert finish() is None


@pytest.mark.parametrize('result',[
    {'revision':True,'outbox':{}}, {'revision':'x'*129,'outbox':{}},
    {'revision':'0001','outbox':{'pending':-1}}, {'revision':'0001','outbox':{'pending':True}},
    {'revision':'0001','outbox':{'pending':'private text'}}, {'revision':'0001','outbox':[]},
    {'revision':'0001','outbox':{str(i):0 for i in range(33)}},
    {'revision':'0001','outbox':{},'outbox_inspected':'no'},
])
def test_malformed_host_telemetry_is_unavailable(admitted_status,result):
    assert admitted_status[-1](result) is None


@pytest.mark.parametrize('drift',['disabled','epoch','package','deadline'])
def test_status_admission_rechecks_after_reservation_before_any_app_send(connector_db,tmp_path,monkeypatch,drift):
    import pwd
    from sqlalchemy import update
    from backend.db.module import ApplicationExtensionInstallation as Installation,ModulePackage
    from backend.services.application_status_probe import begin_status_probe
    db,app=connector_db;package=db.get(ModulePackage,app.module_package_id)
    (tmp_path/(app.instance_id+'.key')).write_bytes(b's'*32)
    settings=SimpleNamespace(key_root=tmp_path,runtime_user=pwd.getpwuid(os.geteuid()).pw_name,
        application_response_socket=tmp_path/'unused.sock')
    closed=[]
    reserved=SimpleNamespace(handoff_deadline=time.monotonic()+2,close=lambda:closed.append(True))
    def reserve(cls,*args):
        if drift=='disabled':db.execute(update(Installation).values(enabled=False))
        elif drift=='epoch':db.execute(update(Installation).values(authority_epoch='e'*32))
        elif drift=='package':db.execute(update(ModulePackage).values(sha256='e'*64))
        else:reserved.handoff_deadline=0
        db.commit();return reserved
    monkeypatch.setattr(ResponseWaiter,'reserve',classmethod(reserve))
    with pytest.raises((ValueError,TimeoutError)):begin_status_probe(db,app,package,settings)
    assert closed==[True] and not db.in_transaction()


from backend.tests.test_application_connectors import connector_db


def test_enabled_response_channel_refuses_core_without_current_feature(tmp_path):
    from three_mm_platform_runtime.server import probe_core
    from three_mm_platform_wire import receive_authority_frame
    path=tmp_path/'old-core.sock';listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);listener.bind(str(path));listener.listen(1)
    def old_core():
        connection,_=listener.accept()
        with connection:
            value,origin=receive_authority_frame(connection,time.monotonic()+1)
            assert origin is None and value.pop('application_response_contract')==1
            connection.sendall(json.dumps(value).encode()+b'\n')
    worker=threading.Thread(target=old_core);worker.start()
    try:
        with pytest.raises(ValueError,match='contract'):probe_core(path,os.geteuid(),responses=True)
    finally:worker.join(timeout=2);listener.close()
