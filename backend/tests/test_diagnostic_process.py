"""Two reviewed neutral packages, actual hosts/HTTP/Runtime and one fixed Core.

Disposable compatibility package fixtures exercise the existing protected helper,
not a replacement for scoped native review. Signed SDK denial is separately real.
"""
import importlib.util
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
from backend.db.module import ModulePackage, ApplicationExtensionInstallation as Installation
from backend.services.module_packages import validate_module_package
from backend.tests.test_platform_runtime_process import (
    identity_app,managed_installed,source_subject,source_installed,checkpoint_app,
    core_stack,activate,activate_identity_grant,
)
from deployment import application_host_component as host
from three_mm_application_sdk import ApplicationPlatformError, SDK_VERSION
from three_mm_protocol.diagnostics import DiagnosticSession
from three_mm_protocol.diagnostic_snapshot import read_export, timeline
from three_mm_runtime.application_activation import activate_application_package, ApplicationActivationError
from tools.extension_dev import DevelopmentClient, inspect_package

pytestmark=pytest.mark.skipif(os.name!='posix' or os.geteuid()==0,reason='Owned unprivileged Linux functional dev lab; OS isolation has separate P4 root evidence')
ROOT=Path(__file__).resolve().parents[2]


def builder(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


@pytest.fixture
def stack(identity_app,monkeypatch):
    state=identity_app;activate_identity_grant(state);Base.metadata.create_all(state.engine);state.response_relay=True
    with core_stack(state,monkeypatch) as s:
        (s.base/'responses').mkdir(mode=0o750)
        s.control.response_path=s.base/'responses/runtime.sock';activate(s,s.artifact('p5-fixed'))
        yield s


class Hosts:
    def __init__(self,s):
        self.s=s;self.processes={};self.logs=[];self.root=s.base/'development-hosts'
        blob,metadata=host.build_component(ROOT)
        store=host.HostStore(self.root/'default',self.root/'updates/default',self.root/'releases')
        store.bootstrap(blob,host._digest(blob))
    def is_enabled(self,instance):return instance in self.processes and self.processes[instance].poll() is None
    def stop_for_data(self,instance):self.stop(instance)
    def stop(self,instance):
        process=self.processes.pop(instance,None)
        if process is not None:
            process.terminate()
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
    def restart(self,instance):
        self.stop(instance);host.bind_instance(instance,root=self.root)
        pin=self.root/'instances'/instance/'current';log=(self.s.base/(instance+'.log')).open('ab');self.logs.append(log)
        self.processes[instance]=subprocess.Popen([str(pin/'.venv/bin/python'),'-I',str(pin/'host.pyz'),'--instance',instance,'--root',str(self.s.base/'applications'),'--key-root',str(self.s.base/'core/transport')],
            cwd=pin,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},stdout=log,stderr=log)
    def close(self):
        for instance in list(self.processes):self.stop(instance)
        for log in self.logs:log.close()


def test_two_packages_install_trace_update_rollback_and_permission_denial_preserve_core(stack,monkeypatch):
    s=stack;before=s.command('fingerprint');runtime_pid=s.control.process.pid
    monkeypatch.setenv('THREE_MM_PLATFORM_RUNTIME_SOCKET',str(s.base/'runtime/runtime.sock'))
    references=builder('p5_application','modules/application-reference/build_reference_package.py')
    public=builder('p5_public','modules/public-web-reference/build_reference_package.py')
    a=references.build_package('dev_'+'d'*32,'http://127.0.0.1:9',version='1.0.1')
    b=references.build_package('dev_'+'d'*32,'http://127.0.0.1:9',version='1.0.2')
    broken=references.build_package('dev_'+'d'*32,'http://127.0.0.1:9',version='1.0.3',broken_health=True)
    peer=public.build_package();supervisor=Hosts(s)
    def install(blob):
        validated=validate_module_package(blob);archive=s.base/(validated.sha256+'.zip');archive.write_bytes(blob)
        assert inspect_package(archive)[1]['sha256']==validated.sha256
        active=activate_application_package(archive,validated.sha256,root=s.base/'applications',key_root=s.base/'core/transport',supervisor=supervisor)
        with Session(s.state.engine) as db:
            package=db.query(ModulePackage).filter_by(sha256=validated.sha256).one_or_none()
            if package is None:
                package=ModulePackage(module_id=validated.manifest.module_id,version=validated.manifest.version,sha256=validated.sha256,size_bytes=len(blob),file_path=str(archive),manifest=validated.manifest.model_dump(mode='json'),registrations=[]);db.add(package);db.flush()
            row=db.query(Installation).filter_by(module_id=validated.manifest.module_id).one_or_none()
            if row is None:row=Installation(module_id=validated.manifest.module_id,module_package_id=package.id,instance_id=active.instance_id,socket_path=str(active.socket_path));db.add(row)
            row.module_package_id=package.id;row.active_version=validated.manifest.version;row.enabled=True;row.status='active';row.authority_mode='compatibility';db.commit()
        return active,validated
    token=s.admin['Authorization'].split(' ',1)[1];client=DevelopmentClient(s.url(),token)
    def post(path,body,admin=True,headers=None):
        request=urllib.request.Request(s.url()+path,json.dumps(body).encode(),headers={**(headers if headers is not None else s.admin if admin else {}),'Content-Type':'application/json'},method='POST')
        try:
            with urllib.request.urlopen(request,timeout=8) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    try:
        selected,av=install(a);other,pv=install(peer);other_pid=supervisor.processes[other.instance_id].pid
        session=json.loads(client.request('POST','/api/v1/diagnostics/session',b'{"profile":"development","ttl_seconds":60}'))
        assert session['active']
        sdk=DiagnosticSession('sdk',SDK_VERSION);sdk.start(60);s.client.diagnostics=sdk
        assert s.client.get_installation_identity()['sdk_version']=='1.3'
        from backend.db.module import ApplicationKioskTerminal
        from backend.utils.jwt_utils import create_access_token
        terminal='t'*32
        with Session(s.state.engine) as db:
            row=db.query(Installation).filter_by(module_id=av.manifest.module_id).one()
            db.add(ApplicationKioskTerminal(terminal_id=terminal,application_installation_id=row.id,label='Owned P5 fixture',credential_hash='fixture',enabled=True));db.commit()
        kiosk={'Authorization':'Bearer '+create_access_token('kiosk:'+terminal,{'token_type':'application_kiosk','module_id':av.manifest.module_id,'terminal_id':terminal})}
        operation='/api/v1/application-extensions/'+av.manifest.module_id+'/kiosk/operations/register'
        status,value=post(operation,{'payload':{'label':'private-label-not-in-traces'},'idempotency_key':'p5-preserved-0001'},headers=kiosk)
        assert status==200,value
        public_operation='/api/v1/application-extensions/'+pv.manifest.module_id+'/public/operations/render_public'
        payload={'payload':{'method':'GET','path':'/','path_params':{},'query':{},'headers':{}}}
        assert post(public_operation,payload,False)[0]==200
        install(b);assert supervisor.processes[other.instance_id].pid==other_pid
        install(a);assert supervisor.processes[other.instance_id].pid==other_pid
        with pytest.raises(ApplicationActivationError):install(broken)
        assert supervisor.processes[other.instance_id].pid==other_pid
        # A helper failure restores/stops/restarts but does not assert readiness.
        # Observe a fresh read-only health query before explicit outcome review.
        from three_mm_runtime.application_transport import ApplicationServiceClient,ApplicationTransportError
        deadline=time.monotonic()+5
        while True:
            try:
                ready=ApplicationServiceClient(selected.socket_path,(s.base/'core/transport'/(selected.instance_id+'.key')).read_bytes(),1).invoke('health',{}, {'audience':'internal'})
                if ready=={'status':'ready'}:break
            except (OSError,ApplicationTransportError):pass
            assert time.monotonic()<deadline,'Restored host readiness is unknown'
            time.sleep(.05)
        # The existing idempotent result/data survives this explicit code rollback.
        assert post(operation,{'payload':{'label':'private-label-not-in-traces'},'idempotency_key':'p5-preserved-0001'},headers=kiosk)==(status,value)
        s.command('revoke')
        with pytest.raises(ApplicationPlatformError):s.client.get_installation_identity()
        raw=client.request('GET','/api/v1/diagnostics/session/records')
        with sdk.export() as chunks:imported=read_export(b''.join(chunks))
        combined=timeline(read_export(raw),imported)
        assert any(row['reason']=='authority_unavailable' for row in combined['records'])
        assert any(row['reason']=='operation_denied' for row in combined['records'])
        assert any(row['operation']=='application.invoke' for row in combined['records'])
        assert any(row['operation']=='installation.identity.get' and row['source']=='imported' for row in combined['records'])
        assert 'private-label-not-in-traces' not in json.dumps(combined)
        assert s.command('fingerprint')==before and s.control.process.pid==runtime_pid
        assert s.http('/settings/read')[0]==200
        client.request('DELETE','/api/v1/diagnostics/session')
    finally:supervisor.close()
