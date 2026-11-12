"""New-project identity, real validation and no-clobber filesystem boundaries."""
import ast
import json
from pathlib import Path
import subprocess
import sys

import pytest

from backend.artifacts.packages import validate_module_package
from tools import application_scaffold as scaffold
from tools.application_project import ProjectCheckError, build_package, configuration, inputs


def create(destination, **overrides):
    return scaffold.create_project(destination, **{'module_id': 'org.example.own-note',
        'name': 'Собствена бележка', 'route': '/own-note', **overrides})


def test_generated_identity_is_complete_and_actual_package_validates(tmp_path):
    destination = tmp_path/'new project'
    result = create(destination)
    package = validate_module_package(build_package(destination))
    assert result['status'] == 'created' and result['checks'] == 'not_run'
    assert result['installation'] == result['grants'] == result['physical_write'] == 'not_requested'
    assert package.manifest.module_id == package.application_extension.module_id == package.compiled_ui.module_id == 'org.example.own-note'
    assert package.manifest.version == package.application_extension.version == package.compiled_ui.version == '1.0.0'
    assert package.manifest.name == 'Собствена бележка'
    assert package.compiled_ui.entrypoints[0].route == '/own-note'
    assert package.compiled_ui.entrypoints[0].label.en == package.manifest.name
    assert (destination/'.3mm-source-only').read_bytes() == b''
    assert configuration(destination)['scenarios'] == configuration(scaffold.TEMPLATE)['scenarios']
    contexts = [node for node in ast.walk(ast.parse((destination/'tests/test_service.py').read_text(encoding='utf-8')))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'ApplicationContext']
    assert contexts[0].args[0].value == package.manifest.module_id
    assert all(node.args[1].value == '1.0.0' for node in contexts)
    guide = (destination/'README.md').read_text(encoding='utf-8')
    assert '/own-note' in guide and 'org.example.own-note' in guide
    assert 'PATH_TO_PROJECT' in guide and 'not a hostile-code sandbox' in guide
    assert 'modules/application-starter --output' not in guide
    assert (destination/'AGENTS.md').read_bytes() == (scaffold.TEMPLATE/'AGENTS.md').read_bytes()
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(build_package(destination))) as archive:
        assert 'AGENTS.md' not in archive.namelist()
    assert not list(tmp_path.glob('.3mm-new-*'))


@pytest.mark.parametrize('value', ['file', 'directory', 'link'])
def test_existing_destination_is_never_replaced(tmp_path, value):
    destination = tmp_path/'existing'
    if value == 'directory':
        destination.mkdir()
    elif value == 'file':
        destination.write_text('user content')
    else:
        try:
            destination.symlink_to(tmp_path/'missing')
        except OSError:
            pytest.skip('Environment cannot create symbolic links')
    with pytest.raises(ProjectCheckError, match='already exists'):
        create(destination)
    assert destination.is_dir() if value == 'directory' else destination.is_symlink() if value == 'link' else destination.read_text() == 'user content'
    assert not list(tmp_path.glob('.3mm-new-*'))


@pytest.mark.parametrize('change', [
    {'module_id': '../bad'}, {'module_id': 'one'}, {'module_id': 'org.3mm.application-starter'},
    {'name': ''}, {'name': '  '}, {'name': 'two\nlines'}, {'name': ' bad'}, {'name': 'n'*121},
    {'route': 'relative'}, {'route': '/../bad'}, {'route': '/wrong?token=bad'},
])
def test_invalid_identity_never_publishes(tmp_path, change):
    destination = tmp_path/'new'
    with pytest.raises(ProjectCheckError):
        create(destination, **change)
    assert not destination.exists() and not list(tmp_path.glob('.3mm-new-*'))


def test_destination_parent_must_exist_and_not_redirect(tmp_path):
    with pytest.raises(ProjectCheckError, match='parent directory'):
        create(tmp_path/'missing'/'new')
    link = tmp_path/'linked'
    actual = tmp_path/'actual'
    actual.mkdir()
    try:
        link.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip('Environment cannot create symbolic links')
    with pytest.raises(ProjectCheckError, match='parents'):
        create(link/'new')
    assert not (actual/'new').exists()


def test_racing_destination_is_not_overwritten_even_when_empty(tmp_path, monkeypatch):
    destination = tmp_path/'new'
    publish = scaffold._publish_new_directory
    def competing(source, target):
        target.mkdir()
        publish(source, target)
    monkeypatch.setattr(scaffold, '_publish_new_directory', competing)
    with pytest.raises(ProjectCheckError):
        create(destination)
    assert destination.is_dir() and not list(destination.iterdir())
    assert not list(tmp_path.glob('.3mm-new-*'))


def test_failed_real_semantic_validation_leaves_no_project(tmp_path, monkeypatch):
    snapshot = tmp_path/'template'
    for filename, data in inputs(scaffold.TEMPLATE).items():
        path = snapshot/filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (snapshot/'.3mm-source-only').touch()
    manifest = snapshot/'manifest.json'
    value = json.loads(manifest.read_text())
    value['entrypoints']['core'] = 'missing.json'
    manifest.write_text(json.dumps(value))
    monkeypatch.setattr(scaffold, 'TEMPLATE', snapshot)
    with pytest.raises(ProjectCheckError):
        create(tmp_path/'new')
    assert not (tmp_path/'new').exists() and not list(tmp_path.glob('.3mm-new-*'))


def test_template_change_after_freeze_never_publishes(tmp_path, monkeypatch):
    real_inputs = scaffold.inputs
    calls = 0
    def changed(path):
        nonlocal calls
        calls += 1
        result = real_inputs(path)
        if calls > 1:
            result['README.md'] += b'\nConcurrent edit\n'
        return result
    monkeypatch.setattr(scaffold, 'inputs', changed)
    with pytest.raises(ProjectCheckError, match='changed'):
        create(tmp_path/'new')
    assert not (tmp_path/'new').exists() and not list(tmp_path.glob('.3mm-new-*'))


def test_created_project_python_denial_tests_execute_outside_modules(tmp_path):
    destination = tmp_path/'independent'
    create(destination)
    root = Path(__file__).resolve().parents[2]
    import os
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        'tests/test_service.py', '--basetemp='+str(tmp_path/'owned-tests')], cwd=destination,
        env={**os.environ, 'PYTHONPATH': str(root)}, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout+result.stderr
    assert '6 passed' in result.stdout and 'skipped' not in result.stdout
