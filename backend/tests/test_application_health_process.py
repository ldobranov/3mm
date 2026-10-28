"""Real admin health HTTP, signed app peer and independent response Runtime."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session
from backend.db.base import Base
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.tests.test_platform_runtime_process import (
    core_stack, activate, identity_app, managed_installed, source_subject, source_installed,
    checkpoint_app, activate_identity_grant,
)
from backend.tests.test_application_public_web_transport import SERVICE, wait_for

pytestmark=pytest.mark.skipif(os.name!='posix',reason='Actual Linux FD transfer and processes')
SOURCE=Path(__file__).resolve().parents[2]
SERVICE=SERVICE.replace("result={'status':200,'content_type':'text/html; charset=utf-8','headers':{},'body':'<h1>Public</h1>'}",
    "result=({'revision':'0001','outbox':{}} if request['operation_id']=='three_mm.platform.status' else {'status':'ready'})")
SERVICE=SERVICE.replace("if mode=='request_id':response['request_id']='foreign'", "if mode=='request_id':response=sign_message({**response,'request_id':'foreign'},secret)")
SERVICE=SERVICE.replace("if mode=='size':result['body']='x'*4097", "if mode=='size':result['body']='x'*(1024*1024)\n        if mode=='schema':result={'status':'failed'}\n        if mode=='type':result=[]")
SERVICE=SERVICE.replace("if mode=='signature':response['signature']='0'*64", "if mode=='signature':response['signature']='0'*64\n        if mode=='failure':response=sign_message({**response,'ok':False,'error':'Host failed'},secret)")


@pytest.fixture
def health_core(identity_app,monkeypatch,request):
    from backend.services import application_health_probe as health
    state=identity_app;activate_identity_grant(state);Base.metadata.create_all(state.engine)
    state.response_relay=True
    prepare=health._prepare
    def short_prepare(*args):
        prepared=prepare(*args)
        return replace(prepared,timeout_seconds=5 if 'full_shared_pool' in request.node.name else 1)
    monkeypatch.setattr(health,'_prepare',short_prepare)
    with core_stack(state,monkeypatch) as s:yield s


@pytest.fixture
def health_stack(health_core):
    s=health_core;root=s.base/'health-host';root.mkdir(mode=0o755);(root/'mode').write_text('valid')
    (s.base/'responses').mkdir(mode=0o750);options={}
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
        s.control.response_path=s.base/'responses/runtime.sock';activate(s,s.artifact('health-a'))
        def seen():
            try:return [json.loads(line) for line in (root/'seen').read_text().splitlines()]
            except FileNotFoundError:return []
        with Session(s.state.engine) as db:module_id=db.get(Installation,1).module_id
        path=f'/api/v1/application-extensions/{module_id}/health'
        def health(headers=None):
            request=urllib.request.Request(s.url()+path,headers=s.admin if headers is None else headers,method='POST')
            try:
                # The full-pool case admits the production 5 s Runtime budget;
                # this outer watchdog must not truncate a valid response.
                with urllib.request.urlopen(request,timeout=10) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as error:return error.code,json.load(error)
        def stamp():
            with Session(s.state.engine) as db:return db.get(Installation,1).health_checked_at
        s.health=health;s.seen=seen;s.health_root=root;s.stamp=stamp
        s.status_path=path.removesuffix('/health')+'/operational-status'
        yield s
    finally:
        process.terminate()
        try:process.wait(timeout=2)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)


def test_health_roundtrip_is_signed_declared_internal_and_stamps_once(health_stack):
    s=health_stack;before=s.command('fingerprint');assert s.stamp() is None
    assert s.health()==(200,{'status':'ready'})
    sent=s.seen();assert len(sent)==1 and sent[0]['operation_id']=='health'
    assert sent[0]['payload']=={} and sent[0]['context']['audience']=='internal'
    assert 'relational_invocation' not in sent[0] and s.stamp() is not None
    assert s.command('fingerprint')==before and s.command('threadpool_tokens')==0


@pytest.mark.parametrize('mode',['hang','trickle','signature','request_id','size','schema','type','failure'])
def test_invalid_or_missing_health_never_stamps_or_replays(health_stack,mode):
    s=health_stack;(s.health_root/'mode').write_text(mode);start=time.monotonic()
    assert s.health()[0]==409
    assert time.monotonic()-start<2 and len(s.seen())==1 and s.stamp() is None
    assert s.http('/api/v1/diagnostics/components',headers=s.admin)[0]==200


@pytest.mark.parametrize('change',['revoke','disabled','package','key','socket'])
def test_health_changed_during_wait_cannot_write_stale_success(health_stack,change):
    s=health_stack;(s.health_root/'mode').write_text('pause')
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(s.health);wait_for(lambda:s.seen())
        if change=='revoke':s.command('revoke')
        elif change=='key':(s.base/'core/transport'/('a'*24+'.key')).write_bytes(b'z'*32)
        else:
            with s.state.engine.begin() as db:
                if change=='disabled':db.execute(update(Installation).where(Installation.id==1).values(enabled=False,status='disabled'))
                elif change=='socket':db.execute(update(Installation).where(Installation.id==1).values(socket_path='changed'))
                else:db.execute(update(ModulePackage).where(ModulePackage.id==1).values(sha256='e'*64))
        (s.health_root/'mode').write_text('valid');assert pending.result(timeout=2)[0]==409
    assert s.stamp() is None and len(s.seen())==1
    # Resource revocation does not grant health SQL or forbid an explicit fresh readiness check.
    if change=='revoke':assert s.health()==(200,{'status':'ready'})


def test_absent_runtime_and_disabled_app_refuse_before_dispatch(health_stack):
    s=health_stack;s.control.stop();assert s.health()[0]==409
    assert s.seen()==[] and s.stamp() is None
    activate(s,s.artifact('health-enabled'))
    with s.state.engine.begin() as db:db.execute(update(Installation).where(Installation.id==1).values(enabled=False,status='disabled'))
    assert s.health()[0]==409 and s.seen()==[] and s.stamp() is None
    assert s.http('/settings/read')[0]==200


def test_health_requires_actual_admin_before_app_io(health_stack):
    s=health_stack
    for headers in ({},{'Authorization':'Bearer invalid'},{'Authorization':'Bearer '+s.state.user_token}):
        assert s.health(headers)[0] in {401,403}
    assert s.seen()==[] and s.stamp() is None


def test_full_shared_pool_leaves_core_threads_and_db_free(health_stack):
    s=health_stack;(s.health_root/'mode').write_text('pause')
    with ThreadPoolExecutor(max_workers=12) as pool:
        pending=[]
        for count in range(1,9):
            pending.append(pool.submit(s.health if count%2 else lambda:s.http(s.status_path,headers=s.admin)))
            wait_for(lambda:len(s.seen())==count)
        assert s.command('threadpool_tokens')<2
        start=time.monotonic()
        with s.state.engine.begin() as db:db.execute(update(Installation).where(Installation.id==1).values(error='independent-writer'))
        assert time.monotonic()-start<.5
        start=time.monotonic();assert s.health()[0]==409 and len(s.seen())==8
        assert s.http('/api/v1/diagnostics/components',headers=s.admin)[0]==200
        assert s.http('/settings/read')[0]==200 and time.monotonic()-start<1
        (s.health_root/'mode').write_text('valid')
        assert all(p.result(timeout=2)[0]==200 for p in pending)


def test_runtime_kill_update_rollback_preserve_core_and_do_not_resend_health(health_stack):
    s=health_stack;before=s.command('fingerprint');a=s.store.target('current')
    (s.health_root/'mode').write_text('pause')
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(s.health);wait_for(lambda:s.seen());s.control.stop()
        assert pending.result(timeout=2)[0]==409
    assert s.stamp() is None and len(s.seen())==1
    (s.health_root/'mode').write_text('valid');activate(s,s.artifact('health-b'))
    assert s.health()==(200,{'status':'ready'})
    s.store.rollback(control=s.control,health=s.control.health,fingerprint=lambda:s.command('fingerprint'))
    assert s.store.target('current')==a and s.health()==(200,{'status':'ready'})
    assert len(s.seen())==3 and s.command('fingerprint')==before


@pytest.mark.skipif(os.geteuid()!=0,reason='Separate root driver for distinct principals')
def test_distinct_health_runtime_cannot_read_core_secrets(health_stack):
    s=health_stack;assert s.core_uid!=s.runtime_uid
    assert s.health()==(200,{'status':'ready'})
    script="import pathlib,sys;errors=0\nfor path in sys.argv[1:]:\n try:pathlib.Path(path).read_bytes();errors+=1\n except PermissionError:pass\nraise SystemExit(errors)"
    result=subprocess.run(['/usr/bin/python3','-c',script,str(s.base/'core/3mm.db'),str(s.base/'core/transport'/('a'*24+'.key'))],
        user=s.runtime_uid,group=s.runtime_uid,extra_groups=[],capture_output=True,timeout=3)
    assert result.returncode==0,result.stderr
