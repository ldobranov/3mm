import json
from pathlib import Path
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
    (wheels / name).write_bytes(b'changed')
    with pytest.raises(ValueError, match='checksum'):
        build(ROOT, wheels, tmp_path / 'third', **args)
