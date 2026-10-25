"""Real Core authority, sealed event grant, independent stdlib Runtime and service."""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import pwd
import socket
import subprocess
import sys
import time

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from backend.db.device import DeviceEvent
from backend.db.module import ApplicationEventDelivery as Delivery, ApplicationEventCursor as Cursor, ApplicationExtensionInstallation as Installation
from backend.tests.test_application_event_authority import (
    events as event_granted, core_installed, source_subject, source_installed,
    activate as activate_events, replace_package,
)
from backend.tests.test_platform_runtime_process import core_stack, activate
from backend.tests.test_application_public_web_transport import SERVICE, wait_for
from three_mm_platform_runtime.server import probe_runtime

pytestmark=pytest.mark.skipif(sys.platform!='linux',reason='Real Linux processes/FD ownership')
SOURCE=Path(__file__).resolve().parents[2]
# Match the admitted event operation's strict empty-object response schema.
SERVICE=SERVICE.replace("result={'status':200,'content_type':'text/html; charset=utf-8','headers':{},'body':'<h1>Public</h1>'}","result={}")
SERVICE=SERVICE.replace("if mode=='request_id':response['request_id']='foreign'", "if mode=='request_id':response=sign_message({**response,'request_id':'foreign'},secret)")


@pytest.fixture
def event_core(event_granted,monkeypatch,request):
    from backend.services import application_events as broker
    state=event_granted
    monkeypatch.setattr(broker,'_send_event_invocation',state.event_sender)
    definition=state.validated.application_extension.model_dump(mode='json')
    for operation in definition['operations']:
        if operation['operation_id']=='process_scan':
            operation['timeout_seconds']=10 if 'core_restart' in request.node.name else 2
    replace_package(state,definition,state.validated.manifest.model_dump(mode='json'))
    activate_events(state)
    with core_stack(state,monkeypatch) as s:yield s


@pytest.fixture
def event_stack(event_core):
    s=event_core;root=s.base/'event-host';root.mkdir(mode=0o755);(root/'mode').write_text('valid')
    options={}
    if os.geteuid()==0:
        app=pwd.getpwnam('3mm-app');os.chown(root,app.pw_uid,app.pw_gid)
        options={'user':app.pw_uid,'group':app.pw_gid,'extra_groups':[]}
    peer=subprocess.Popen(['/usr/bin/python3','-c',SERVICE,str(root),(b's'*32).hex()],cwd=SOURCE,
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(SOURCE)},
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**options)
    engine=create_engine('sqlite:///'+str(s.base/'core/3mm.db'))
    try:
        wait_for(lambda:(root/'service.sock').exists())
        with Session(engine) as db:
            db.execute(update(Installation).where(Installation.id==1).values(socket_path=str(root/'service.sock')));db.commit()
        s.control.event_worker=True
        activate(s,s.artifact('event-a'))
        def enqueue(suffix):
            with Session(engine) as db:
                event=DeviceEvent(device_id=1,event_id='evt_'+suffix+'0'*(32-len(suffix)),
                    event_type='device.changed.v1',occurred_at=datetime.now(UTC),
                    payload={'capability_id':'gpio.digital.control','value':True})
                db.add(event);db.commit();identifier=event.id
            s.command('event_enqueue')
            return identifier
        def deliveries():
            with Session(engine) as db:
                return [dict(id=d.id,status=d.status,attempts=d.attempts,dispatch_id=d.dispatch_id,
                    metadata=d.dispatch_metadata,error=d.last_error) for d in db.scalars(select(Delivery).order_by(Delivery.id))]
        def seen():
            try:return [json.loads(line) for line in (root/'seen').read_text().splitlines()]
            except FileNotFoundError:return []
        s.enqueue=enqueue;s.deliveries=deliveries;s.seen=seen;s.event_root=root;s.event_peer=peer;s.event_engine=engine
        yield s
    finally:
        peer.terminate()
        try:peer.wait(timeout=2)
        except subprocess.TimeoutExpired:peer.kill();peer.wait(timeout=2)
        engine.dispose()


def test_real_worker_acknowledges_durable_event_and_preserves_core(event_stack):
    s=event_stack;before=s.command('fingerprint');identifier=s.enqueue('once')
    wait_for(lambda:s.deliveries() and s.deliveries()[0]['status']=='acknowledged')
    row=s.deliveries()[0];assert row['attempts']==1
    request=s.seen()[0]
    assert request['operation_id']=='process_scan'
    assert request['context']['idempotency_key']==request['payload']['event_id']
    assert request['payload']['event_type']=='device.changed.v1'
    s.command('event_enqueue');time.sleep(.1)
    assert len(s.seen())==1 and s.http('/settings/read')[0]==200
    assert s.client.discover_platform()['instance_id']=='a'*24
    assert s.command('fingerprint')==before
    with Session(s.event_engine) as db:assert db.scalar(select(Cursor)).acknowledged_count==1


@pytest.mark.parametrize('mode',['signature','request_id','trickle','hang'])
def test_bad_or_blocked_handler_is_bounded_and_core_stays_administrable(event_stack,mode):
    s=event_stack;before=s.command('fingerprint');(s.event_root/'mode').write_text(mode)
    s.enqueue(mode)
    wait_for(lambda:len(s.seen())==1)
    for _ in range(4):assert s.http('/settings/read')[0]==200
    assert s.client.discover_platform()['instance_id']=='a'*24
    wait_for(lambda:s.deliveries()[0]['status']=='pending',seconds=5)
    assert s.deliveries()[0]['attempts']==1
    time.sleep(.1);assert len(s.seen())==1
    (s.event_root/'mode').write_text('valid');s.command('event_retry')
    wait_for(lambda:s.deliveries()[0]['status']=='acknowledged')
    assert s.deliveries()[0]['attempts']==2 and len(s.seen())==2
    assert s.command('fingerprint')==before


def test_runtime_kill_cannot_replay_until_durable_lease_expires(event_stack):
    s=event_stack;before=s.command('fingerprint');(s.event_root/'mode').write_text('pause')
    s.enqueue('lost');wait_for(lambda:len(s.seen())==1)
    first=s.deliveries()[0];assert first['status']=='delivering' and first['attempts']==1
    s.control.process.kill();s.control.process.wait(timeout=3)
    (s.event_root/'mode').write_text('valid')
    s.control.start();s.control.health(s.store.target('current'))
    time.sleep(.2);assert s.deliveries()[0]['dispatch_id']==first['dispatch_id'] and len(s.seen())==1
    # Controlled expiry in the owned test DB, not a claim to have waited 40 s.
    s.command('event_expire')
    wait_for(lambda:s.deliveries()[0]['status']=='acknowledged')
    assert s.deliveries()[0]['attempts']==2
    assert s.seen()[0]['context']['idempotency_key']==s.seen()[1]['context']['idempotency_key']
    assert s.command('fingerprint')==before and s.http()[0]==200


def test_core_restart_keeps_same_runtime_claim_and_records_original_response(event_stack):
    s=event_stack;(s.event_root/'mode').write_text('pause');s.enqueue('core')
    wait_for(lambda:len(s.seen())==1)
    first=s.deliveries()[0];runtime=s.control.process.pid;peer=s.event_peer.pid;old=s.core.pid
    s.restart_core();assert s.core.pid!=old and s.http()[0]==200
    assert s.control.process.pid==runtime and s.event_peer.pid==peer
    (s.event_root/'mode').write_text('valid')
    wait_for(lambda:s.deliveries()[0]['status']=='acknowledged')
    assert s.deliveries()[0]['dispatch_id']==first['dispatch_id'] and s.deliveries()[0]['attempts']==1
    assert len(s.seen())==1


def test_revocation_before_next_attempt_cannot_renew_old_event_grant(event_stack):
    s=event_stack;(s.event_root/'mode').write_text('signature');s.enqueue('revoked')
    wait_for(lambda:s.deliveries() and s.deliveries()[0]['status']=='pending' and s.deliveries()[0]['attempts']==1)
    s.command('revoke');(s.event_root/'mode').write_text('valid');s.command('event_retry')
    wait_for(lambda:s.deliveries()[0]['status']=='dead_letter')
    assert s.deliveries()[0]['attempts']==1 and len(s.seen())==1
    assert s.http('/settings/read')[0]==200


def test_independent_update_rollback_and_bad_candidate_preserve_event_journal(event_stack):
    s=event_stack;before=s.command('fingerprint');peer=s.event_peer.pid;first=s.store.target('current')
    s.enqueue('first');wait_for(lambda:s.deliveries() and s.deliveries()[0]['status']=='acknowledged')
    activate(s,s.artifact('event-b'))
    s.enqueue('second');wait_for(lambda:len(s.deliveries())==2 and s.deliveries()[1]['status']=='acknowledged')
    s.store.rollback(control=s.control,health=s.control.health,fingerprint=lambda:s.command('fingerprint'))
    assert s.store.target('current')==first
    with pytest.raises(Exception):activate(s,s.artifact('event-bad',broken=True))
    assert s.event_peer.pid==peer and s.event_peer.poll() is None
    assert s.command('fingerprint')==before
    assert [d['attempts'] for d in s.deliveries()]==[1,1] and len(s.seen())==2


@pytest.mark.skipif(os.geteuid()!=0,reason='Root driver with existing distinct OS principals')
def test_distinct_event_worker_cannot_read_core_database_or_transport_key(event_stack):
    s=event_stack
    assert s.core_uid!=s.runtime_uid
    s.enqueue('principals');wait_for(lambda:s.deliveries() and s.deliveries()[0]['status']=='acknowledged')
    app=pwd.getpwnam('3mm-app')
    script="from pathlib import Path;import sys;\nfor p in sys.argv[1:]:\n try:Path(p).read_bytes()\n except PermissionError:continue\n raise SystemExit('unexpected Core access')"
    for uid,gid in [(s.runtime_uid,s.runtime_uid),(app.pw_uid,app.pw_gid)]:
        result=subprocess.run(['/usr/bin/python3','-c',script,str(s.base/'core/3mm.db'),
            str(s.base/'core/transport'/('a'*24+'.key'))],user=uid,group=gid,extra_groups=[],
            capture_output=True,text=True,timeout=5)
        assert result.returncode==0,result.stderr
    assert s.http('/settings/read')[0]==200


def test_core_crash_after_durable_send_before_fd_handoff_keeps_unknown_attempt(event_stack):
    s=event_stack;runtime=s.control.process.pid
    trigger=s.base/'crash-before-handoff';trigger.write_text('owned test Core only')
    # Enqueue via the real Core and let the child terminate itself before handoff.
    try:s.enqueue('handoff')
    except (EOFError,AssertionError):pass
    s.core.join(timeout=5);assert s.core.exitcode==17
    wait_for(lambda:len(s.seen())==1)
    assert s.deliveries()[0]['status']=='delivering' and s.deliveries()[0]['attempts']==1
    trigger.unlink();s.restart_core()
    assert s.control.process.pid==runtime and s.http()[0]==200
    time.sleep(.2);assert len(s.seen())==1
    s.command('event_expire')
    wait_for(lambda:s.deliveries()[0]['status']=='acknowledged')
    assert s.deliveries()[0]['attempts']==2
    assert s.seen()[0]['context']['idempotency_key']==s.seen()[1]['context']['idempotency_key']
    with Session(s.event_engine) as db:assert db.scalar(select(Cursor)).acknowledged_count==1


def test_cold_runtime_with_pending_blocked_handler_reports_worker_readiness(event_stack):
    s=event_stack;s.control.stop();(s.event_root/'mode').write_text('pause')
    s.enqueue('cold');s.control.start();s.control.health(s.store.target('current'))
    wait_for(lambda:len(s.seen())==1)
    assert probe_runtime(s.base/'runtime/runtime.sock',expected_uid=s.runtime_uid,require_events=True)['event_worker_ready']
    assert s.deliveries()[0]['status']=='delivering' and s.http()[0]==200
    (s.event_root/'mode').write_text('valid')
    wait_for(lambda:s.deliveries()[0]['status']=='acknowledged')


def test_event_feature_probe_refuses_core_without_delivery_support(tmp_path):
    import threading
    from three_mm_platform_runtime.server import probe_core
    from three_mm_platform_wire import receive_authority_frame
    path=tmp_path/'old.sock'
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
        listener.bind(str(path));listener.listen(1)
        def older_core():
            with listener.accept()[0] as connection:
                request,origin=receive_authority_frame(connection,time.monotonic()+2)
                assert origin is None and request['event_delivery_contract']==1
                connection.sendall(json.dumps({k:request[k] for k in ('authority_probe','authority_contract')}).encode()+b'\n')
        thread=threading.Thread(target=older_core);thread.start()
        try:
            with pytest.raises(ValueError,match='contract'):probe_core(path,os.geteuid(),events=True)
        finally:thread.join(timeout=3)
        assert not thread.is_alive()
