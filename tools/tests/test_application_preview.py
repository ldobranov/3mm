"""Preview configuration/lifecycle and CLI boundaries; browser behavior is separate."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import application_preview as preview
from tools.application_project import ProjectCheckError, inputs

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def source(tmp_path, monkeypatch):
    project = tmp_path/'project'
    for name, data in inputs(ROOT/'modules/application-starter').items():
        target = project/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    frontend = tmp_path/'frontend'
    for name in ['node_modules/vite', 'node_modules/@vitejs/plugin-vue']:
        (frontend/name).mkdir(parents=True)
    monkeypatch.setenv('COMPILED_UI_NODE', 'test-node')
    return project, frontend


def test_preview_uses_exact_project_entry_and_public_descriptor_identity(source):
    project, frontend = source
    settings = preview.preview_settings(project, frontend=frontend)
    assert settings['source'] == str(project/'source/frontend/Notes.vue')
    assert settings['mock'] == str(project/'preview/host.ts')
    assert settings['info']['module_id'] == 'org.3mm.application-starter'
    assert settings['info']['artifact_sha256'] == '0'*64  # Never an actual trust proof.
    assert {op['operation_id'] for op in settings['info']['operations']} == {
        'save_note', 'read_note', 'lookup_save', 'observe_resource'}
    assert not any('token' in key or 'url' in key for key in settings)


@pytest.mark.parametrize('port', [0, 1023, 65536, '5178', True])
def test_bad_port_never_starts_a_process(source, monkeypatch, port):
    monkeypatch.setattr(preview.subprocess, 'Popen', lambda *_a, **_kw: pytest.fail('No process should start'))
    with pytest.raises(ProjectCheckError, match='port'):
        preview.preview_settings(source[0], frontend=source[1], port=port)


@pytest.mark.parametrize('change', [
    lambda c: c.pop('preview'),
    lambda c: c['preview'].update(host='../outside.ts'),
    lambda c: c['preview'].update(entrypoint_id='missing'),
])
def test_missing_or_escaping_preview_configuration_refuses(source, change):
    project, frontend = source
    path = project/'development.json'
    value = json.loads(path.read_text()); change(value); path.write_text(json.dumps(value))
    with pytest.raises(ProjectCheckError):
        preview.preview_settings(project, frontend=frontend)


def test_owned_child_is_stopped_and_temp_files_removed_on_interrupt(source, monkeypatch):
    settings_file = None
    child = SimpleNamespace(alive=True, terminated=False)
    def start(command, **_):
        nonlocal settings_file
        settings_file = Path(command[-1])
        settings = json.loads(settings_file.read_text())
        assert settings['port'] == 5178 and settings['project'] == str(source[0])
        return child
    def wait(timeout=None):
        if timeout is None:
            raise KeyboardInterrupt
        child.alive = False
        return 0
    child.wait = wait
    child.poll = lambda: None if child.alive else 0
    child.terminate = lambda: setattr(child, 'terminated', True)
    monkeypatch.setattr(preview.subprocess, 'Popen', start)
    preview.preview_project(source[0], frontend=source[1])
    assert child.terminated and not child.alive
    assert not settings_file.parent.exists()


def test_preview_process_failure_is_not_a_success(source, monkeypatch):
    monkeypatch.setattr(preview.subprocess, 'Popen', lambda *_a, **_kw: SimpleNamespace(wait=lambda: 1, poll=lambda: 1))
    with pytest.raises(ProjectCheckError, match='unsuccessfully'):
        preview.preview_project(source[0], frontend=source[1])


def test_cli_retains_exact_identity_if_evidence_fails_after_package_publication(monkeypatch, tmp_path, capsys):
    from tools import application_project, extension_dev
    import sys
    monkeypatch.setattr(sys, 'argv', ['extension-dev', 'check', 'project', '--output', str(tmp_path/'app.zip')])
    monkeypatch.setattr(application_project, 'check_project', lambda *_a, **_kw: {
        'status': 'failed', 'stage': 'output', 'message': 'Final evidence could not be confirmed.',
        'package_publication': 'published', 'package': {'sha256': 'a'*64, 'path': str(tmp_path/'app.zip')},
    })
    with pytest.raises(SystemExit) as stopped:
        extension_dev.main()
    assert stopped.value.code == 1
    output = capsys.readouterr().out
    assert 'Package publication: published' in output and 'a'*64 in output
    assert str(tmp_path/'app.zip') in output


@pytest.mark.parametrize('action', ['init', 'preview', 'schemas'])
def test_local_commands_do_not_prompt_for_credentials_or_require_url(monkeypatch, tmp_path, capsys, action):
    from tools import extension_dev
    import sys
    arguments = {'init': ['init', str(tmp_path/'new'), '--module-id', 'org.example.note', '--name', 'Note', '--route', '/note'],
                 'preview': ['preview', 'project'], 'schemas': ['schemas']}[action]
    monkeypatch.setattr(sys, 'argv', ['extension-dev', *arguments])
    monkeypatch.setattr(extension_dev.getpass, 'getpass', lambda *_: pytest.fail('Local commands need no credentials'))
    monkeypatch.setattr(preview, 'preview_project', lambda *_a, **_kw: None)
    from tools import application_scaffold
    monkeypatch.setattr(application_scaffold, 'create_project', lambda *_a, **_kw: {'status': 'created'})
    extension_dev.main()
    output = capsys.readouterr().out
    if action == 'schemas':
        assert 'module-manifest.v2' in output and 'application-extension.v1' in output
