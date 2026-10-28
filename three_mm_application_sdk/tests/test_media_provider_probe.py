"""Actual bounded child probes, without importing image codecs into Core."""
import os
import sys

import pytest

from three_mm_application_sdk.media_provider import probe_provider

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Resource-bounded image worker')


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
    assert probe_provider() == expected
    assert tuple(tmp_path.rglob('*')) == before  # No bytecode, file namespace or database.


def test_installed_optional_provider_encodes_and_decodes_its_supported_formats_in_child():
    pytest.importorskip('PIL.Image', reason='Install the isolated optional image-provider profile')
    assert probe_provider() == 'ready'
