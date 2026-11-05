"""Explicit local generation and upgrade selection never imply remote approval."""
import json
from pathlib import Path
import sys

import pytest

from tools import application_project, extension_dev


@pytest.mark.parametrize('explicit', [False, True])
def test_generation_cli_passes_only_explicit_local_selection(monkeypatch, capsys, explicit):
    from tools import application_client
    output = Path('source/frontend/client.generated.ts')
    monkeypatch.setattr(application_project, 'configuration', lambda _: {'generated_client': str(output).replace('\\', '/')})
    seen = []
    def generate(project, selected, *, replace):
        seen.append((project, selected, replace))
        return {'status': 'created', 'installation': 'not_requested'}
    monkeypatch.setattr(application_client, 'generate_client', generate)
    monkeypatch.setattr(extension_dev.getpass, 'getpass', lambda *_: pytest.fail('No credentials'))
    monkeypatch.setattr(extension_dev, 'DevelopmentClient', lambda *_: pytest.fail('No Core API'))
    arguments = ['extension-dev', 'generate-client', 'project']
    if explicit:
        arguments.extend(['--output', str(output), '--replace'])
    monkeypatch.setattr(sys, 'argv', arguments)
    extension_dev.main()
    assert seen == [(Path('project'), output, explicit)]
    assert json.loads(capsys.readouterr().out)['installation'] == 'not_requested'


def test_generation_without_declared_destination_fails_without_calling_generator(monkeypatch, capsys):
    from tools import application_client
    monkeypatch.setattr(application_project, 'configuration', lambda _: {})
    monkeypatch.setattr(application_client, 'generate_client', lambda *_a, **_kw: pytest.fail('No destination'))
    monkeypatch.setattr(sys, 'argv', ['extension-dev', 'generate-client', 'project'])
    with pytest.raises(SystemExit) as stopped:
        extension_dev.main()
    assert stopped.value.code == 1
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'failed' and result['stage'] == 'client'


def test_check_passes_an_explicit_previous_archive_without_remote_action(monkeypatch, tmp_path, capsys):
    previous = tmp_path/'previous.zip'
    output = tmp_path/'candidate.zip'
    seen = []
    def check(project, selected, *, frontend, previous_archive):
        seen.append((project, selected, frontend, previous_archive))
        return {'status': 'failed', 'stage': 'upgrade', 'message': 'fixture refusal', 'installation': 'not_requested'}
    monkeypatch.setattr(application_project, 'check_project', check)
    monkeypatch.setattr(extension_dev.getpass, 'getpass', lambda *_: pytest.fail('No credentials'))
    monkeypatch.setattr(extension_dev, 'DevelopmentClient', lambda *_: pytest.fail('No API'))
    monkeypatch.setattr(sys, 'argv', ['extension-dev', 'check', 'project', '--output', str(output),
        '--previous-archive', str(previous), '--json'])
    with pytest.raises(SystemExit) as stopped:
        extension_dev.main()
    assert stopped.value.code == 1
    assert seen == [(Path('project'), output, None, previous)]
    assert json.loads(capsys.readouterr().out)['stage'] == 'upgrade'
