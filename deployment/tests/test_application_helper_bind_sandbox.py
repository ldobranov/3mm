"""First application-host binding under the actual helper filesystem hardening."""
import json,os,shutil,subprocess,sys,uuid
from pathlib import Path
import pytest
from deployment import application_host_component as component
from deployment.tests.test_application_host_component import artifacts,digest

pytestmark=pytest.mark.skipif(os.getenv('THREE_MM_RUN_HELPER_BIND_TESTS')!='1',reason='Explicit owned root/systemd acceptance only')
SOURCE=Path(__file__).resolve().parents[2]
INSTANCE='3'*24
OTHER='4'*24

def properties(unit,hosts,state,*,fixed):
    text=unit.read_text()
    values=dict(line.split('=',1) for line in text.splitlines() if '=' in line and not line.startswith('#'))
    names=['ProtectSystem','NoNewPrivileges','PrivateTmp','ProtectHome','RestrictAddressFamilies','ReadWritePaths','StateDirectory','StateDirectoryMode']
    result=[]
    for name in names:
        value=values[name]
        if name=='ReadWritePaths':
            tokens=value.split()
            if not fixed:tokens=[t for t in tokens if t.lstrip('-')!='/opt/3mm-application-hosts/instances']
            value=' '.join(tokens).replace('/opt/3mm-application-hosts/instances',str(hosts/'instances'))
        if name=='StateDirectory':
            tokens=value.split()
            if not fixed:tokens=[t for t in tokens if t!='3mm-application-host-updates']
            value=' '.join(tokens).replace('3mm-application-host-updates',state.name)
        result+=['--property='+name+'='+value]
    return result


def test_first_bind_needs_only_mutable_pointer_and_journal_paths(artifacts,monkeypatch):
    assert sys.platform=='linux' and os.geteuid()==0 and Path('/run/systemd/system').is_dir()
    token='3mm-helper-bind-'+uuid.uuid4().hex[:12]
    hosts=Path('/opt')/token;state=Path('/var/lib')/token
    assert not hosts.exists() and not state.exists()
    blob,metadata=artifacts[0]
    try:
        default=component.HostStore(hosts/'default',state/'default',hosts/'releases')
        build=default.bootstrap(blob,digest(blob))
        # Existing default components also need this parent on installer rerun.
        assert not (hosts/'instances').exists()
        monkeypatch.setattr(component,'ROOT',hosts);monkeypatch.setattr(component,'STATE',state)
        monkeypatch.setattr(sys,'argv',['application-host','bootstrap','--source',str(SOURCE)])
        component.main()
        assert (hosts/'instances').is_dir()
        unit=SOURCE/'deployment/systemd/3mm-update-helper.service'
        code="""import errno,json
from pathlib import Path
import deployment.application_host_component as c
c.ROOT=Path(HOSTS);c.STATE=Path(STATE)
a=c.bind_instance(INSTANCE,root=c.ROOT);again=c.bind_instance(INSTANCE,root=c.ROOT);b=c.bind_instance(OTHER,root=c.ROOT)
blocked={}
for label,p in [('default',c.ROOT/'default'/'forbidden'),('binaries',c.ROOT/'releases'/'forbidden')]:
 try:p.write_text('not allowed');blocked[label]=False
 except OSError as e:blocked[label]=e.errno==errno.EROFS
print(json.dumps({'first':a,'repeat':again,'other':b,'immutable_paths_readonly':blocked}))
""".replace('HOSTS',repr(str(hosts))).replace('STATE)',repr(str(state))+')').replace('INSTANCE',repr(INSTANCE)).replace('OTHER',repr(OTHER))
        for fixed in (False,True):
            command=['systemd-run','--quiet','--wait','--pipe','--collect','--service-type=exec','--unit='+token+('-fixed' if fixed else '-before'),'--property=User=root','--working-directory='+str(SOURCE),'--setenv=PYTHONPATH='+str(SOURCE),'--setenv=PYTHONDONTWRITEBYTECODE=1',*properties(unit,hosts,state,fixed=fixed),'/opt/3mm/current/.venv/bin/python','-B','-c',code]
            result=subprocess.run(command,capture_output=True,text=True,timeout=35)
            if not fixed:
                assert result.returncode!=0 and 'Read-only file system' in result.stderr,result.stderr
                assert not (hosts/'instances'/INSTANCE/'current').exists()
            else:
                assert result.returncode==0,result.stderr
                facts=json.loads(result.stdout)
                assert facts=={'first':build,'repeat':build,'other':build,'immutable_paths_readonly':{'default':True,'binaries':True}}
                print(json.dumps({'original_hardening_refused_first_bind':True,'fixed':facts}))
        assert default.target('current')==metadata['build_id']
    finally:
        for p,parent in [(hosts,Path('/opt')),(state,Path('/var/lib'))]:
            assert p.parent==parent and p.name==token and p.resolve()==p
            if p.exists():shutil.rmtree(p)
