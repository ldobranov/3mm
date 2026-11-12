"""Actual bounded child probes, without importing image codecs into Core."""
import os
import sys

import pytest

from packages.application_sdk import media_provider
from packages.application_sdk.media_provider import probe_provider

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Resource-bounded image worker')


def test_absent_optional_package_does_not_start_a_child_or_import_codecs(monkeypatch):
    before = {name for name in sys.modules if name == 'PIL' or name.startswith('PIL.')}
    monkeypatch.setattr(media_provider.importlib.util, 'find_spec', lambda name: None)
    def forbidden(*args, **kwargs):
        pytest.fail('An absent optional image package needs no conformance child')
    monkeypatch.setattr(media_provider.subprocess, 'run', forbidden)
    assert probe_provider() == 'unavailable'
    assert {name for name in sys.modules if name == 'PIL' or name.startswith('PIL.')} == before


@pytest.mark.parametrize('failure', [ImportError, ValueError, RuntimeError])
def test_uncertain_package_lookup_keeps_the_bounded_child_probe(monkeypatch, failure):
    calls = []
    def uncertain(name):
        raise failure('Optional package metadata is inconclusive')
    monkeypatch.setattr(media_provider.importlib.util, 'find_spec', uncertain)
    def inconclusive_child(*args, **kwargs):
        calls.append(kwargs['timeout'])
        assert kwargs['timeout'] == 2
        raise media_provider.subprocess.TimeoutExpired(args[0], kwargs['timeout'])
    monkeypatch.setattr(media_provider.subprocess, 'run', inconclusive_child)
    assert probe_provider() == 'unknown'
    assert calls == [2]


def test_present_optional_package_is_validated_without_importing_it_in_parent(tmp_path, monkeypatch):
    package = tmp_path / 'PIL'
    package.mkdir()
    package.joinpath('__init__.py').write_text('from . import Image')
    package.joinpath('Image.py').write_text('''
class ProbeImage:
    def save(self, output, *, format):
        assert format in ('PNG', 'JPEG', 'WEBP')
        output.write(b'probe')
    def load(self):
        pass
def new(mode, size):
    assert mode == 'RGB' and size == (1, 1)
    return ProbeImage()
def open(source):
    assert source.read() == b'probe'
    return ProbeImage()
''')
    monkeypatch.syspath_prepend(str(tmp_path))
    before = {name for name in sys.modules if name == 'PIL' or name.startswith('PIL.')}
    assert probe_provider() == 'ready'
    assert {name for name in sys.modules if name == 'PIL' or name.startswith('PIL.')} == before


@pytest.mark.parametrize('fault,expected', [('missing','unavailable'), ('broken','unknown'), ('timeout','unknown')])
def test_unusable_image_dependency_is_observed_in_a_child(tmp_path, monkeypatch, fault, expected):
    package = tmp_path / 'PIL'
    package.mkdir()
    package.joinpath('__init__.py').write_text({
        'missing': 'raise ImportError("Image provider is absent")',
        'broken': 'raise RuntimeError("Broken native image library")',
        'timeout': 'import time; time.sleep(10)',
    }[fault])
    monkeypatch.syspath_prepend(str(tmp_path))
    before = tuple(tmp_path.rglob('*'))
    imported = {name for name in sys.modules if name == 'PIL' or name.startswith('PIL.')}
    assert probe_provider() == expected
    assert tuple(tmp_path.rglob('*')) == before  # No bytecode, file namespace or database.
    assert {name for name in sys.modules if name == 'PIL' or name.startswith('PIL.')} == imported


def test_installed_optional_provider_encodes_and_decodes_its_supported_formats_in_child():
    pytest.importorskip('PIL.Image', reason='Install the isolated optional image-provider profile')
    assert probe_provider() == 'ready'
