"""The catalog is a local JSON inspection, not a check, approval or remote action."""
import json
from pathlib import Path
import sys

import pytest

from tools import extension_dev
from tools.application_project import ProjectCheckError


@pytest.mark.parametrize('project', [None, 'local-project'])
def test_catalog_cli_returns_json_without_credentials_or_remote_actions(monkeypatch, capsys, project):
    from tools import application_catalog
    seen = []
    expected = {'catalog_version': 1, 'scope': 'local declarations, not approval'}

    def inspect(path):
        seen.append(path)
        return expected

    monkeypatch.setattr(application_catalog, 'application_catalog', inspect)
    monkeypatch.setattr(extension_dev.getpass, 'getpass', lambda *_: pytest.fail('No credentials'))
    monkeypatch.setattr(extension_dev, 'DevelopmentClient', lambda *_: pytest.fail('No API client'))
    monkeypatch.setattr(sys, 'argv', ['extension-dev', 'catalog', *([project] if project else [])])
    extension_dev.main()
    assert seen == [Path(project) if project else None]
    assert json.loads(capsys.readouterr().out) == expected


@pytest.mark.parametrize('error,stage,message', [
    (ProjectCheckError('catalog', 'Public contract format is unsupported.'), 'catalog',
     'Public contract format is unsupported.'),
    (ProjectCheckError('manifest', 'Project declarations are invalid.'), 'manifest',
     'Project declarations are invalid.'),
    (OSError('private-path-or-content'), 'catalog', 'Catalog inputs are invalid or unavailable.'),
])
def test_catalog_failure_is_nonzero_json_not_a_traceback_or_check_pass(monkeypatch, capsys, error, stage, message):
    from tools import application_catalog

    def fail(_):
        raise error

    monkeypatch.setattr(application_catalog, 'application_catalog', fail)
    monkeypatch.setattr(sys, 'argv', ['extension-dev', 'catalog', 'local-project'])
    with pytest.raises(SystemExit) as stopped:
        extension_dev.main()
    assert stopped.value.code == 1
    assert json.loads(capsys.readouterr().out) == {
        'status': 'failed', 'stage': stage, 'message': message, 'installation': 'not_requested',
    }
