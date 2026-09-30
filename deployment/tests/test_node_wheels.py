import io
import zipfile

import pytest

from deployment.prepare_node_wheels import digest, normalize_alias


def wheel():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('gpiod-2.5.0.dist-info/WHEEL', 'Wheel-Version: 1.0\nTag: cp313-cp313-linux_armv7l\n')
        archive.writestr('gpiod-2.5.0.dist-info/RECORD', '')
        archive.writestr('gpiod/native.so', b'unchanged-native-code')
    return buffer.getvalue()


def test_explicit_alias_retag_is_deterministic_and_preserves_binary():
    data = wheel()
    name = 'gpiod-2.5.0-cp313-cp313-linux_armv6l.whl'
    files = {n: {'filehash': digest(data)} for n in (name, name.replace('v6l', 'v7l'))}
    result = normalize_alias(data, name, files)
    assert result == normalize_alias(data, name, files)
    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        assert archive.read('gpiod/native.so') == b'unchanged-native-code'
        assert b'linux_armv6l' in archive.read('gpiod-2.5.0.dist-info/WHEEL')
        assert b'sha256=' in archive.read('gpiod-2.5.0.dist-info/RECORD')


def test_unverified_alias_fails():
    with pytest.raises(ValueError, match='hash'):
        normalize_alias(wheel(), 'gpiod-2.5.0-cp313-cp313-linux_armv6l.whl', {})


def test_unreviewed_native_package_fails():
    with pytest.raises(ValueError, match='Unreviewed'):
        normalize_alias(wheel(), 'other-2.5.0-cp313-cp313-linux_armv6l.whl', {})
