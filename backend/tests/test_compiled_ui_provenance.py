"""Whole-build pins, bounded verified bytes and legacy compatibility."""

import json
import os
from pathlib import Path

import pytest

from backend.services import compiled_ui
from backend.services.compiled_ui_provenance import read_asset, UiBuildEvidenceError
from backend.services.module_packages import validate_module_package
from backend.tests.test_compiled_ui import fake_compiler, package


def compiler_with_evidence(calls):
    compile_fake = fake_compiler(calls)

    def run(command, **kwargs):
        result = compile_fake(command, **kwargs)
        (Path(command[3]) / 'build-toolchain.json').write_text(json.dumps(
            {'node': '24.19.0', 'vite': '6.4.3', 'vue_plugin': '5.2.4'}))
        return result

    return run


@pytest.fixture
def built(monkeypatch, tmp_path):
    blob = package()
    validated = validate_module_package(blob)
    calls = []
    monkeypatch.setenv('COMPILED_UI_ARTIFACTS_DIR', str(tmp_path / 'builds'))
    monkeypatch.setattr(compiled_ui.subprocess, 'run', compiler_with_evidence(calls))
    artifact = compiled_ui.compile_ui_package(blob, validated)
    return artifact, validated, calls, blob


def test_recorded_build_is_cached_and_reads_verified_bytes(built):
    artifact, validated, calls, blob = built
    assert len(artifact.built_ui_sha256) == 64
    assert compiled_ui.compile_ui_package(blob, validated) == artifact
    assert len(calls) == 1
    assert read_asset(artifact, 'assets/clock-test.mjs') == b'export default {}'
    value = json.loads((artifact.path / 'build-provenance.json').read_bytes())
    assert value['source_sha256'] == validated.sha256
    assert {'artifact.json', 'compiled-ui.json', 'entrypoints.json', 'build-toolchain.json'} <= value['files'].keys()


@pytest.mark.parametrize('change', ['asset', 'css', 'extra', 'missing', 'index', 'source', 'toolchain', 'compiler', 'duplicate'])
def test_whole_inventory_drift_is_never_loaded_as_the_reviewed_build(built, change):
    artifact, validated, _, _ = built
    if change in {'asset', 'css', 'extra', 'index'}:
        relative = {'asset': 'assets/clock-test.mjs', 'css': 'assets/clock-test.css',
            'extra': 'assets/extra.mjs', 'index': 'entrypoints.json'}[change]
        (artifact.path / relative).write_text('changed')
    elif change == 'missing':
        (artifact.path / 'assets/clock-test.mjs').unlink()
    elif change == 'toolchain':
        (artifact.path / 'build-toolchain.json').write_text('{}')
    else:
        manifest = artifact.path / 'build-provenance.json'
        value = json.loads(manifest.read_bytes())
        value['source_sha256' if change == 'source' else 'compiler_sha256'] = 'f' * 64
        manifest.write_text(json.dumps(value) if change != 'duplicate' else '{"build_version":1,"build_version":1}')
    if change == 'compiler':
        # Coherently replacing build metadata yields a DIFFERENT identity, never
        # the old native attestation. Compiler source changes do not retroactively
        # revoke already immutable outputs from an older installed toolchain.
        assert compiled_ui.load_compiled_ui_artifact(validated).built_ui_sha256 != artifact.built_ui_sha256
    else:
        with pytest.raises(compiled_ui.CompiledUiBuildError):
            compiled_ui.load_compiled_ui_artifact(validated)


def test_asset_is_checked_again_after_load_and_paths_are_closed(built):
    artifact, _, _, _ = built
    for relative in ('../artifact.json', '/artifact.json', 'assets/../artifact.json', 'assets\\clock-test.mjs'):
        with pytest.raises(UiBuildEvidenceError):
            read_asset(artifact, relative)
    (artifact.path / 'assets/clock-test.mjs').write_text('changed')
    with pytest.raises(UiBuildEvidenceError):
        read_asset(artifact, 'assets/clock-test.mjs')


def test_legacy_outputs_are_not_silently_promoted(monkeypatch, tmp_path):
    blob = package()
    validated = validate_module_package(blob)
    calls = []
    monkeypatch.setenv('COMPILED_UI_ARTIFACTS_DIR', str(tmp_path / 'builds'))
    monkeypatch.setattr(compiled_ui.subprocess, 'run', fake_compiler(calls))
    assert compiled_ui.compile_ui_package(blob, validated).built_ui_sha256 is None
    monkeypatch.setattr(compiled_ui.subprocess, 'run', compiler_with_evidence(calls))
    assert compiled_ui.compile_ui_package(blob, validated).built_ui_sha256 is None
    assert len(calls) == 1


@pytest.mark.skipif(os.name != 'posix', reason='Actual POSIX ownership and symlinks')
@pytest.mark.parametrize('change', ['file_writable', 'directory_writable', 'asset_link', 'manifest_link'])
def test_unprotected_or_linked_outputs_never_supply_build_evidence(built, change):
    artifact, validated, _, _ = built
    asset = artifact.path / 'assets/clock-test.mjs'
    if change == 'file_writable':
        asset.chmod(0o666)
    elif change == 'directory_writable':
        (artifact.path / 'assets').chmod(0o777)
    else:
        target = artifact.path / ('build-provenance.json' if change == 'manifest_link' else 'assets/clock-test.mjs')
        target.unlink()
        target.symlink_to(artifact.path / 'absent')
    with pytest.raises(compiled_ui.CompiledUiBuildError):
        compiled_ui.load_compiled_ui_artifact(validated)
