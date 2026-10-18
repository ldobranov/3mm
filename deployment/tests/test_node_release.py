import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

from deployment.build_node_release import build
from deployment.prepare_node_wheels import digest

ROOT = Path(__file__).resolve().parents[2]


def test_node_archive_is_minimal_and_reproducible(tmp_path):
    wheels = tmp_path / 'wheels'
    wheels.mkdir()
    name = 'test-1.0-py3-none-any.whl'
    (wheels / name).write_bytes(b'fixture')
    (wheels / 'provenance.json').write_text(json.dumps({
        'architecture': 'armv6l', 'python': '3.13',
        'wheels': [{'filename': name, 'sha256': digest(b'fixture')}]}))
    args = dict(version=(ROOT / 'VERSION').read_text().strip(), commit='a' * 40,
                repository='example/3mm', epoch=1700000000)
    first = build(ROOT, wheels, tmp_path / 'first', **args)
    second = build(ROOT, wheels, tmp_path / 'second', **args)
    assert first == second
    assert first['profile'] == 'node'
    assert not {'nodejs', 'npm'} & set(first['dependencies']['apt_packages'])
    with tarfile.open(tmp_path / 'first' / first['artifacts'][0]['filename']) as archive:
        names = archive.getnames()
        assert '.3mm-install-profile' in names
        assert 'setup_service/static/setup.html' in names
        assert 'three_mm_runtime/node_recovery.py' in names
        assert not any(n.startswith(('backend/', 'frontend/', 'modules/')) for n in names)
        assert 'three_mm_runtime/update_helper.py' not in names
        assert b'\r' not in archive.extractfile('deployment/install-systemd.sh').read()
        assert 'agent/session_transport.py' in names
        assert 'three_mm_protocol/interactive_session.py' in names
        assert not any(n.startswith('three_mm_application_sdk/') for n in names)
        extracted = tmp_path / 'extracted-node'
        archive.extractall(extracted, filter='data')
    # Import the actual artifact, not the full checkout. Fail if the unused M21
    # Agent prototype drags Core or the application SDK into a minimal Node.
    result = subprocess.run(
        [sys.executable, '-c', '''
import importlib.abc
import sys
class NoCoreOrSdk(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'backend', 'three_mm_application_sdk'}:
            raise ModuleNotFoundError('Node must not need Core or Application SDK')
sys.meta_path.insert(0, NoCoreOrSdk())
from agent.session_transport import AgentSessionHost
assert AgentSessionHost().capability_ids() == []
'''],
        cwd=extracted, env={**os.environ, 'PYTHONPATH': str(extracted)},
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    (wheels / name).write_bytes(b'changed')
    with pytest.raises(ValueError, match='checksum'):
        build(ROOT, wheels, tmp_path / 'third', **args)
