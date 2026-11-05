"""Exercise package review with real immutable ZIPs and no executable side effects."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

from tools import application_project, extension_dev
from tools.application_package_review import PackageReviewError, compare_application_packages


STARTER = Path(__file__).resolve().parents[2] / 'modules/application-starter'


@pytest.fixture
def packages(tmp_path):
    project = tmp_path / 'project'
    for name, contents in application_project.inputs(STARTER).items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)

    def edit(name, change):
        path = project / name
        value = json.loads(path.read_bytes())
        change(value)
        path.write_text(json.dumps(value), encoding='utf-8')

    def write(name):
        path = tmp_path / name
        path.write_bytes(application_project.build_package(project))
        return path

    old = write('old.zip')
    return project, old, edit, write


def _version(edit, version):
    for name in ('manifest.json', 'application-extension.json', 'compiled-ui.json'):
        def update(value):
            value['version'] = version
            if 'service' in value:
                value['service']['artifact'] = f'service/starter_app-{version}-py3-none-any.whl'
        edit(name, update)


def test_compare_reports_exact_artifacts_and_declaration_changes_without_values(packages):
    project, old, edit, write = packages
    _version(edit, '1.1.0')

    def declarations(app):
        app['permissions'][1]['permission_id'] = 'note_review'
        for operation in app['operations']:
            if operation.get('required_permission') == 'note_write':
                operation['required_permission'] = 'note_review'
        app['storage']['schema_revision'] = '0002'
        app['command_bindings'][0]['max_ttl_seconds'] = 5

    edit('application-extension.json', declarations)
    config_value = 'dev_' + 'f' * 32
    edit('manifest.json', lambda manifest: manifest['configuration_defaults'].update(RESOURCE_DEVICE_ID=config_value))
    # A valid artifact for static inspection, never a service to execute.
    (project / 'service/starter_app/service.py').write_text('raise RuntimeError("must not execute")\n', encoding='utf-8')
    new = write('candidate.zip')
    result = compare_application_packages(old, new)
    assert result == compare_application_packages(old, new)
    assert result['status'] == 'compared'
    assert result['previous']['sha256'] == hashlib.sha256(old.read_bytes()).hexdigest()
    assert result['candidate']['sha256'] == hashlib.sha256(new.read_bytes()).hexdigest()
    assert (result['previous']['schema_revision'], result['candidate']['schema_revision']) == ('0001', '0002')
    assert result['service_artifact_changed'] is True
    assert result['changes']['manifest']['fields'] == ['configuration_defaults']
    application = result['changes']['application']
    assert application['fields'] == ['command_bindings', 'operations', 'permissions', 'storage']
    assert application['items']['permissions'] == {'added': ['note_review'], 'removed': ['note_write'], 'changed': {}}
    assert application['items']['operations']['changed'] == {'lookup_save': ['required_permission'], 'save_note': ['required_permission']}
    assert application['items']['command_bindings']['changed'] == {'resource': ['max_ttl_seconds']}
    assert result['executed_checks'] == 'not_run' and result['installation'] == 'not_requested'
    assert config_value not in json.dumps(result) and str(project) not in json.dumps(result)


def test_version_and_service_bytes_are_distinct_from_declarations(packages):
    _, old, edit, write = packages
    assert compare_application_packages(old, old)['same_archive'] is True
    _version(edit, '1.0.1')
    result = compare_application_packages(old, write('candidate.zip'))
    assert result['same_archive'] is False and result['service_artifact_changed'] is True
    assert result['changes'] == {}


@pytest.mark.parametrize('case,reason', [
    ('same_version', 'reuse the same application version'),
    ('different_module', 'same application identity'),
    ('invalid', 'fails this checkout'),
    ('incompatible', 'fails this checkout'),
])
def test_compare_refuses_unsafe_pairs(packages, tmp_path, case, reason):
    _, old, edit, write = packages
    if case == 'invalid':
        new = tmp_path / 'invalid.zip'
        new.write_bytes(b'private input, not a ZIP')
    else:
        if case == 'same_version':
            edit('manifest.json', lambda manifest: manifest.update(description='different bytes'))
        elif case == 'incompatible':
            _version(edit, '1.0.1')
            edit('manifest.json', lambda manifest: manifest['compatibility'].update(core='>=99.0.0'))
        else:
            for name in ('manifest.json', 'application-extension.json', 'compiled-ui.json'):
                edit(name, lambda descriptor: descriptor.update(module_id='org.example.other'))
        new = write('candidate.zip')
    with pytest.raises(PackageReviewError, match=reason):
        compare_application_packages(old, new)


def test_compare_cli_is_local_even_when_url_is_supplied(packages, monkeypatch, capsys):
    _, old, edit, write = packages
    _version(edit, '1.0.1')
    new = write('candidate.zip')
    monkeypatch.setattr(extension_dev.getpass, 'getpass', lambda *_: pytest.fail('Unexpected credentials prompt'))
    monkeypatch.setattr(extension_dev, 'DevelopmentClient', lambda *_: pytest.fail('Unexpected remote client'))
    monkeypatch.setattr(sys, 'argv', ['extension-dev', '--url', 'http://127.0.0.1:18887',
                                      'compare', str(old), str(new), '--json'])
    extension_dev.main()
    assert json.loads(capsys.readouterr().out)['status'] == 'compared'


def test_compare_cli_refusal_does_not_echo_validation_details(packages, monkeypatch, capsys):
    _, old, edit, write = packages
    edit('manifest.json', lambda manifest: manifest['permissions'].append('private-invalid-identifier'))
    new = write('invalid.zip')
    monkeypatch.setattr(sys, 'argv', ['extension-dev', 'compare', str(old), str(new), '--json'])
    with pytest.raises(SystemExit) as stopped:
        extension_dev.main()
    assert stopped.value.code == 1
    result = capsys.readouterr()
    assert result.err == ''
    assert json.loads(result.out)['status'] == 'failed'
    assert 'private-invalid-identifier' not in result.out
