"""Request-local immutable code reuse must refuse drift and never retain trust."""
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor
import os

import pytest

from backend.services.application_code_scope import code_verification_scope, load_verified_package
from backend.services import compiled_ui
from backend.services.module_packages import ModulePackageError
from backend.tests.test_compiled_ui_provenance import built
from backend.tests.test_module_packages import application_package


def test_scope_crosses_worker_phases_but_expires_in_copied_context(built, tmp_path):
    _, validated, _, blob = built
    path = tmp_path / 'source.zip'
    path.write_bytes(blob)
    with ThreadPoolExecutor(2) as pool:
        with code_verification_scope():
            first = pool.submit(copy_context().run, load_verified_package, path).result()
            second = pool.submit(copy_context().run, load_verified_package, path).result()
            retained = copy_context()
            assert first is second and first.sha256 == validated.sha256
        assert retained.run(load_verified_package, path) is not first
        with code_verification_scope():
            assert load_verified_package(path) is not first


@pytest.mark.parametrize('policy', ['explicit', 'current'])
def test_reuse_cannot_bypass_a_different_core_compatibility_policy(tmp_path, monkeypatch, policy):
    from backend.services import module_packages
    path = tmp_path / 'application.zip'
    path.write_bytes(application_package())
    with code_verification_scope():
        monkeypatch.setattr(module_packages, 'actual_core_version', lambda: '1.0.0')
        load_verified_package(path, **({'core_version': '1.0.0'} if policy == 'explicit' else {}))
        monkeypatch.setattr(module_packages, 'actual_core_version', lambda: '0.0.0')
        with pytest.raises(ModulePackageError, match='incompatible Core'):
            load_verified_package(path, **({'core_version': '0.0.0'} if policy == 'explicit' else {}))


@pytest.mark.parametrize('change', ['bytes', 'replace', 'link'])
def test_package_change_cannot_reuse_verified_descriptor(built, tmp_path, change):
    _, _, _, blob = built
    path = tmp_path / 'source.zip'
    path.write_bytes(blob)
    with code_verification_scope():
        load_verified_package(path)
        before = path.stat()
        if change == 'link':
            target = tmp_path / 'target.zip'; target.write_bytes(blob)
            path.unlink(); path.symlink_to(target)
        elif change == 'replace':
            path.unlink(); path.write_bytes(blob)
        else:
            path.write_bytes(blob[:-1] + bytes([blob[-1] ^ 1]))
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with pytest.raises((ModulePackageError, OSError)):
            load_verified_package(path)


@pytest.mark.parametrize('change', ['same_size_mtime', 'extra', 'missing', 'permissions', 'provenance'])
def test_verified_build_is_reused_only_while_all_protected_files_match(built, change):
    artifact, validated, _, _ = built
    target = artifact.path / 'assets/clock-test.mjs'
    with code_verification_scope():
        first = compiled_ui.load_compiled_ui_artifact(validated)
        assert compiled_ui.load_compiled_ui_artifact(validated) is first
        before = target.stat()
        if change == 'same_size_mtime':
            target.write_bytes(b'x' * before.st_size)
            os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        elif change == 'extra': (artifact.path / 'extra.mjs').write_bytes(b'')
        elif change == 'missing': target.unlink()
        elif change == 'provenance': (artifact.path / 'build-provenance.json').write_text('{}')
        else: target.chmod(0o666)
        with pytest.raises(compiled_ui.CompiledUiBuildError):
            compiled_ui.load_compiled_ui_artifact(validated)
