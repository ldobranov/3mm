"""Previous and candidate wheels, seeded real data and no installed state."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.services.module_packages import validate_module_package
from tools import application_project as project
from tools import application_upgrade as upgrade

STARTER = Path(__file__).resolve().parents[2] / 'modules/application-starter'
FIXTURE = '''from three_mm_application_sdk import OperationContext
from starter_app.service import create_service

def actor(*permissions, key=None):
    return OperationContext('operator', 'fixture', user_id=7,
                            permission_ids=tuple(permissions), idempotency_key=key)

def seed(application):
    assert application.version == '1.0.0'
    service = create_service(application)
    saved = service.handle('save_note', {'text': 'private fixture row', 'revision': 0},
                           actor('note_write', key='a'*32))
    return {'saved': saved}

def verify(application, expectation):
    assert application.version == '1.1.0'
    service = create_service(application)
    assert service.handle('read_note', {}, actor('note_read')) == expectation['saved']
    assert service.handle('lookup_save', {'request_id': 'a'*32}, actor('note_write')) == {
        'status': 'found', 'revision': expectation['saved']['revision']}
'''


@pytest.fixture
def packages(tmp_path):
    source = tmp_path / 'project'
    for name, data in project.inputs(STARTER).items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    old_blob = project.build_package(source)
    old = validate_module_package(old_blob)
    for name in ('manifest.json', 'application-extension.json', 'compiled-ui.json'):
        path = source / name
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        value['version'] = '1.1.0'
        if name == 'application-extension.json':
            value['service']['artifact'] = 'service/starter_app-1.1.0-py3-none-any.whl'
            value['storage']['schema_revision'] = '0002'
        path.write_text(json.dumps(value), encoding='utf-8')
    migration = source / 'service/starter_app/migrations.py'
    code = migration.read_text(encoding='utf-8')
    migration.write_text(code + '''
def add_label(connection):
    connection.execute("ALTER TABLE note ADD COLUMN label TEXT NOT NULL DEFAULT ''")

def get_migrations():
    return [ApplicationMigration('0001', create_note), ApplicationMigration('0002', add_label)]
''', encoding='utf-8')
    fixture = source / 'tests/upgrade_fixture.py'
    fixture.write_text(FIXTURE, encoding='utf-8')
    return source, fixture, old_blob, old


def candidate(source):
    blob = project.build_package(source)
    return blob, validate_module_package(blob)


def run(packages, root):
    source, fixture, old_blob, old = packages
    blob, new = candidate(source)
    root.mkdir()
    with (root / 'local.log').open('w', encoding='utf-8') as log:
        return upgrade.run_packaged_upgrade(old_blob, old, blob, new, fixture=fixture,
            root=root, environment=dict(os.environ), log=log)


def test_exact_old_service_data_and_receipt_survive_candidate_schema_upgrade_and_reopen(packages, tmp_path):
    result = run(packages, tmp_path / 'run')
    assert result['status'] == 'passed'
    assert result['previous_version'] == '1.0.0' and result['candidate_version'] == '1.1.0'
    assert result['previous_revision'] == '0001' and result['target_revision'] == '0002'
    assert result['previous_revision_count'] == 1 and result['revision_count'] == 2
    assert result['rollback_probe_count'] == 1 and result['rollback_status'] == 'passed'
    assert result['domain_verified'] is result['integrity_verified'] is result['reopen_verified'] is True
    assert result['previous_package_sha256'] == packages[3].sha256
    assert result['fixture_sha256'] == hashlib.sha256(packages[1].read_bytes()).hexdigest()
    assert 'private fixture row' not in json.dumps(result)
    assert [path.name for path in (tmp_path / 'run').iterdir()] == ['local.log']


def test_same_schema_version_bump_does_not_claim_an_executed_rollback_probe(packages, tmp_path):
    source = packages[0]
    path = source / 'application-extension.json'
    definition = json.loads(path.read_text())
    definition['storage']['schema_revision'] = '0001'
    path.write_text(json.dumps(definition))
    migration = source / 'service/starter_app/migrations.py'
    migration.write_text(migration.read_text().split('def add_label', 1)[0])
    result = run(packages, tmp_path / 'run')
    assert result['domain_verified'] is True
    assert result['rollback_probe_count'] == 0 and result['rollback_status'] == 'not_applicable'


@pytest.mark.parametrize('change,reason', [
    (lambda s, f: f.write_text(FIXTURE.replace("== expectation['saved']", "== {'text': 'lost', 'revision': 99}")), 'fixture'),
    (lambda s, f: f.write_text(FIXTURE + '\nseed = None\n'), 'fixture'),
    (lambda s, f: f.write_text(FIXTURE.replace("return {'saved': saved}", "return {'secret': 'x' * 70000}")), 'fixture'),
    (lambda s, f: f.write_text(FIXTURE.replace("def verify(application, expectation):", "def verify(application, expectation):\n    return {'false': 'success'}\n\ndef old_verify(application, expectation):")), 'fixture'),
])
def test_bad_seed_or_domain_verification_never_returns_green_or_public_row_values(packages, tmp_path, change, reason):
    change(packages[0], packages[1])
    with pytest.raises(project.ProjectCheckError) as failure:
        run(packages, tmp_path / 'run')
    assert failure.value.stage == 'upgrade'
    assert 'private fixture row' not in str(failure.value) and 'Traceback' not in str(failure.value)
    assert [path.name for path in (tmp_path / 'run').iterdir()] == ['local.log']


def test_verifier_cannot_repair_lost_data_and_call_it_preserved(packages, tmp_path):
    fixture = packages[1]
    fixture.write_text(FIXTURE.replace("def verify(application, expectation):", '''def verify(application, expectation):
    with application.storage.transaction() as connection:
        connection.execute("UPDATE note SET text='rewritten during verify'")

def old_verify(application, expectation):'''))
    with pytest.raises(project.ProjectCheckError):
        run(packages, tmp_path / 'run')
    assert 'verification changed' in (tmp_path / 'run/local.log').read_text()


@pytest.mark.parametrize('change', [
    lambda code: code.replace("ApplicationMigration('0001', create_note)", "ApplicationMigration('renamed', create_note)"),
    lambda code: code.replace("connection.execute(\"ALTER TABLE note ADD COLUMN label TEXT NOT NULL DEFAULT ''\")",
        "connection.execute(\"UPDATE note SET text='must rollback'\")\n    connection.commit()"),
])
def test_history_rewrite_or_migration_transaction_escape_fails(packages, tmp_path, change):
    path = packages[0] / 'service/starter_app/migrations.py'
    path.write_text(change(path.read_text()))
    with pytest.raises(project.ProjectCheckError):
        run(packages, tmp_path / 'run')
    log = (tmp_path / 'run/local.log').read_text()
    assert 'revision sequence' in log or 'Interrupted upgrade changed committed' in log


def test_changed_artifact_or_missing_fixture_refuses_before_execution(packages, tmp_path, monkeypatch):
    source, fixture, old_blob, old = packages
    blob, new = candidate(source)
    monkeypatch.setattr(upgrade.subprocess, 'run', lambda *_a, **_k: pytest.fail('No child'))
    with pytest.raises(project.ProjectCheckError, match='validated artifact'):
        upgrade.run_packaged_upgrade(old_blob + b'changed', old, blob, new,
            fixture=fixture, root=tmp_path, environment={}, log=None)
    with pytest.raises(project.ProjectCheckError, match='regular local Python'):
        upgrade.run_packaged_upgrade(old_blob, old, blob, new,
            fixture=tmp_path/'missing.py', root=tmp_path, environment={}, log=None)


def test_different_module_or_nonincreasing_version_refuses_before_child(packages, tmp_path, monkeypatch):
    source, fixture, old_blob, old = packages
    blob, new = candidate(source)
    monkeypatch.setattr(upgrade.subprocess, 'run', lambda *_a, **_k: pytest.fail('No child'))
    for manifest in [new.manifest.model_copy(update={'module_id': 'org.example.other'}),
                     new.manifest.model_copy(update={'version': '1.0.0'})]:
        changed = SimpleNamespace(manifest=manifest)
        with pytest.raises(project.ProjectCheckError, match='same application'):
            upgrade.run_packaged_upgrade(old_blob, old, blob, changed,
                fixture=fixture, root=tmp_path, environment={}, log=None)


@pytest.mark.parametrize('old,new,expected', [
    ('1.0.0', '1.0.1', True), ('1.0.0', '1.0.0+other', False),
    ('1.0.0-beta.2', '1.0.0-beta.10', True), ('1.0.0-beta.10', '1.0.0-beta.2', False),
    ('1.0.0-beta', '1.0.0', True), ('1.0.0', '1.0.0-beta', False),
    ('1.0.0-1', '1.0.0-alpha', True), ('1.0.0-alpha', '1.0.0-alpha.1', True),
])
def test_version_order_is_semver_not_lexicographic_or_build_metadata(old, new, expected):
    assert upgrade._newer(old, new) is expected


def test_no_worker_evidence_cannot_be_success(packages, tmp_path, monkeypatch):
    monkeypatch.setattr(upgrade.subprocess, 'run', lambda *_a, **_k: SimpleNamespace(returncode=0))
    with pytest.raises(project.ProjectCheckError):
        run(packages, tmp_path / 'run')


def test_direct_worker_timeout_is_not_retried(packages, tmp_path, monkeypatch):
    fixture = packages[1]
    fixture.write_text('import time\ndef seed(application): time.sleep(60)\ndef verify(application, expectation): pass\n')
    monkeypatch.setattr(upgrade, 'TIMEOUT_SECONDS', 0.3)
    with pytest.raises(project.ProjectCheckError, match='time budget'):
        run(packages, tmp_path / 'run')
    assert [path.name for path in (tmp_path / 'run').iterdir()] == ['local.log']


@pytest.mark.parametrize('name', ['fixture', 'wheel'])
def test_pinned_fixture_and_service_files_cannot_change_between_children(packages, tmp_path, monkeypatch, name):
    real_run = upgrade.subprocess.run
    calls = []
    def altered(command, **options):
        calls.append(command)
        outcome = real_run(command, **options)
        request = json.loads(Path(command[-1]).read_text())
        if request['phase'] == 'seed':
            target = packages[1] if name == 'fixture' else Path(request['work']) / 'candidate.whl'
            target.write_bytes(target.read_bytes() + b'\nchanged after seed\n')
        return outcome
    monkeypatch.setattr(upgrade.subprocess, 'run', altered)
    with pytest.raises(project.ProjectCheckError, match='changed during verification'):
        run(packages, tmp_path / 'run')
    # A changed original fixture is checked after verification; a changed exact
    # candidate artifact is refused before candidate execution.
    assert len(calls) == (2 if name == 'fixture' else 1)
