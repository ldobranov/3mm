"""Real Core + isolated SDK Runtime + independently pinned network worker + HTTP."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.module import ApplicationConnectorAttempt as Attempt, ApplicationConnectorBinding as Binding, ApplicationExtensionInstallation as Installation
from backend.services.application_connectors import prepare_application_connector_binding, bind_application_connector
from backend.services.authority_metadata import authority_transaction
from backend.tests.test_application_authority_management import installed as connector_installed, source_subject, source_installed, activate_grant, identity
from backend.tests.test_application_event_authority import replace_package
from backend.tests.test_platform_runtime_process import core_stack, activate
from backend.tests.test_application_public_web_transport import wait_for
from deployment.platform_runtime_component import RuntimeStore
from three_mm_application_sdk import ApplicationPlatformError
from three_mm_platform_runtime.connector_worker import probe_worker

pytestmark=pytest.mark.skipif(os.name!='posix',reason='Actual Linux processes/SCM_RIGHTS')


class WorkerProcesses:
    def __init__(self,s):
        self.s=s;self.process=None
        self.store=RuntimeStore(s.base/'network-components',s.base/'network-updates')
        self.log=(s.base/'network.log').open('ab')
    def active(self):return self.process is not None and self.process.poll() is None
    def stop(self):
        if self.active():
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
    def start(self):
        s=self.s;path=self.store.root/'current'
        command=[str(path/'.venv/bin/python'),'-I',str(path/'runtime.pyz'),'--connector-worker',
            '--socket',str(s.base/'connectors/worker.sock'),'--core-uid',str(s.core_uid)]
        options={}
        if os.geteuid()==0:
            options={'user':s.state.connector_worker_uid,'group':s.state.connector_worker_uid,'extra_groups':[]}
            command+=['--socket-group',__import__('grp').getgrgid(s.core_uid).gr_name]
        self.process=subprocess.Popen(command,cwd=path,stdout=self.log,stderr=self.log,
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},**options)
    def health(self,identifier):
        deadline=time.monotonic()+4
        while True:
            try:
                result=probe_worker(self.s.base/'connectors/worker.sock',expected_uid=self.s.state.connector_worker_uid,expected_build=identifier)
                fingerprint=self.s.command('fingerprint')
                return {**result,'core_pid':fingerprint['pid'],'core_process_generation':fingerprint['generation']}
            except (OSError,ValueError):
                if time.monotonic()>deadline:raise
                time.sleep(.02)
    def activate(self,artifact):
        blob,_=artifact
        return self.store.activate(blob,hashlib.sha256(blob).hexdigest(),control=self,
            health=self.health,fingerprint=lambda:self.s.command('fingerprint'))


@pytest.fixture
def network_stack(connector_installed,monkeypatch,request):
    state=connector_installed;seen=[];release=threading.Event();mode=['valid']
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append({'path':self.path,'headers':dict(self.headers),'body':self.rfile.read(int(self.headers.get('Content-Length',0))).decode()})
            if mode[0]=='hang':release.wait(12)
            try:
                data=b'x'*2048 if mode[0]=='limit' else b'0123456789' if mode[0]=='trickle' else b'{}'
                status=302 if mode[0]=='redirect' else 201
                self.send_response(status);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data)));self.send_header('Set-Cookie','private-cookie')
                if status==302:self.send_header('Location','/api/second-effect')
                self.end_headers()
                if mode[0]=='trickle':
                    for byte in data:
                        self.wfile.write(bytes([byte]));self.wfile.flush();time.sleep(.2)
                else:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass
        def log_message(self,*_args):pass
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    origin=f'http://127.0.0.1:{http.server_port}'
    definition=state.validated.application_extension.model_dump(mode='json')
    definition['connectors'][0]['timeout_seconds']=10 if any(word in request.node.name for word in ('core_restart','revocation','saturated','worker_kill','runtime_kill')) else 1
    definition['connectors'][0]['max_response_bytes']=1024
    replace_package(state,definition,state.validated.manifest.model_dump(mode='json'))
    with Session(state.engine) as db:
        app=db.get(Installation,1);app.configuration={**app.configuration,'BUSINESS_API_URL':origin};db.commit()
        binding=db.get(Binding,1)
        # Current fixture resource update before the actual sealed adoption.
        binding.destination_origin=origin;db.commit()
    activate_grant(state)
    state.connector_worker_uid=65533 if os.geteuid()==0 else os.geteuid()
    try:
        with core_stack(state,monkeypatch) as s:
            (s.base/'connectors').mkdir(mode=0o750)
            if os.geteuid()==0:
                os.chown(s.base/'connectors',state.connector_worker_uid,s.core_uid)
                (s.base/'connectors').chmod(0o2750)
            worker=WorkerProcesses(s);worker.activate(s.artifact('network-a'))
            activate(s,s.artifact('sdk-a'))
            s.network=worker;s.seen=seen;s.release=release;s.mode=mode
            def call(request_id=None):
                return s.client._call('connector.request',{'connector_id':'business_api',
                    'connector_request_id':request_id or 'connector_'+identity(),'method':'POST',
                    'path':'/api/records','headers':{'Content-Type':'application/json'},
                    'body_base64':base64.b64encode(b'{}').decode(),'idempotency_key':'one-logical-effect'})
            s.call_connector=call
            def attempts():
                with Session(state.engine) as db:
                    return [dict(id=a.id,outcome=a.outcome,metadata=a.dispatch_metadata,error=a.error_category) for a in db.scalars(select(Attempt).order_by(Attempt.id))]
            s.attempts=attempts
            try:yield s
            finally:release.set();worker.stop();worker.log.close()
    finally:release.set();http.shutdown();http.server_close();thread.join(timeout=2)


def test_real_http_result_and_duplicate_preserve_core_and_hide_credentials(network_stack):
    s=network_stack;before=s.command('fingerprint');rid='connector_'+identity()
    result=s.call_connector(rid)
    assert result['outcome']=='succeeded' and result['http_status']==201
    assert result['headers']=={'Content-Type':'application/json'}
    assert result['body_base64']=='e30=' and not result['duplicate']
    assert s.call_connector(rid)['duplicate'] and len(s.seen)==1
    assert s.seen[0]['headers']['Idempotency-Key']=='one-logical-effect'
    assert s.seen[0]['headers']['Authorization'].startswith('Basic ')
    assert 'PRIVATE' not in repr(s.attempts()) and 'Authorization' not in repr(s.attempts())
    assert s.command('fingerprint')==before and s.http()[0]==200


@pytest.mark.parametrize('mode,expected',[('hang','ambiguous'),('trickle','ambiguous'),('limit','failed'),('redirect','retryable')])
def test_network_deadline_limit_and_redirect_never_replay(network_stack,mode,expected):
    s=network_stack;s.mode[0]=mode;rid='connector_'+identity();start=time.monotonic()
    result=s.call_connector(rid)
    assert time.monotonic()-start<4
    assert result['outcome']==expected
    assert s.call_connector(rid)['duplicate'] and len(s.seen)==1
    assert s.http()[0]==200


def test_revocation_during_http_records_original_effect_without_new_admission(network_stack):
    s=network_stack;s.mode[0]='hang';rid='connector_'+identity()
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(s.call_connector,rid);wait_for(lambda:len(s.seen)==1)
        s.command('revoke');s.release.set()
        assert pending.result(timeout=5)['outcome']=='succeeded'
    assert s.call_connector(rid)['duplicate']
    with pytest.raises(ApplicationPlatformError):s.call_connector()
    assert len(s.seen)==1 and s.http()[0]==200


def test_core_restart_can_finish_original_durable_result(network_stack):
    s=network_stack;s.mode[0]='hang';rid='connector_'+identity();old=s.core.pid
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(s.call_connector,rid);wait_for(lambda:len(s.seen)==1)
        s.restart_core();s.release.set()
        assert pending.result(timeout=10)['outcome']=='succeeded'
    assert s.core.pid!=old and s.call_connector(rid)['duplicate'] and len(s.seen)==1


def test_worker_kill_and_independent_update_rollback_preserve_core_runtime(network_stack):
    s=network_stack;s.mode[0]='hang';rid='connector_'+identity()
    before=s.command('fingerprint');runtime_pid=s.control.process.pid
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(s.call_connector,rid);wait_for(lambda:len(s.seen)==1)
        s.network.stop()
        assert pending.result(timeout=5)['outcome']=='ambiguous'
    s.release.set();s.mode[0]='valid'
    a=s.network.store.target('current');b=s.artifact('network-b')
    s.network.activate(b)
    assert s.network.store.target('current')==b[1]['build_id']
    assert s.call_connector()['outcome']=='succeeded'
    s.network.store.rollback(control=s.network,health=s.network.health,fingerprint=lambda:s.command('fingerprint'))
    assert s.network.store.target('current')==a
    assert s.call_connector(rid)['duplicate'] and len(s.seen)==2
    assert s.command('fingerprint')==before and s.control.process.pid==runtime_pid


def test_runtime_kill_lost_result_expires_without_replay(network_stack):
    s=network_stack;s.mode[0]='hang';rid='connector_'+identity();before=s.command('fingerprint')
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(s.call_connector,rid);wait_for(lambda:len(s.seen)==1)
        s.control.stop()
        with pytest.raises(ApplicationPlatformError):pending.result(timeout=5)
    s.release.set();time.sleep(.1)
    with Session(s.state.engine) as db:
        row=db.scalar(select(Attempt));row.dispatch_metadata={**row.dispatch_metadata,'deadline_ms':0};db.commit()
    activate(s,s.artifact('sdk-after-loss'))
    result=s.call_connector(rid)
    assert result['outcome']=='ambiguous' and result['duplicate']
    assert len(s.seen)==1 and s.command('fingerprint')==before


def test_saturated_network_worker_leaves_short_core_admission_and_admin_available(network_stack):
    s=network_stack;s.mode[0]='hang'
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending=[]
        # Current key admission is intentionally nonblocking. Admit each request
        # before filling the next HTTP wait slot; all four responses stay blocked.
        for count in range(1,5):
            pending.append(pool.submit(s.call_connector))
            wait_for(lambda:len(s.seen)==count)
        start=time.monotonic()
        assert s.client.discover_platform()['operations']
        assert s.http('/settings/read')[0]==200
        assert s.http('/api/v1/diagnostics/components',headers=s.admin)[0]==200
        assert s.http()[0]==200
        assert time.monotonic()-start<2
        s.release.set()
        assert all(p.result(timeout=5)['outcome']=='succeeded' for p in pending)


def test_core_crash_after_durable_send_before_handoff_cannot_resend(network_stack):
    s=network_stack;s.mode[0]='hang';rid='connector_'+identity()
    (s.base/'crash-before-connector-handoff').touch()
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(s.call_connector,rid)
        with pytest.raises(ApplicationPlatformError):pending.result(timeout=5)
    s.core.join(timeout=3);assert s.core.exitcode==18
    wait_for(lambda:len(s.seen)==1)
    (s.base/'crash-before-connector-handoff').unlink();s.release.set()
    with Session(s.state.engine) as db:
        row=db.scalar(select(Attempt));assert row.outcome=='in_progress'
        row.dispatch_metadata={**row.dispatch_metadata,'deadline_ms':0};db.commit()
    s.restart_core()
    assert s.call_connector(rid)['outcome']=='ambiguous' and len(s.seen)==1
    assert s.http()[0]==200


def test_bad_worker_candidate_rolls_back_only_network_process(network_stack):
    from deployment.platform_runtime_component import build_component
    s=network_stack;before=s.command('fingerprint');runtime_pid=s.control.process.pid
    a=s.network.store.target('current')
    s.artifact('bad-worker')
    path=s.base/'source-bad-worker/three_mm_platform_runtime/connector_worker.py'
    path.write_text(path.read_text().replace('    worker = ConnectorWorker(', '    raise RuntimeError("injected bad worker")\n    worker = ConnectorWorker('))
    bad=build_component(s.base/'source-bad-worker')
    with pytest.raises((OSError,ValueError)):s.network.activate(bad)
    assert s.network.store.target('current')==a and s.network.store.pending() is None
    assert s.call_connector()['outcome']=='succeeded'
    assert s.command('fingerprint')==before and s.control.process.pid==runtime_pid


def test_dns_hang_is_killed_outside_core_at_absolute_deadline(network_stack):
    from deployment.platform_runtime_component import build_component
    s=network_stack;s.artifact('dns-stall')
    path=s.base/'source-dns-stall/three_mm_platform_runtime/connector_worker.py'
    text=path.read_text().replace('    parsed = urlsplit(plan["url"])', '    socket.getaddrinfo=lambda *a,**k: time.sleep(60)\n    parsed = urlsplit(plan["url"])')
    path.write_text(text);s.network.activate(build_component(s.base/'source-dns-stall'))
    start=time.monotonic();result=s.call_connector()
    assert result['outcome']=='ambiguous' and result['error_category']=='response_timeout'
    assert time.monotonic()-start<4 and s.seen==[] and s.http()[0]==200


@pytest.mark.skipif(os.geteuid()!=0,reason='Distinct UIDs need root test driver')
def test_distinct_network_worker_and_runtime_cannot_read_core_secrets(network_stack):
    s=network_stack
    assert len({s.core_uid,s.runtime_uid,s.state.connector_worker_uid})==3
    assert s.call_connector()['outcome']=='succeeded'
    for uid in (s.runtime_uid,s.state.connector_worker_uid):
        script="import pathlib,sys; failures=0\nfor p in sys.argv[1:]:\n try:pathlib.Path(p).read_bytes();failures+=1\n except PermissionError:pass\nraise SystemExit(failures)"
        result=subprocess.run(['/usr/bin/python3','-c',script,str(s.base/'core/3mm.db'),str(s.base/'core/transport'/('a'*24+'.key'))],
            user=uid,group=uid,extra_groups=[],capture_output=True,timeout=3)
        assert result.returncode==0,result.stderr
    # An application/SDK Runtime UID cannot feed an arbitrary network plan.
    script="import socket,sys;s=socket.socket(socket.AF_UNIX);s.connect(sys.argv[1])"
    result=subprocess.run(['/usr/bin/python3','-c',script,str(s.base/'connectors/worker.sock')],
        user=s.runtime_uid,group=s.runtime_uid,extra_groups=[],capture_output=True,timeout=3)
    assert result.returncode!=0 and b'PermissionError' in result.stderr
    assert s.http()[0]==200
