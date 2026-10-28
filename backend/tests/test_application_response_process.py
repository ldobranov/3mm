"""Actual Core HTTP admission, independent Runtime response FD relay and service."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,UTC
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session
from backend.db.base import Base
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.tests.test_platform_runtime_process import (
    core_stack, activate, identity_app, managed_installed, source_subject, source_installed, checkpoint_app, activate_identity_grant,
)
from backend.tests.test_application_public_web_transport import SERVICE,wait_for
from three_mm_platform_runtime.server import probe_runtime

pytestmark=pytest.mark.skipif(os.name!='posix',reason='Actual Linux peers, FD transfer and processes')
SOURCE=Path(__file__).resolve().parents[2]
SERVICE=SERVICE.replace("result={'status':200,'content_type':'text/html; charset=utf-8','headers':{},'body':'<h1>Public</h1>'}","result={'revision':'0001','outbox':{'pending':2,'delivered':3}}")
SERVICE=SERVICE.replace("if mode=='request_id':response['request_id']='foreign'", "if mode=='request_id':response=sign_message({**response,'request_id':'foreign'},secret)")
SERVICE=SERVICE.replace("if mode=='size':result['body']='x'*4097", "if mode=='size':result['body']='x'*(1024*1024)")


@pytest.fixture
def status_core(identity_app,monkeypatch,request):
    from backend.services.application_response_relay import ResponseWaiter
    state=identity_app;activate_identity_grant(state)
    Base.metadata.create_all(state.engine)
    state.response_relay=True
    reserve=ResponseWaiter.reserve
    def short_reserve(cls,*args,**kwargs):
        waiter=reserve(*args,**kwargs);waiter.timeout_seconds=getattr(request,'param',1);return waiter
    monkeypatch.setattr(ResponseWaiter,'reserve',classmethod(short_reserve))
    with core_stack(state,monkeypatch) as s:yield s


@pytest.fixture
def status_stack(status_core):
    s=status_core;root=s.base/'status-host';root.mkdir(mode=0o755);(root/'mode').write_text('valid')
    (s.base/'responses').mkdir(mode=0o750)
    options={}
    if os.geteuid()==0:
        import pwd
        app=pwd.getpwnam('3mm-app');os.chown(root,app.pw_uid,app.pw_gid)
        options={'user':app.pw_uid,'group':app.pw_gid,'extra_groups':[]}
        os.chown(s.base/'responses',s.runtime_uid,s.core_uid);(s.base/'responses').chmod(0o2750)
    process=subprocess.Popen(['/usr/bin/python3','-c',SERVICE,str(root),(b's'*32).hex()],cwd=SOURCE,
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(SOURCE)},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**options)
    try:
        wait_for(lambda:(root/'service.sock').exists())
        with s.state.engine.begin() as db:db.execute(update(Installation).where(Installation.id==1).values(socket_path=str(root/'service.sock')))
        s.control.response_path=s.base/'responses/runtime.sock'
        activate(s,s.artifact('responses-a'))
        def seen():
            try:return [json.loads(line) for line in (root/'seen').read_text().splitlines()]
            except FileNotFoundError:return []
        with Session(s.state.engine) as db:module_id=db.get(Installation,1).module_id
        path=f'/api/v1/application-extensions/{module_id}/operational-status'
        def status(headers=None):
            return s.http(path,headers=s.admin if headers is None else headers)[1]
        s.status=status;s.status_path=path;s.seen=seen;s.status_root=root;s.status_peer=process
        yield s
    finally:
        process.terminate()
        try:process.wait(timeout=2)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)


def test_status_roundtrip_keeps_response_auth_and_core_metadata(status_stack):
    s=status_stack;before=s.command('fingerprint')
    result=s.status()
    assert result['runtime_observation']=={'status':'available','outbox_inspected':True}
    assert result['storage']['runtime_revision']=='0001' and result['outbox']=={'pending':2,'delivered':3}
    assert len(s.seen())==1 and s.seen()[0]['operation_id']=='three_mm.platform.status'
    assert s.command('fingerprint')==before
    assert s.command('threadpool_tokens')==0


@pytest.mark.parametrize('mode',['hang','trickle','signature','request_id','size'])
def test_failed_status_is_bounded_and_never_resubmitted(status_stack,mode):
    s=status_stack;(s.status_root/'mode').write_text(mode);start=time.monotonic()
    result=s.status()
    assert time.monotonic()-start<2
    assert result['runtime_observation']['status']=='unavailable'
    assert result['storage']['declared_revision'] and result['storage']['runtime_revision'] is None
    assert result['outbox']=={} and len(s.seen())==1
    assert s.http('/api/v1/diagnostics/components',headers=s.admin)[0]==200


@pytest.mark.parametrize('status_core',[5],indirect=True)
def test_status_can_complete_after_two_seconds_within_production_budget(status_stack):
    s=status_stack;(s.status_root/'mode').write_text('pause')
    start=time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(s.status);wait_for(lambda:len(s.seen())==1)
        try:
            time.sleep(2.2)
        finally:
            (s.status_root/'mode').write_text('valid')
        result=pending.result(timeout=2)
    assert 2<time.monotonic()-start<5
    assert result['runtime_observation']=={'status':'available','outbox_inspected':True}
    assert result['storage']['runtime_revision']=='0001' and result['outbox']=={'pending':2,'delivered':3}
    assert len(s.seen())==1 and s.command('threadpool_tokens')==0


@pytest.mark.parametrize('status_core',[5],indirect=True)
def test_full_response_pool_rejects_before_dispatch_and_leaves_core_threads_free(status_stack):
    s=status_stack;(s.status_root/'mode').write_text('pause')
    # This case uses the production 5 s budget; other faults use a short 1 s probe.
    with ThreadPoolExecutor(max_workers=16) as pool:
        pending=[]
        for count in range(1,9):
            pending.append(pool.submit(s.status));wait_for(lambda:len(s.seen())==count)
        assert s.command('threadpool_tokens')<2
        start=time.monotonic()
        with s.state.engine.begin() as db:
            db.execute(update(Installation).where(Installation.id==1).values(health_checked_at=datetime.now(UTC)))
        assert time.monotonic()-start<.5  # No Core DB lock spans an application wait.
        start=time.monotonic()
        extra=[pool.submit(s.status) for _ in range(8)]
        assert all(p.result(timeout=1)['runtime_observation']['status']=='unavailable' for p in extra)
        assert len(s.seen())==8
        assert s.http('/api/v1/diagnostics/components',headers=s.admin)[0]==200
        assert s.http('/settings/read')[0]==200 and time.monotonic()-start<1
        (s.status_root/'mode').write_text('valid')
        assert all(p.result(timeout=2)['runtime_observation']['status']=='available' for p in pending)


def test_revoke_during_status_discards_old_runtime_data(status_stack):
    s=status_stack;(s.status_root/'mode').write_text('pause')
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(s.status);wait_for(lambda:s.seen())
        s.command('revoke');(s.status_root/'mode').write_text('valid')
        result=pending.result(timeout=2)
    assert result['runtime_observation']['status']=='unavailable' and result['outbox']=={}
    assert len(s.seen())==1


def test_disabled_status_never_opens_application_socket(status_stack):
    s=status_stack
    with s.state.engine.begin() as db:db.execute(update(Installation).where(Installation.id==1).values(enabled=False,status='disabled'))
    result=s.status()
    assert result['runtime_observation']['status']=='inactive' and s.seen()==[]


def test_runtime_kill_and_independent_update_rollback_do_not_replay(status_stack):
    s=status_stack;before=s.command('fingerprint');a=s.store.target('current')
    (s.status_root/'mode').write_text('pause')
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(s.status);wait_for(lambda:s.seen())
        s.control.stop();result=pending.result(timeout=2)
    assert result['runtime_observation']['status']=='unavailable' and len(s.seen())==1
    (s.status_root/'mode').write_text('valid')
    activate(s,s.artifact('responses-b'));assert s.status()['runtime_observation']['status']=='available'
    s.store.rollback(control=s.control,health=s.control.health,fingerprint=lambda:s.command('fingerprint'))
    assert s.store.target('current')==a and s.status()['runtime_observation']['status']=='available'
    assert len(s.seen())==3 and s.command('fingerprint')==before


def test_non_admin_status_is_denied_before_reservation_or_app_io(status_stack):
    s=status_stack
    for headers in ({},{'Authorization':'Bearer invalid'}):
        with pytest.raises(urllib.error.HTTPError) as error:s.status(headers)
        assert error.value.code in {401,403}
    with pytest.raises(urllib.error.HTTPError) as denied:
        s.status({'Authorization':'Bearer '+s.state.user_token})
    assert denied.value.code==403
    assert s.seen()==[]


@pytest.mark.skipif(os.geteuid()!=0,reason='Separate root driver for distinct principals')
def test_distinct_runtime_cannot_read_keys_and_app_cannot_reserve(status_stack):
    s=status_stack;assert s.core_uid!=s.runtime_uid
    assert s.status()['runtime_observation']['status']=='available'
    script="import pathlib,sys;errors=0\nfor path in sys.argv[1:]:\n try:pathlib.Path(path).read_bytes();errors+=1\n except PermissionError:pass\nraise SystemExit(errors)"
    result=subprocess.run(['/usr/bin/python3','-c',script,str(s.base/'core/3mm.db'),str(s.base/'core/transport'/('a'*24+'.key'))],
        user=s.runtime_uid,group=s.runtime_uid,extra_groups=[],capture_output=True,timeout=3)
    assert result.returncode==0,result.stderr
    import pwd
    app=pwd.getpwnam('3mm-app')
    script="import socket,sys;s=socket.socket(socket.AF_UNIX);s.connect(sys.argv[1])"
    result=subprocess.run(['/usr/bin/python3','-c',script,str(s.base/'responses/runtime.sock')],
        user=app.pw_uid,group=app.pw_gid,extra_groups=[],capture_output=True,timeout=3)
    assert result.returncode!=0 and b'PermissionError' in result.stderr


def test_absent_runtime_returns_core_metadata_without_opening_application_socket(status_stack):
    s=status_stack;s.control.stop();before=s.command('fingerprint');start=time.monotonic()
    result=s.status()
    assert result['runtime_observation']['status']=='unavailable' and result['storage']['declared_revision']
    assert s.seen()==[] and time.monotonic()-start<1
    assert s.http('/api/v1/diagnostics/components',headers=s.admin)[0]==200
    assert s.command('fingerprint')==before
