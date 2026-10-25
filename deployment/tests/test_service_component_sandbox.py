"""Explicit P4 OS boundary proof using only uniquely owned transient units.

No installed 3mm unit, database, grant, network setting or hardware is changed.
This proves packaging/socket/sandbox behavior, not M21 browser acceptance.
"""
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
import zipfile

import pytest
from deployment import service_component as component
from deployment.tests.test_service_component import artifacts,digest
from backend.tests.test_platform_runtime_process import (
    stack,identity_app,managed_installed,source_subject,source_installed,checkpoint_app,
)

ENABLED=os.getenv('THREE_MM_RUN_P4_SANDBOX_TESTS')=='1'
pytestmark=pytest.mark.skipif(not ENABLED,reason='Explicit owned transient systemd acceptance only')
ROOT=Path(__file__).resolve().parents[2]

PROVIDER="""import json,os,socket
from three_mm_runtime.component_identity import component_health
class Provider:
 provider_id='org.3mm.p4-neutral'
 contract_version='1.0'
 capability_ids=('org.3mm.p4.echo',)
 control_actions=()
 async def open(self,context):pass
 async def receive(self,sid,data):
  if data!=b'facts':return data
  denied=True
  try:s=socket.socket(socket.AF_INET);s.close();denied=False
  except OSError:pass
  paths=('/etc/3mm','/var/lib/3mm','/run/3mm','/mnt','/home','/root')
  return json.dumps({'identity':component_health(),'uid':os.geteuid(),'network_denied':denied,
   'paths_denied':all(not os.access(p,os.R_OK|os.X_OK) for p in paths),
   'secret_env':any('KEY' in k or 'TOKEN' in k or 'DATABASE' in k for k in os.environ)}).encode()
 async def read_output(self,sid):return None
 async def control(self,sid,message):pass
 async def close(self,sid,reason):pass
def create():return Provider()
"""
CLIENT="""import base64,hashlib,json,socket,struct,sys,uuid
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(8);s.connect(sys.argv[1])
def send(v):
 raw=json.dumps(v,separators=(',',':')).encode();s.sendall(struct.pack('!I',len(raw))+raw)
def readn(n):
 data=b''
 while len(data)<n:
  part=s.recv(n-len(data))
  if not part:raise EOFError('Session link closed')
  data+=part
 return data
def read():return json.loads(readn(struct.unpack('!I',readn(4))[0]))
wheel=base64.b64decode(sys.argv[2]);sid='ses_'+uuid.uuid4().hex
send({'version':1,'size':len(wheel),'sha256':hashlib.sha256(wheel).hexdigest(),
 'factory':'p4_fixture:create','provider_id':'org.3mm.p4-neutral',
 'context':{'session_id':sid,'device_id':'dev_'+'a'*32,'capability_id':'org.3mm.p4.echo','access_mode':'write','options':{}}})
s.sendall(wheel);hello=read();assert hello['ready'] is True
send({'id':1,'op':'input','data':base64.b64encode(b'facts').decode()});facts=json.loads(base64.b64decode(read()['data']))
send({'id':2,'op':'input','data':base64.b64encode(b'echo').decode()});assert base64.b64decode(read()['data'])==b'echo'
send({'id':3,'op':'close'});assert read()['closed'] is True
s.close();print(json.dumps(facts))
"""


def test_independent_session_artifact_update_runs_in_actual_sandbox_and_preserves_core(stack):
    import base64
    assert os.geteuid()==0 and Path('/run/systemd/system').is_dir()
    s=stack;before=s.command('fingerprint');a,b=artifacts('session-worker')
    directory=Path(tempfile.mkdtemp(prefix='3mm-p4-session-',dir='/opt'));directory.chmod(0o755)
    assert directory.resolve().parent==Path('/opt') and directory.name.startswith('3mm-p4-session-')
    name='3mm-session-worker-p4-'+uuid.uuid4().hex[:12]
    assert re.fullmatch(r'3mm-session-worker-p4-[a-f0-9]{12}',name)
    unitroot=Path('/run/systemd/system');service=unitroot/(name+'@.service');listener=unitroot/(name+'.socket')
    assert not service.exists() and not listener.exists()
    store=component.ServiceStore('session-worker',directory/'component',directory/'journal');store.bootstrap(a[0],digest(a[0]))
    endpoint=directory/'worker.sock'
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as wheel:
        wheel.writestr('p4_fixture.py',PROVIDER);wheel.writestr('p4_fixture-1.dist-info/WHEEL','Root-Is-Purelib: true\nTag: py3-none-any\n')
    encoded=base64.b64encode(stream.getvalue()).decode()
    def command(*args,check=True):
        return subprocess.run(['/usr/bin/systemctl',*args],check=check,capture_output=True,text=True,timeout=30)
    class Control:
        def active(self):return command('is-active','--quiet',name+'.socket',check=False).returncode==0
        def stop(self):
            command('stop',name+'.socket',check=False);command('stop',name+'@*.service',check=False)
        def start(self):command('start',name+'.socket')
    control=Control()
    def facts():
        import pwd
        user=pwd.getpwnam('3mm')
        result=subprocess.run(['/usr/bin/python3','-I','-c',CLIENT,str(endpoint),encoded],user=user.pw_uid,group=user.pw_gid,extra_groups=[],
            cwd=directory,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},capture_output=True,text=True,timeout=15)
        assert result.returncode==0,result.stderr
        value=json.loads(result.stdout)
        assert 61184<=value['uid']<=65519 and value['network_denied'] and value['paths_denied'] and not value['secret_env'],value
        return value
    def health(identifier):
        assert control.active()
        value=facts();assert value['identity']['component']=='session-worker' and value['identity']['build_id']==identifier
        current=s.command('fingerprint')
        return {'core_pid':current['pid'],'core_process_generation':current['generation']}
    try:
        unit=(ROOT/'deployment/systemd/3mm-session-worker@.service').read_text()
        # Only this owned template uses the owned artifact and has no dependency
        # capable of starting/stopping an installed Core unit.
        unit='\n'.join(line for line in unit.splitlines() if not line.startswith(('PartOf=','BindsTo=','After=')))+'\n'
        unit=unit.replace('/opt/3mm-session-worker/current',str(store.root/'current'))
        service.write_text(unit)
        listener.write_text('[Socket]\nListenStream='+str(endpoint)+'\nSocketUser=root\nSocketGroup=3mm\nSocketMode=0660\nAccept=yes\nMaxConnections=4\nRemoveOnStop=yes\n')
        command('daemon-reload');control.start()
        # Root is NOT the trusted Core socket peer. Refusal precedes provider IPC.
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as foreign:
            foreign.settimeout(8);foreign.connect(str(endpoint));assert foreign.recv(1)==b''
        health(a[1]['build_id'])
        store.activate(b[0],digest(b[0]),control=control,health=health,fingerprint=lambda:s.command('fingerprint'))
        assert store.target('current')==b[1]['build_id']
        store.rollback(control=control,health=health,fingerprint=lambda:s.command('fingerprint'))
        assert store.target('current')==a[1]['build_id'] and s.command('fingerprint')==before
        assert s.http('/settings/read')[0]==200
    finally:
        control.stop();command('reset-failed',name+'@*.service',check=False)
        for path in (service,listener):
            assert path.parent==unitroot and path.name.startswith(name)
            path.unlink(missing_ok=True)
        command('daemon-reload')
        assert directory.resolve().parent==Path('/opt') and not directory.is_symlink()
        shutil.rmtree(directory)
