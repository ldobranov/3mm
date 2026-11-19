"""Opt-in systemd acceptance with disposable data, never installed app paths."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

import pytest


UNIT = Path(__file__).resolve().parents[1] / 'systemd' / '3mm-application-extension@.service'
pytestmark = pytest.mark.skipif(os.environ.get('TEST_APP_MOUNT_NAMESPACE') != '1',
                                reason='Explicit disposable Linux systemd integration only')


def test_only_selected_instance_is_visible_and_writable_under_shared_account():
    assert os.geteuid() == 0 and Path('/run/systemd/system').is_dir()
    import pwd
    account = pwd.getpwnam('nobody')
    unit = dict(line.split('=', 1) for line in UNIT.read_text().splitlines()
                if '=' in line and not line.startswith('#'))
    with tempfile.TemporaryDirectory(dir='/run', prefix='app-mount-test-') as tmp:
        root = Path(tmp)
        root.chmod(0o755)
        state, config = root / 'state', root / 'config'
        state_apps, keys = state / 'application-extensions', config / 'application-extensions'
        keys.mkdir(parents=True)
        (state / 'core').mkdir(parents=True)
        (config / 'private-marker').touch()
        ids = [uuid.uuid4().hex[:24] for _ in range(2)]
        for instance in ids:
            own = state_apps / instance
            for sub in ('data', 'run'):
                p = own / sub
                p.mkdir(parents=True)
                os.chown(p, account.pw_uid, account.pw_gid)
            (own / 'active.json').write_text('{}')
            (keys / (instance+'.key')).write_text('public fixture marker')
        verify = """
from pathlib import Path
import errno,json,os,socket,sys
root,instance=Path(sys.argv[1]),sys.argv[2]
apps=root/'state'/'application-extensions'
keys=root/'config'/'application-extensions'
own=apps/instance
assert os.geteuid()!=0
assert {p.name for p in apps.iterdir()}=={instance}
assert {p.name for p in keys.iterdir()}=={instance+'.key'}
assert (keys/(instance+'.key')).read_text()=='public fixture marker' and (own/'active.json').read_text()=='{}'
assert not (root/'state'/'core').exists() and not (root/'config'/'private-marker').exists()
(own/'data'/'written').write_text(instance)
with socket.socket(socket.AF_UNIX) as server:
    server.bind(str(own/'run'/'service.sock'))
assert os.statvfs(own).f_flag & os.ST_RDONLY
print(json.dumps({'visible':instance,'writable_data_and_run':True}))
"""
        for i in ids:
            properties = []
            for name in ('TemporaryFileSystem', 'BindReadOnlyPaths', 'BindPaths', 'ReadWritePaths',
                         'ProtectSystem', 'PrivateTmp', 'NoNewPrivileges', 'PrivateNetwork', 'RestrictAddressFamilies'):
                value = unit[name].replace('/var/lib/3mm', str(state)).replace('/etc/3mm', str(config)).replace('%i', i)
                properties.append('--property=' + name + '=' + value)
            result = subprocess.run(['systemd-run','--quiet','--pipe','--wait','--collect',
                                     '--unit=app-mount-test-'+i,'--property=User=nobody',
                                     '--property=RuntimeMaxSec=15s',*properties,
                                     '/usr/bin/python3','-I','-B','-c',verify,str(root),i],
                                    capture_output=True,text=True,timeout=30)
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout) == {'visible':i,'writable_data_and_run':True}
            assert (state_apps/i/'data'/'written').read_text() == i
            assert (state_apps/i/'run'/'service.sock').is_socket()
        assert {p.name for p in state_apps.iterdir()} == set(ids)
