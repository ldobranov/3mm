"""Opt-in local Linux Node payload smoke. Not an ARM wheel or physical board test."""
import configparser
import functools
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import time

import pytest

from deployment.build_node_release import build
from deployment.prepare_node_wheels import digest
from deployment import service_resources


@pytest.mark.skipif(os.environ.get('TEST_MINIMAL_NODE_RESOURCES') != '1',
                    reason='Explicit disposable Linux user-manager acceptance only')
def test_packaged_node_runs_without_core_and_reports_its_own_resources(tmp_path, monkeypatch):
    # The user manager is separate from the installed system manager. Start
    # only if this exact name is unused; never stop a pre-existing Agent.
    assert os.getuid() != 0
    manager = functools.partial(subprocess.run, capture_output=True, text=True, timeout=12, check=True)
    unit = '3mm-agent.service'
    def prop(name):
        return manager(['systemctl','--user','show',unit,'-p',name,'--value']).stdout.strip()
    assert prop('LoadState') == 'not-found'
    root = Path(__file__).resolve().parents[2]
    wheels = tmp_path / 'fixture-wheels'
    wheels.mkdir()
    # Builder requires a wheel inventory. No wheel is installed or executed;
    # the test runs the extracted portable source with the local locked env.
    wheel = wheels / 'fixture-1-py3-none-any.whl'
    wheel.write_bytes(b'fixture')
    (wheels/'provenance.json').write_text(json.dumps({'architecture':'armv6l','python':'3.13',
        'wheels':[{'filename':wheel.name,'sha256':digest(wheel.read_bytes())}]}))
    result = build(root, wheels, tmp_path/'bundle', version=(root/'VERSION').read_text().strip(),
                   commit='a'*40, repository='example/test', epoch=1700000000)
    extracted = tmp_path/'minimal'
    with tarfile.open(tmp_path/'bundle'/result['artifacts'][0]['filename']) as archive:
        archive.extractall(extracted, filter='data')
    assert (extracted/'.3mm-install-profile').read_text().strip() == 'node'
    assert not any((extracted/n).exists() for n in ('backend','frontend','packages/application_sdk'))
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read(extracted/'deployment/systemd'/unit)
    # Evaluate the shipped resource policy; do not run the installed identity,
    # permanent data paths, network listener, GPIO driver or restart policy.
    properties = ['--property='+n+'='+config['Service'][n] for n in
                  ('MemoryMax','TasksMax','CPUQuota','LimitNOFILE','TimeoutStopSec')]
    program = """
import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from agent.config import AgentSettings
from agent.hardware import HardwareProfile
from agent.main import create_app
import uvicorn
data=Path(sys.argv[2])
app=create_app(AgentSettings(data_dir=data/'own',provisioning_data_dir=data/'provision',
                            hardware_profile=HardwareProfile.MOCK_LINUX))
uvicorn.run(app,uds=str(data/'http.sock'),log_level='warning')
"""
    with tempfile.TemporaryDirectory(prefix='node-cap-', dir=os.environ['XDG_RUNTIME_DIR']) as directory:
        data = Path(directory)
        manager(['systemd-run','--user','--quiet','--collect','--unit='+unit,
                 '--property=Type=exec','--property=RuntimeMaxSec=75s','--property=Restart=no',
                 '--property=NoNewPrivileges=yes','--property=RestrictAddressFamilies=AF_UNIX',
                 *properties,sys.executable,'-I','-B','-c',program,str(extracted),str(data)])
        invocation = prop('InvocationID')
        try:
            def ready():
                conn = http.client.HTTPConnection('localhost',timeout=1)
                with socket.socket(socket.AF_UNIX) as local:
                    local.settimeout(1)
                    local.connect(str(data/'http.sock'))
                    conn.sock = local
                    conn.request('GET','/ready')
                    reply = conn.getresponse()
                    return reply.status == 200 and json.loads(reply.read(4096))['status'] == 'ready'
            deadline = time.monotonic()+45
            while True:
                try:
                    if ready(): break
                except (OSError,http.client.HTTPException): pass
                assert time.monotonic() < deadline and prop('ActiveState') in ('active','activating')
                time.sleep(.2)
            # Use the production probe with only its systemctl manager selection
            # redirected to the disposable user manager. All kernel reads are real.
            real_run = subprocess.run
            class UserManager:
                SubprocessError = subprocess.SubprocessError
                @staticmethod
                def run(args, **kw): return real_run([args[0],'--user',*args[1:]], **kw)
            monkeypatch.setattr(service_resources,'subprocess',UserManager)
            sample = service_resources.collect_node_agent()
            assert sample['state'] == 'observed' and sample['supervision']['state'] == 'active'
            assert sample['main_process_fds'] == {'state':'os_enforced','soft':256,'hard':256}
            assert sample['limits']['tasks']['max_tasks'] == 64 and sample['usage']['tasks'] > 0
            assert sample['limits']['memory']['max_bytes'] == 256*1024**2 and sample['usage']['memory_bytes'] > 0
            cpu = sample['limits']['cpu']
            assert cpu['state'] == 'unavailable' or cpu['quota_usec'] == cpu['period_usec']
            assert ready()
            print(json.dumps({'role':'minimal-node','hardware':'mock-linux','ready':True,'limits':sample['limits'],
                              'fds':sample['main_process_fds'],'usage':sample['usage']}))
        finally:
            if prop('LoadState') != 'not-found':
                assert invocation and invocation == prop('InvocationID')
                manager(['systemctl','--user','stop',unit])
        assert prop('LoadState') == 'not-found'
