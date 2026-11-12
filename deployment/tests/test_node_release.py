import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

from deployment.build_node_release import build, RUNTIME_FILES
from deployment.prepare_node_wheels import digest

ROOT = Path(__file__).resolve().parents[2]
SETUP_FILES = {'components/__init__.py', 'components/setup/requirements.txt',
               'components/setup/static/setup.html', *('components/setup/' + name + '.py' for name in
               ('__init__', '__main__', 'captive_portal', 'cli', 'config', 'main', 'product', 'provision', 'schemas'))}


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
    assert not {'network-manager', 'dnsmasq-base'} & set(first['dependencies']['apt_packages'])
    with tarfile.open(tmp_path / 'first' / first['artifacts'][0]['filename']) as archive:
        names = archive.getnames()
        assert 'deployment/systemd/3mm-setup-local.service' in names
        assert '.3mm-install-profile' in names
        assert 'deployment/component_transition.py' in names
        assert 'components/setup/static/setup.html' in names
        assert 'components/setup/product.py' in names
        assert 'config_templates/product.json' in names
        assert 'components/system_runtime/node_recovery.py' in names
        assert not any(n.startswith(('backend/', 'frontend/', 'modules/', 'setup_service/')) for n in names)
        assert {n for n in names if n.startswith('components/')} == SETUP_FILES | {
            'components/system_runtime/' + name for name in RUNTIME_FILES}
        assert not any(n.startswith('three_mm_runtime/') for n in names)
        assert archive.extractfile('components/__init__.py').read() == (ROOT/'components/__init__.py').read_bytes()
        assert archive.extractfile('components/setup/static/setup.html').read() == (ROOT/'components/setup/static/setup.html').read_bytes().replace(b'\r\n',b'\n')
        assert 'components/system_runtime/update_helper.py' not in names
        assert b'\r' not in archive.extractfile('deployment/install-systemd.sh').read()
        assert 'agent/session_transport.py' in names
        assert 'components/system_runtime/session_output.py' in names
        assert 'packages/protocol/interactive_session.py' in names
        assert 'packages/__init__.py' in names
        assert 'packages/platform_wire/__init__.py' in names
        assert 'packages/protocol/__init__.py' in names
        assert {'packages/provisioning/__init__.py','packages/provisioning/network_recovery.py',
                'packages/provisioning/network_helper.py','packages/provisioning/setup_access_point.py'} <= set(names)
        asset='packages/protocol/theme_design_defaults.json'
        assert archive.extractfile(asset).read()==(ROOT/asset).read_bytes()
        assert not any(n.startswith('three_mm_protocol/') for n in names)
        assert not any(n.startswith('three_mm_provisioning/') for n in names)
        assert all(n=='packages/__init__.py' or n==asset
                   or Path(n).parent.as_posix() in {'packages/platform_wire','packages/protocol','packages/provisioning'} and n.endswith('.py')
                   for n in names if n.startswith('packages/'))
        assert not any(n.startswith(('three_mm_application_sdk/','packages/application_sdk/')) for n in names)
        extracted = tmp_path / 'extracted-node'
        archive.extractall(extracted, filter='data')
    # Import the actual artifact, not the full checkout. Fail if the unused M21
    # Agent prototype drags Core or the application SDK into a minimal Node.
    result = subprocess.run(
        [sys.executable, '-E', '-c', '''
import importlib.abc
import importlib.util
import sys
class NoCoreOrSdk(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname.split('.')[0] in {'backend', 'three_mm_application_sdk'}
                or fullname=='packages.application_sdk' or fullname.startswith('packages.application_sdk.')):
            raise ModuleNotFoundError('Node must not need Core or Application SDK')
sys.meta_path.insert(0, NoCoreOrSdk())
from agent.session_transport import AgentSessionHost
from deployment import component_transition
from components.system_runtime.session_output import pump_session_output
from components.setup.product import load_product_metadata
from components.setup.captive_portal import AP_SETUP_URL
from packages.protocol.theme_extension_v2 import DESIGN_DEFAULTS, validate_design
from packages.provisioning import MemoryProvisioningStore, ProvisioningStateMachine
from packages.provisioning.mock_network import MockNetworkAdapter
from packages.provisioning.network_helper import _handle_request
assert importlib.util.find_spec('three_mm_provisioning') is None
assert importlib.util.find_spec('setup_service') is None
assert importlib.util.find_spec('three_mm_runtime') is None
for sibling in ('admin_web', 'public_web', 'platform_runtime'):
    assert importlib.util.find_spec('components.' + sibling) is None
assert MemoryProvisioningStore().load() is None
assert ProvisioningStateMachine(MockNetworkAdapter()).start_setup().state.value == 'setup'
assert _handle_request(None) == {'ok': False, 'error': 'invalid_request'}
assert AgentSessionHost().capability_ids() == []
assert callable(pump_session_output)
assert callable(component_transition.main)
assert load_product_metadata()['schema_version'] == 1
assert AP_SETUP_URL == 'http://10.42.0.1:8895/setup'
assert validate_design(DESIGN_DEFAULTS) == DESIGN_DEFAULTS
'''],
        cwd=extracted, env={**os.environ, 'PYTHONPATH': str(extracted)},
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run([sys.executable, '-E', '-m', 'components.setup', '--help'],
        cwd=extracted, env={**os.environ, 'PYTHONPATH': str(extracted)},
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert '--read-only' in result.stdout and '--recovery-captive-port' in result.stdout
    (wheels / name).write_bytes(b'changed')
    with pytest.raises(ValueError, match='checksum'):
        build(ROOT, wheels, tmp_path / 'third', **args)


def test_wheelhouse_uses_the_installer_dependency_lock(tmp_path, monkeypatch):
    from deployment import prepare_node_wheels as preparation

    def download(command, **kwargs):
        requirements = [command[i + 1] for i, value in enumerate(command) if value == '-r']
        assert requirements == [str(ROOT / 'deployment/node-requirements.txt')]
        # A newer transitive release must not displace the Agent's exact pins.
        lock = (ROOT / 'deployment/node-requirements.txt').read_text()
        assert '-r service-agent-requirements.txt' in lock
        destination = Path(command[command.index('--dest') + 1])
        (destination / 'fixture-1-py3-none-any.whl').write_bytes(b'fixture')

    monkeypatch.setattr(preparation.subprocess, 'run', download)
    output = tmp_path / 'locked-wheels'
    preparation.prepare(output)
    provenance = json.loads((output / 'provenance.json').read_text())
    assert provenance['wheels'][0]['sha256'] == digest(b'fixture')
