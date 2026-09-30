"""Build the minimal ARMv6/Python 3.13 Node artifact, separate from Core OTA."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deployment.build_release import (PayloadFile, write_release_archive,
    COMMIT_PATTERN, SEMVER_PATTERN, REPOSITORY_PATTERN)
from deployment.prepare_node_wheels import digest

RUNTIME_FILES = ('__init__.py', 'services.py', 'activate.py', 'install_profile.py',
                 'network_recovery.py', 'node_recovery.py')
UNITS = ('3mm-agent.service', '3mm-setup.service', '3mm-setup-ap.service',
         '3mm-network-helper.service', '3mm-node-recovery.service',
         '3mm-captive-portal-dnsmasq.conf')
APT_PACKAGES = sorted(['avahi-daemon', 'ca-certificates', 'curl', 'dnsmasq-base',
                      'network-manager', 'python3', 'python3-venv', 'util-linux'])


def build(root, wheels, output, *, version, commit, repository, epoch,
          working_tree=False):
    if not (SEMVER_PATTERN.fullmatch(version) and COMMIT_PATTERN.fullmatch(commit)
            and REPOSITORY_PATTERN.fullmatch(repository) and epoch > 0):
        raise ValueError('Invalid release identity')
    if (root / 'VERSION').read_text().strip() != version:
        raise ValueError('VERSION does not match')
    names = {'VERSION', 'deployment/install-systemd.sh', 'deployment/node-requirements.txt',
             'deployment/node_preflight.py'}
    names.update('three_mm_runtime/' + name for name in RUNTIME_FILES)
    names.update('deployment/systemd/' + name for name in UNITS)
    for package in ('agent', 'setup_service', 'three_mm_protocol', 'three_mm_provisioning'):
        for path in (root / package).rglob('*'):
            relative = path.relative_to(root)
            if (path.is_file() and not {'tests', '__pycache__'} & set(relative.parts)
                    and path.suffix in {'.py', '.html', '.txt'}):
                names.add(relative.as_posix())
    payload = []
    for name in sorted(names):
        path = root / name
        if path.is_symlink():
            raise ValueError('Symlinks are not release input')
        # Windows source checkouts must not ship CRLF Bash scripts.
        data = path.read_bytes().replace(b'\r\n', b'\n')
        payload.append(PayloadFile(name, data, 0o755 if name.endswith('.sh') else 0o644))
    provenance = json.loads((wheels / 'provenance.json').read_text())
    if provenance.get('architecture') != 'armv6l' or provenance.get('python') != '3.13':
        raise ValueError('Wrong wheelhouse target')
    seen = set()
    for entry in provenance['wheels']:
        name = entry['filename']
        if Path(name).name != name or '\\' in name or not name.endswith('.whl') or name in seen:
            raise ValueError('Invalid wheel name')
        seen.add(name)
        data = (wheels / name).read_bytes()
        if digest(data) != entry['sha256']:
            raise ValueError('Wheel checksum mismatch')
        payload.append(PayloadFile('deployment/node-wheels/' + name, data, 0o644))
    if not seen:
        raise ValueError('Empty wheelhouse')
    payload.append(PayloadFile('deployment/node-wheels/provenance.json',
                              (wheels / 'provenance.json').read_bytes(), 0o644))
    payload.append(PayloadFile('.3mm-install-profile', b'node\n', 0o644))
    tag = 'v' + version
    filename = f'3mm-{version}-node-armv6l.tar.gz'
    sha, size = write_release_archive(output / filename, payload, {
        'architecture': 'armv6l', 'profile': 'node', 'python': '3.13',
        'branch': 'main', 'commit': commit, 'release_id': tag, 'version': version,
        'includes_working_tree': working_tree}, epoch=epoch)
    suffix = version.partition('-')[2]
    manifest = {'schema_version': 1, 'profile': 'node', 'version': version,
        'release_id': tag, 'commit': commit,
        'channel': 'stable' if not suffix else 'test' if suffix.split('.')[0] == 'test' else 'beta',
        'dependencies': {'apt_packages': APT_PACKAGES},
        'artifacts': [{'architecture': 'armv6l', 'python': '3.13', 'filename': filename,
            'sha256': sha, 'size_bytes': size,
            'download_url': f'https://github.com/{repository}/releases/download/{tag}/{filename}'}]}
    (output / '3mm-node-manifest.json').write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path('.'))
    parser.add_argument('--wheels', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--repository', default='ldobranov/3mm')
    parser.add_argument('--epoch', type=int, required=True)
    parser.add_argument('--working-tree', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.source_root, args.wheels, args.output, version=args.version,
        commit=args.commit, repository=args.repository, epoch=args.epoch,
        working_tree=args.working_tree)))
