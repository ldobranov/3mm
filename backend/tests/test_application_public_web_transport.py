"""Real public response handoff: Core HTTP + independent Runtime + signed service."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import io
import zipfile
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.services.module_packages import validate_module_package
from backend.tests.test_module_packages import application_package
from backend.tests.test_application_public_web import definition
from backend.tests.test_platform_runtime_process import (
    stack, identity_app, managed_installed, source_subject, source_installed,
    checkpoint_app, activate_identity_grant, identity, activate,
)
from three_mm_platform_wire import send_authority_frame, receive_authority_frame, peer_identity
from three_mm_public_web.server import PublicWebRuntimeClient, PublicWebRuntimeError, create_server

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Real Linux processes/SCM_RIGHTS")
SOURCE = Path(__file__).resolve().parents[2]
INSTANCE = "b" * 24
SECRET = b"p" * 32

# Neutral service using the production transport/signature format. The package
# registry is real; this peer exercises response boundary faults deliberately.
SERVICE = r"""
import json,os,socket,sys,threading,time
from pathlib import Path
from three_mm_runtime.application_transport import read_message,verify_message,sign_message,send_message
root=Path(sys.argv[1]);secret=bytes.fromhex(sys.argv[2]);lock=threading.Lock()
def handle(connection):
    with connection:
        request=verify_message(read_message(connection),secret)
        with lock:
            with (root/'seen').open('a') as f:f.write(json.dumps(request)+'\n')
        mode=(root/'mode').read_text()
        if mode=='hang':time.sleep(120);return
        if mode=='pause':
            while (root/'mode').read_text()=='pause':time.sleep(.01)
            mode=(root/'mode').read_text()
        result={'status':200,'content_type':'text/html; charset=utf-8','headers':{},'body':'<h1>Public</h1>'}
        if mode=='content':result['content_type']='image/png'
        if mode=='headers':result['headers']={'Set-Cookie':'admin=bad'}
        if mode=='size':result['body']='x'*4097
        response=sign_message({'version':1,'request_id':request['request_id'],'timestamp':int(time.time()),'ok':True,'result':result},secret)
        if mode=='signature':response['signature']='0'*64
        if mode=='request_id':response['request_id']='foreign'
        if mode=='trickle':
            for byte in b'{"version":1':
                try:connection.send(bytes([byte]));time.sleep(.2)
                except OSError:return
            return
        send_message(connection,response)
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.bind(str(root/'service.sock'));os.chmod(root/'service.sock',0o666);s.listen(32)
while True:
    c,_=s.accept();threading.Thread(target=handle,args=(c,),daemon=True).start()
"""


def wait_for(predicate, seconds=5):
    until=time.monotonic()+seconds
    while not predicate():
        if time.monotonic()>until:raise AssertionError("Test peer did not reach expected state")
        time.sleep(.01)


@pytest.fixture
def public(stack,request):
    s=stack
    response_seconds=getattr(request,'param',2)
    root=s.base/'host';root.mkdir(mode=0o755)
    (root/'mode').write_text('valid')
    if os.geteuid()==0:
        import pwd
        host=pwd.getpwnam('3mm-app')
        os.chown(root,host.pw_uid,host.pw_gid)
        host_options={'user':host.pw_uid,'group':host.pw_gid,'extra_groups':[]}
    else: host_options={}
    peer=subprocess.Popen(['/usr/bin/python3','-c',SERVICE,str(root),SECRET.hex()],cwd=SOURCE,
        env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(SOURCE),'LANG':'C.UTF-8'},
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**host_options)
    try:
        wait_for(lambda:(root/'service.sock').exists())
        current=definition('org.3mm.workflow-reference','/public/{slug}',max_response_bytes=4096).model_dump(mode='json')
        current['operations'][-1]['timeout_seconds']=response_seconds
        blob=application_package(definition=current)
        output=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(blob)) as source, zipfile.ZipFile(output,'w') as target:
            for name in source.namelist():
                content=source.read(name)
                if name in {'manifest.json','application-extension.json','compiled-ui.json'}:
                    value=json.loads(content);value['module_id']='org.example.public-neutral'
                    content=json.dumps(value).encode()
                target.writestr(name,content)
        blob=output.getvalue()
        validated=validate_module_package(blob)
        archive=s.base/'core/uploads/public.zip';archive.write_bytes(blob);archive.chmod(0o644)
        key=s.base/'core/transport'/(INSTANCE+'.key');key.write_bytes(SECRET);key.chmod(0o600)
        if os.geteuid()==0:os.chown(archive,s.core_uid,s.core_uid);os.chown(key,s.core_uid,s.core_uid)
        engine=create_engine('sqlite:///'+str(s.base/'core/3mm.db'))
        with Session(engine) as db:
            package=ModulePackage(module_id=validated.manifest.module_id,version=validated.manifest.version,
                manifest=validated.manifest.model_dump(mode='json'),sha256=validated.sha256,
                size_bytes=len(blob),file_path=str(archive),registrations=[])
            db.add(package);db.flush()
            existing=Installation(module_id=package.module_id,module_package_id=package.id,
                instance_id=INSTANCE,active_version=package.version,status='active',enabled=True,
                authority_mode='compatibility',socket_path=str(root/'service.sock'),configuration={})
            db.add(existing)
            db.commit();installation_id=existing.id
        s.control.public_web_path=s.base/'runtime/public.sock'
        activate(s,s.artifact('public-a'))
        s.public_root=root;s.public_peer=peer;s.public_engine=engine;s.public_id=installation_id
        s.public_client=PublicWebRuntimeClient(s.control.public_web_path,timeout_seconds=response_seconds+3)
        def call(**changes):
            return s.public_client.request(method='GET',path='/public/hello',query={'q':['one']},
                headers={'authorization':'Bearer must-not-forward','accept-language':'bg'},**changes)
        s.public_call=call
        s.seen=lambda: [json.loads(line) for line in (root/'seen').read_text().splitlines()] if (root/'seen').exists() else []
        yield s
    finally:
        peer.terminate()
        try:peer.wait(timeout=2)
        except subprocess.TimeoutExpired:peer.kill();peer.wait(timeout=2)
        if 'engine' in locals():engine.dispose()


def test_public_signed_response_and_http_projection_preserve_real_core(public):
    s=public;before=s.command('fingerprint')
    result=s.public_call();assert result.body=='<h1>Public</h1>'
    request=s.seen()[0]
    assert request['context']['audience']=='public'
    assert request['payload']['path_params']=={'slug':'hello'}
    assert request['payload']['headers']=={'accept-language':'bg'}
    assert 'must-not-forward' not in json.dumps(request)
    server=create_server(s.control.public_web_path,port=0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        url='http://127.0.0.1:'+str(server.server_port)+'/public/hello'
        with urllib.request.urlopen(url,timeout=5) as response:
            assert response.status==200 and response.read()==b'<h1>Public</h1>'
        with urllib.request.urlopen(urllib.request.Request(url,method='HEAD'),timeout=5) as response:
            assert response.status==200 and response.read()==b''
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
    assert s.http('/ready')[0]==200 and s.command('fingerprint')==before


@pytest.mark.parametrize('mode',['signature','request_id','content','headers','size','trickle'])
def test_untrusted_application_result_fails_closed_without_replay(public,mode):
    s=public;(s.public_root/'mode').write_text(mode)
    start=time.monotonic()
    with pytest.raises(PublicWebRuntimeError):s.public_call()
    assert time.monotonic()-start<4
    assert len(s.seen())==1
    assert s.http()[0]==200
    (s.public_root/'mode').write_text('valid')
    assert s.public_call().status==200


@pytest.mark.parametrize('change',['disabled','mode','epoch','package','key'])
def test_authority_change_while_runtime_waits_cannot_release_a_stale_result(public,change):
    s=public;(s.public_root/'mode').write_text('pause')
    with ThreadPoolExecutor() as pool:
        future=pool.submit(s.public_call)
        wait_for(lambda:len(s.seen())==1)
        # Extension is blocked but every private Core handler is released.
        assert s.http('/settings/read')[0]==200
        with Session(s.public_engine) as db:
            row=db.get(Installation,s.public_id)
            if change=='disabled':row.enabled=False;row.status='disabled'
            elif change=='mode':row.authority_mode='enforced'
            elif change=='epoch':row.authority_epoch=identity()
            elif change=='package':db.get(ModulePackage,row.module_package_id).sha256='0'*64
            elif change=='key':(s.base/'core/transport'/(INSTANCE+'.key')).write_bytes(b'x'*32)
            db.commit()
        (s.public_root/'mode').write_text('valid')
        with pytest.raises(PublicWebRuntimeError):future.result(timeout=5)
    assert len(s.seen())==1
    if change=='epoch':
        # The stale response is denied; a newly admitted current request is valid.
        assert s.public_call().status==200 and len(s.seen())==2
    else:
        with pytest.raises(PublicWebRuntimeError):s.public_call()
        if change!='key':assert len(s.seen())==1



@pytest.mark.parametrize('public',[30],indirect=True)
def test_saturated_public_waits_and_runtime_kill_leave_core_handlers_available(public):
    s=public;before=s.command('fingerprint');(s.public_root/'mode').write_text('hang')
    with ThreadPoolExecutor(max_workers=9) as pool:
        # Saturation needs overlapping live requests, not eight historical sends.
        # Keep the ordinary 2 s response-fault profile for the other tests; this
        # case uses the supported 30 s window and kills Runtime to end the waits.
        futures=[]
        try:
            # Admit serially so the separate short Core admission pool is not
            # the fault under test; all response waits must still overlap.
            for index in range(8):
                futures.append(pool.submit(s.public_call))
                wait_for(lambda:len(s.seen())==index+1)
            assert all(not future.done() for future in futures)
            start=time.monotonic()
            for _ in range(4):assert s.http('/settings/read')[0]==200
            assert time.monotonic()-start<2
            assert s.client.get_installation_identity()['sdk_version']=='1.3'
            from three_mm_platform_runtime.server import probe_runtime
            assert probe_runtime(s.base/'runtime/runtime.sock',expected_uid=s.runtime_uid,require_public_web=True)['ready']
            assert all(not future.done() for future in futures)
            # Overflow must be refused promptly, not dispatched and timed out.
            overflow=pool.submit(s.public_call)
            with pytest.raises(PublicWebRuntimeError):overflow.result(timeout=2)
            assert len(s.seen())==8
            assert all(not future.done() for future in futures)
        finally:
            # Assertion failure must also release the owned client threads.
            if s.control.process.poll() is None:s.control.process.kill()
            s.control.process.wait(timeout=3)
        for future in futures:
            with pytest.raises(PublicWebRuntimeError):future.result(timeout=5)
    assert s.command('fingerprint')==before and s.http()[0]==200
    (s.public_root/'mode').write_text('valid')
    s.control.start();s.control.health(s.store.target("current"))
    assert s.public_call().status==200 and len(s.seen())==9


def test_public_runtime_update_bad_candidate_and_rollback_keep_core_and_peer(public):
    s=public;before=s.command('fingerprint');peer=s.public_peer.pid
    first=s.store.target("current");activate(s,s.artifact('public-b'))
    assert s.public_call().status==200
    s.store.rollback(control=s.control,health=s.control.health,fingerprint=lambda:s.command('fingerprint'))
    assert s.store.target("current")==first and s.public_call().status==200
    with pytest.raises(Exception):activate(s,s.artifact('public-bad',broken=True))
    assert s.public_call().status==200
    assert s.public_peer.pid==peer and s.public_peer.poll() is None
    assert s.command('fingerprint')==before


@pytest.mark.parametrize('change',[{'method':'POST'},{'path':'/missing'},{'version':True},
    {'extra':'forbidden'},{'query':{'q':'not-a-list'}},{'headers':{'a':[]}}])
def test_invalid_public_requests_do_not_dispatch(public,change):
    s=public;value={'version':1,'request_id':'a'*32,'method':'GET','path':'/public/hello','query':{},'headers':{}}
    value.update(change)
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(3);connection.connect(str(s.control.public_web_path))
        connection.sendall(json.dumps(value).encode()+b'\n')
        payload=connection.recv(65536)
    assert not payload or json.loads(payload).get('ok') is False
    assert s.seen()==[]


@pytest.mark.parametrize('damage',['signature','route','instance','expired','core','runtime','extra','response'])
def test_result_receipt_is_bound_and_cannot_authorize_another_dispatch(public,damage):
    from backend.config import ApplicationRuntimeSettings
    from backend.services.application_public_web_transport import begin_public_http,finish_public_http
    from three_mm_platform_wire import read_frame
    from three_mm_runtime.application_transport import sign_message
    s=public;settings=ApplicationRuntimeSettings(key_root=s.base/'core/transport')
    request={'version':1,'request_id':identity(),'method':'GET','path':'/public/hello','query':{},'headers':{}}
    with Session(s.public_engine) as db:
        begin,origin=begin_public_http(db,settings,request,core_generation='test-core',runtime_generation='test-runtime')
    with origin:response=read_frame(origin,time.monotonic()+2,max_bytes=1024*1024)
    receipt=begin['receipt']
    if damage=='signature':receipt['signature']='0'*64
    elif damage=='route':receipt['route_id']='another'
    elif damage=='instance':receipt['instance_id']='f'*24
    elif damage=='expired':
        receipt=sign_message({**receipt,'timestamp':int(time.time())-60},SECRET)
    elif damage=='core':receipt['core_generation']='old-core'
    elif damage=='runtime':receipt['runtime_generation']='old-runtime'
    elif damage=='extra':receipt['operation_id']='another'
    elif damage=='response':response['result']['body']='tampered'
    with Session(s.public_engine) as db,pytest.raises(Exception):
        finish_public_http(db,settings,receipt,response,core_generation='test-core',runtime_generation='test-runtime')
    assert len(s.seen())==1
    assert s.public_call().status==200 and len(s.seen())==2


@pytest.mark.skipif(os.geteuid()!=0,reason='Root driver for existing distinct OS principals')
def test_distinct_principals_pass_fd_without_core_key_or_database_access(public):
    import pwd
    s=public
    assert s.runtime_uid!=s.core_uid and s.public_peer.pid!=s.control.process.pid
    assert s.public_call().status==200
    # Neither the relay nor the service can read the Core authority material.
    script="from pathlib import Path;import sys;\nfor p in sys.argv[1:]:\n try:Path(p).read_bytes()\n except PermissionError:continue\n raise SystemExit('unexpected readable Core file')"
    app=pwd.getpwnam('3mm-app')
    for uid,gid in [(s.runtime_uid,s.runtime_uid),(app.pw_uid,app.pw_gid)]:
        result=subprocess.run(['/usr/bin/python3','-c',script,str(s.base/'core/3mm.db'),
            str(s.base/'core/transport'/(INSTANCE+'.key'))],user=uid,group=gid,extra_groups=[],
            capture_output=True,text=True,timeout=5)
        assert result.returncode==0,result.stderr
    # An untrusted local UID cannot enter the private public authority gate.
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(2);connection.connect(str(s.base/'authority/gate.sock'))
        try:
            send_authority_frame(connection,{'public_web_contract':1,'begin':{}})
            assert connection.recv(1)==b''
        except (ConnectionResetError,BrokenPipeError):pass
    assert s.http('/settings/read')[0]==200


def test_public_feature_probe_rejects_an_abi2_core_without_public_support(tmp_path):
    from three_mm_platform_runtime.server import probe_core
    path=tmp_path/'old-core.sock';observed=[]
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
        listener.bind(str(path));listener.listen(1)
        def old_core():
            with listener.accept()[0] as connection:
                request,origin=receive_authority_frame(connection,time.monotonic()+2)
                assert origin is None;observed.append(request)
                connection.sendall(json.dumps({k:request[k] for k in ('authority_contract','authority_probe')}).encode()+b'\n')
        thread=threading.Thread(target=old_core);thread.start()
        try:
            with pytest.raises(ValueError,match='contract'):
                probe_core(path,os.geteuid(),public_web=True)
        finally:thread.join(timeout=3)
        assert not thread.is_alive() and observed[0]['public_web_contract']==1
