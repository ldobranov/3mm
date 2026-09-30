"""Prepare a CPython 3.13 ARMv6 wheelhouse with explicit piwheels provenance.

Only the two tested piwheels aliases may have their platform metadata corrected.
Native binary bytes are unchanged. Source and output hashes are recorded.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import urlopen
import zipfile

ALIASES = {'pydantic_core': '2.46.4', 'gpiod': '2.5.0'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalize_alias(data: bytes, filename: str, files: dict) -> bytes:
    package, version, python, abi, platform = filename[:-4].split('-')
    if (ALIASES.get(package) != version or python != 'cp313' or abi != 'cp313'
            or platform != 'linux_armv6l'):
        raise ValueError('Unreviewed native wheel')
    sibling = filename.replace('linux_armv6l', 'linux_armv7l')
    original_hash = digest(data)
    if any(files.get(name, {}).get('filehash') != original_hash
           for name in (filename, sibling)):
        raise ValueError('piwheels ARMv6/ARMv7 aliases do not match the downloaded hash')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate wheel entry')
        contents = {name: archive.read(name) for name in names}
    prefix = f'{package}-{version}.dist-info/'
    wheel_name, record_name = prefix + 'WHEEL', prefix + 'RECORD'
    metadata = contents[wheel_name].decode('utf-8')
    tags = [line for line in metadata.splitlines() if line.startswith('Tag:')]
    if tags != ['Tag: cp313-cp313-linux_armv7l']:
        raise ValueError('Unexpected native wheel metadata')
    contents[wheel_name] = metadata.replace(tags[0], 'Tag: cp313-cp313-linux_armv6l').encode()
    if any(name.endswith(('/RECORD.jws', '/RECORD.p7s')) for name in names):
        raise ValueError('Cannot retag a signed wheel')
    records = io.StringIO(newline='')
    writer = csv.writer(records, lineterminator='\n')
    for name, value in sorted(contents.items()):
        if name != record_name:
            encoded = base64.urlsafe_b64encode(hashlib.sha256(value).digest()).rstrip(b'=').decode()
            writer.writerow([name, 'sha256=' + encoded, len(value)])
    writer.writerow([record_name, '', ''])
    contents[record_name] = records.getvalue().encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in sorted(contents.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, value)
    return output.getvalue()


def prepare(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Output wheelhouse must be empty')
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='3mm-node-wheels-') as directory:
        subprocess.run([sys.executable, '-m', 'pip', '--isolated', 'download',
            '--disable-pip-version-check', '--only-binary=:all:',
            '--index-url', 'https://pypi.org/simple',
            '--extra-index-url', 'https://www.piwheels.org/simple',
            '--platform', 'linux_armv6l', '--python-version', '313',
            '--implementation', 'cp', '--abi', 'cp313', '--dest', directory,
            '-r', str(root / 'agent/requirements.txt'),
            '-r', str(root / 'setup_service/requirements.txt'), 'gpiod==2.5.0'], check=True)
        entries = []
        for path in sorted(Path(directory).glob('*.whl')):
            source = data = path.read_bytes()
            normalized = not path.name.endswith('-none-any.whl')
            if normalized:
                package, version = path.name.split('-')[:2]
                if ALIASES.get(package) != version:
                    raise ValueError('Unreviewed native dependency: ' + path.name)
                url = f'https://www.piwheels.org/project/{package.replace("_", "-")}/json'
                with urlopen(url, timeout=30) as response:
                    files = json.load(response)['releases'][version]['files']
                data = normalize_alias(source, path.name, files)
            (output / path.name).write_bytes(data)
            entries.append({'filename': path.name, 'source_sha256': digest(source),
                            'sha256': digest(data), 'retagged_piwheels_alias': normalized})
        (output / 'provenance.json').write_text(json.dumps({
            'schema_version': 1, 'architecture': 'armv6l', 'python': '3.13',
            'wheels': entries}, indent=2, sort_keys=True) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args().output)
