"""Authoring runner guards; actual starter/compiler/Core integration is separate."""
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import zipfile

import pytest

from tools import application_project as project
from backend.services.module_packages import validate_module_package

ROOT = Path(__file__).resolve().parents[2]
STARTER = ROOT/'modules/application-starter'


@pytest.fixture
def source(tmp_path):
    root = tmp_path/'project'
    for name, data in project.inputs(STARTER).items():
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def change_config(root, change):
    value = json.loads((root/'development.json').read_text())
    change(value)
    (root/'development.json').write_text(json.dumps(value))


def test_standard_package_is_reproducible_validated_and_excludes_tests(source):
    blob = project.build_package(source)
    assert blob == project.build_package(source)
    package = validate_module_package(blob)
    assert package.application_extension.optional_resources == ('command:resource',)
    assert package.application_extension.storage.schema_revision == '0001'
    assert package.application_extension.routes[0].administration_actions == ()
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        assert not any(n.startswith(('tests/', 'development')) for n in archive.namelist())
        wheel = archive.read(package.application_extension.service.artifact)
    with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
        assert 'starter_app/service.py' in archive.namelist()
        assert not any(n.startswith(('backend/', 'tools/')) for n in archive.namelist())


@pytest.mark.parametrize('name', ['../outside.json', '/absolute.json', 'tests\\bad.py'])
def test_declared_paths_cannot_escape_project(source, name):
    change_config(source, lambda c: c.update(ui_tests=name))
    with pytest.raises(project.ProjectCheckError):
        project.configuration(source)


def test_required_denial_scenarios_cannot_be_omitted(source):
    change_config(source, lambda c: c['scenarios'].pop('revoked_access'))
    with pytest.raises(project.ProjectCheckError, match='denial'):
        project.configuration(source)


def test_private_runtime_import_is_an_authoring_error(source):
    path = source/'service/starter_app/service.py'
    path.write_text('from backend.services import module_packages\n')
    with pytest.raises(project.ProjectCheckError, match='public SDK'):
        project.build_package(source)


def fake_pipeline(monkeypatch, tmp_path, *, skipped=False, missing=False, changed=False, fail_stage=None):
    frontend = tmp_path/'frontend'
    for name in ['node_modules/vitest/vitest.mjs', 'node_modules/vue-tsc/bin/vue-tsc.js']:
        target = frontend/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('fixture')
    monkeypatch.setenv('COMPILED_UI_NODE', 'test-node')
    calls = []
    def run(command, *, cwd, environment, stage, log, timeout=180):
        calls.append(stage)
        if stage == fail_stage:
            raise project.ProjectCheckError(stage, 'Deliberate failure')
        if stage == 'python':
            names = ['test_missing_permission', 'test_revoked_access', 'test_provider_unavailable']
            if missing: names.pop()
            cases = ''.join('<testcase classname="tests.test_service" name="'+n+'">'+
                ('<skipped/>' if skipped else '')+'</testcase>' for n in names)
            output = next(c.split('=', 1)[1] for c in command if c.startswith('--junitxml='))
            Path(output).write_text('<testsuites>'+cases+'</testsuites>')
        if stage == 'ui':
            output = next(c.split('=', 1)[1] for c in command if c.startswith('--outputFile='))
            Path(output).write_text('<testsuites><testcase name="ui"/></testsuites>')
        if changed:
            (cwd/'source/frontend/Notes.vue').write_text('changed by check')
    monkeypatch.setattr(project, 'run_check', run)
    from backend.services import compiled_ui
    def compile_(*_):
        path = tmp_path/'compiler-result'
        path.mkdir(exist_ok=True)
        (path/'build-toolchain.json').write_text('{}')
        return SimpleNamespace(built_ui_sha256='f'*64, path=path)
    monkeypatch.setattr(compiled_ui, 'compile_ui_package', compile_)
    from tools import application_migrations
    monkeypatch.setattr(application_migrations, 'run_packaged_migrations', lambda *_a, **_kw: {
        'status': 'passed', 'target_revision': '0001', 'revision_count': 1,
        'prefix_upgrade_count': 0, 'reopen_verified': True, 'integrity_verified': True,
        'rollback_verified': True, 'rollback_probe_count': 1,
        'scope': 'controller double; real packaged migrations verified separately',
    })
    return frontend, calls


@pytest.mark.parametrize('problem,stage', [('skipped', 'python'), ('missing', 'scenarios'),
    ('changed', 'source'), ('ui_failure', 'ui'), ('type_failure', 'typecheck')])
def test_incomplete_or_changed_checks_never_publish_a_candidate(source, tmp_path, monkeypatch, problem, stage):
    frontend, _ = fake_pipeline(monkeypatch, tmp_path, skipped=problem=='skipped', missing=problem=='missing',
        changed=problem=='changed', fail_stage='ui' if problem=='ui_failure' else 'typecheck' if problem=='type_failure' else None)
    output = tmp_path/'candidate.zip'
    result = project.check_project(source, output, frontend=frontend)
    assert result['status'] == 'failed' and result['stage'] == stage
    assert not output.exists()
    assert output.with_suffix('.report.json').is_file()
    assert result['installation'] == 'not_requested'


def test_success_has_exact_package_review_and_never_overwrites(source, tmp_path, monkeypatch):
    frontend, calls = fake_pipeline(monkeypatch, tmp_path)
    output = tmp_path/'candidate.zip'
    result = project.check_project(source, output, frontend=frontend)
    assert result['status'] == 'passed'
    assert calls == ['python', 'ui', 'typecheck']
    assert result['review']['human_permissions'] == ['note_read', 'note_write']
    assert result['review']['optional_resources'] == ['command:resource']
    assert result['review']['identity']['sdk_version'] == '1.3'
    assert result['review']['identity']['compatibility']['core'] == '>=0.3.7'
    write = next(item for item in result['review']['operations'] if item['operation_id'] == 'save_note')
    assert write['required_permission'] == 'note_write' and write['idempotency'] == 'required'
    binding = result['review']['resource_bindings']['command_bindings'][0]
    assert binding['target_device_config_key'] == 'RESOURCE_DEVICE_ID'
    assert binding['capability_id'] == 'gpio.digital.control' and binding['contract_version'] == '1.0'
    assert result['review']['storage']['schema_revision'] == '0001'
    assert result['semantic_validation']['status'] == 'passed'
    assert result['migrations']['status'] == 'passed'
    assert result['migrations']['target_revision'] == result['review']['storage']['schema_revision']
    assert result['stages'].index('packaged_migrations') < result['stages'].index('python_and_denial_scenarios')
    assert 'not installed authority' in result['semantic_validation']['scope']
    assert validate_module_package(output.read_bytes()).sha256 == result['package']['sha256']
    assert result['live_acceptance'] == 'not_performed'
    assert result['package_publication'] == 'published'
    assert result['evidence'] == {'report': 'published', 'log': 'published'}
    assert json.loads(output.with_suffix('.report.json').read_text()) == result
    with pytest.raises(project.ProjectCheckError, match='already exists'):
        project.check_project(source, output, frontend=frontend)


def test_packaged_migration_refusal_stops_before_project_tests_and_zip(source, tmp_path, monkeypatch):
    frontend, calls = fake_pipeline(monkeypatch, tmp_path)
    from tools import application_migrations
    def refuse(blob, validated, *, root, environment, log):
        assert validate_module_package(blob).sha256 == validated.sha256
        assert root.is_dir() and root != source
        assert 'PYTHONPATH' in environment
        log.write('Local migration test refusal\n')
        raise project.ProjectCheckError('migrations', 'Packaged migrations did not pass.')
    monkeypatch.setattr(application_migrations, 'run_packaged_migrations', refuse)
    output = tmp_path/'migration-failure.zip'
    result = project.check_project(source, output, frontend=frontend)
    assert result['status'] == 'failed' and result['stage'] == 'migrations'
    assert calls == [] and not output.exists() and result['package_publication'] == 'not_published'
    assert result['review']['storage']['schema_revision'] == '0001'
    assert json.loads(output.with_suffix('.report.json').read_text())['stage'] == 'migrations'
    assert 'Local migration test refusal' in output.with_suffix('.checks.log').read_text()


def test_source_symlink_is_refused(source, tmp_path):
    target = source/'service/starter_app/linked.py'
    try:
        target.symlink_to(tmp_path/'elsewhere.py')
    except OSError:
        pytest.skip('Environment does not permit creating symbolic links')
    with pytest.raises(project.ProjectCheckError, match='symbolic'):
        project.inputs(source)


def test_check_cli_needs_no_server_or_credentials(monkeypatch, capsys, tmp_path):
    from tools import extension_dev
    import sys
    monkeypatch.setattr(sys, 'argv', ['extension-dev', 'check', 'project', '--output', str(tmp_path/'new.zip'), '--json'])
    monkeypatch.setattr(extension_dev.getpass, 'getpass', lambda *_: pytest.fail('Local checks must not request credentials'))
    monkeypatch.setattr(project, 'check_project', lambda *_args, **_kw: {
        'status': 'failed', 'stage': 'project', 'message': 'test refusal', 'installation': 'not_requested'})
    with pytest.raises(SystemExit) as error:
        extension_dev.main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)['installation'] == 'not_requested'


def test_compiler_failure_reports_its_phase_without_echoing_private_error(source, tmp_path, monkeypatch):
    frontend, _ = fake_pipeline(monkeypatch, tmp_path)
    from backend.services import compiled_ui
    def fail(*_):
        raise RuntimeError('private compiler content must stay local')
    monkeypatch.setattr(compiled_ui, 'compile_ui_package', fail)
    result = project.check_project(source, tmp_path/'failed.zip', frontend=frontend)
    assert result['stage'] == 'ui_compilation' and result['status'] == 'failed'
    assert 'private compiler content' not in json.dumps(result)
    assert not (tmp_path/'failed.zip').exists()


@pytest.mark.parametrize('stage', ['python', 'ui'])
@pytest.mark.parametrize('fault', ['missing', 'malformed', 'empty', 'skipped',
                                 'root_error', 'suite_error', 'error_node', 'invalid_count', 'zero_count'])
def test_incomplete_result_evidence_keeps_its_phase_and_never_publishes(
    source, tmp_path, monkeypatch, stage, fault,
):
    frontend, _ = fake_pipeline(monkeypatch, tmp_path)
    clean_run = project.run_check
    def run(command, **kwargs):
        clean_run(command, **kwargs)
        if kwargs['stage'] != stage:
            return
        import xml.etree.ElementTree as ET
        prefix = '--junitxml=' if stage == 'python' else '--outputFile='
        path = Path(next(item.split('=', 1)[1] for item in command if item.startswith(prefix)))
        if fault == 'missing':
            path.unlink()
        elif fault == 'malformed':
            path.write_text('<broken')
        elif fault == 'empty':
            path.write_text('<testsuites/>')
        else:
            tree = ET.parse(path)
            root = tree.getroot()
            if fault == 'skipped':
                ET.SubElement(next(root.iter('testcase')), 'skipped')
            elif fault == 'root_error':
                root.set('errors', '1')
            elif fault == 'suite_error':
                ET.SubElement(root, 'testsuite', {'errors': '1'})
            elif fault == 'error_node':
                ET.SubElement(root, 'error')
            elif fault == 'zero_count':
                root.set('tests', '0')
            else:
                root.set('failures', 'unknown')
            tree.write(path)
    monkeypatch.setattr(project, 'run_check', run)
    output = tmp_path/'bad-evidence.zip'
    result = project.check_project(source, output, frontend=frontend)
    assert result['status'] == 'failed' and result['stage'] == stage
    assert result['package_publication'] == 'not_published' and not output.exists()
    assert json.loads(Path(result['report']).read_text())['stage'] == stage
    assert Path(result['log']).is_file()


@pytest.mark.parametrize('failure', ['configuration', 'toolchain'])
def test_early_project_or_toolchain_failure_has_retained_evidence(source, tmp_path, monkeypatch, failure):
    frontend, calls = fake_pipeline(monkeypatch, tmp_path)
    if failure == 'configuration':
        (source/'development.json').write_text('{broken')
    else:
        frontend = tmp_path/'missing-frontend'
    output = tmp_path/'early.zip'
    result = project.check_project(source, output, frontend=frontend)
    assert result['status'] == 'failed' and result['stage'] == ('project' if failure == 'configuration' else 'toolchain')
    assert not output.exists() and calls == []
    assert json.loads(Path(result['report']).read_text())['status'] == 'failed'
    assert Path(result['log']).is_file()


def test_actual_pytest_scenarios_keep_project_identities_inside_the_repository(source, tmp_path, monkeypatch):
    """Real nested pytest, not a synthetic assumption about JUnit classnames."""
    real_run = project.run_check
    frontend, _ = fake_pipeline(monkeypatch, tmp_path)
    fake_run = project.run_check
    observed = []
    def run(command, **kwargs):
        if kwargs['stage'] == 'python':
            real_run(command, **kwargs)
            evidence = Path(next(item.split('=', 1)[1] for item in command if item.startswith('--junitxml=')))
            observed.extend((item.get('classname'), item.get('name')) for item in project.read_junit(evidence, 'python'))
        else:
            fake_run(command, **kwargs)
    monkeypatch.setattr(project, 'run_check', run)
    (ROOT/'.runtime').mkdir(exist_ok=True)  # A clean checkout has no ignored runtime directory.
    with tempfile.TemporaryDirectory(prefix='cap21-scenario-regression-', dir=ROOT/'.runtime') as owned:
        result = project.check_project(source, Path(owned)/'candidate.zip', frontend=frontend)
        assert result['status'] == 'passed', {'result': result, 'observed': observed}
        assert result['python_passed'] == 6
        assert all(('tests.test_service', 'test_'+name) in observed for name in project.SCENARIOS)


@pytest.mark.parametrize('target_name', ['candidate.zip', 'candidate.report.json', 'candidate.checks.log'])
def test_output_race_never_overwrites_or_removes_the_other_file(source, tmp_path, monkeypatch, target_name):
    frontend, _ = fake_pipeline(monkeypatch, tmp_path)
    output = tmp_path/'candidate.zip'
    original_link = os.link
    target = tmp_path/target_name
    def collide(source_path, destination):
        if Path(destination) == target:
            target.write_bytes(b'other owner data')
        return original_link(source_path, destination)
    monkeypatch.setattr(project.os, 'link', collide)
    result = project.check_project(source, output, frontend=frontend)
    assert result['status'] == 'failed' and result['stage'] == 'output'
    assert result['package_publication'] == 'not_published'
    assert target.read_bytes() == b'other owner data'
    if target != output:
        assert not output.exists()
    if target_name == 'candidate.zip':
        assert json.loads(Path(result['report']).read_text())['status'] == 'failed'


def test_evidence_must_be_prepared_before_a_zip_is_published(source, tmp_path, monkeypatch):
    frontend, _ = fake_pipeline(monkeypatch, tmp_path)
    def fail_report(*_):
        raise OSError('private output failure')
    monkeypatch.setattr(project, 'write_report', fail_report)
    output = tmp_path/'candidate.zip'
    result = project.check_project(source, output, frontend=frontend)
    assert result['status'] == 'failed' and result['stage'] == 'output'
    assert result['package_publication'] == 'not_published' and not output.exists()
    assert 'private output failure' not in json.dumps(result)
    assert Path(result['log']).is_file()


def test_zip_publication_io_failure_is_not_a_claim_that_no_file_was_created(source, tmp_path, monkeypatch):
    frontend, _ = fake_pipeline(monkeypatch, tmp_path)
    output = tmp_path/'candidate.zip'
    original_link = os.link
    def fail_zip(source_path, destination):
        if Path(destination) == output:
            raise OSError('unconfirmed filesystem outcome')
        return original_link(source_path, destination)
    monkeypatch.setattr(project.os, 'link', fail_zip)
    result = project.check_project(source, output, frontend=frontend)
    assert result['status'] == 'failed' and result['stage'] == 'output'
    assert result['package_publication'] == 'unconfirmed'
    assert json.loads(Path(result['report']).read_text())['package_publication'] == 'unconfirmed'


@pytest.mark.parametrize('name', ['candidate.report.json', 'candidate.checks.log'])
@pytest.mark.parametrize('replacement', [False, True])
def test_replaced_evidence_is_neither_overwritten_nor_claimed_confirmed(source, tmp_path, monkeypatch, name, replacement):
    frontend, _ = fake_pipeline(monkeypatch, tmp_path)
    output = tmp_path/'candidate.zip'
    target = tmp_path/name
    original_link = os.link
    def replace_on_package(source_path, destination):
        if Path(destination) == output:
            target.unlink()
            if replacement:
                target.write_bytes(b'new owner evidence')
        return original_link(source_path, destination)
    monkeypatch.setattr(project.os, 'link', replace_on_package)
    result = project.check_project(source, output, frontend=frontend)
    assert result['status'] == 'failed' and result['stage'] == 'output'
    assert result['package_publication'] == 'published'
    assert result['evidence']['report' if name.endswith('json') else 'log'] == 'unconfirmed'
    if replacement:
        assert target.read_bytes() == b'new owner evidence'
    else:
        assert not target.exists()


@pytest.mark.parametrize('persistent', [False, True])
def test_late_report_failure_retains_exact_published_package_identity(source, tmp_path, monkeypatch, persistent):
    frontend, _ = fake_pipeline(monkeypatch, tmp_path)
    original_report = project.write_report
    calls = []
    def fail_after_zip(path, summary):
        calls.append(summary['package_publication'])
        if len(calls) == 2 or persistent and len(calls) > 2:
            raise OSError('private report write failure')
        return original_report(path, summary)
    monkeypatch.setattr(project, 'write_report', fail_after_zip)
    output = tmp_path/'candidate.zip'
    result = project.check_project(source, output, frontend=frontend)
    assert result['status'] == 'failed' and result['stage'] == 'output'
    assert result['package_publication'] == 'published'
    assert 'was published' in result['message']
    assert validate_module_package(output.read_bytes()).sha256 == result['package']['sha256']
    assert result['evidence']['report'] == ('unconfirmed' if persistent else 'published')
    if not persistent:
        assert json.loads(Path(result['report']).read_text())['status'] == 'failed'
