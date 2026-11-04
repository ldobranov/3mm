"""Real packaged migration checks use only disposable developer data/processes."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest

from backend.services.module_packages import validate_module_package
from tools import application_migrations as migrations
from tools import application_project as project

STARTER = Path(__file__).resolve().parents[2] / 'modules/application-starter'
MULTI_STEP = '''from three_mm_application_sdk import ApplicationMigration

def first(connection):
    connection.execute('CREATE TABLE notes (value TEXT NOT NULL)')
    connection.execute("INSERT INTO notes VALUES ('private fixture row')")

def second(connection):
    connection.execute('ALTER TABLE notes ADD COLUMN enabled INTEGER DEFAULT 1')

def get_migrations():
    return [ApplicationMigration('0001', first), ApplicationMigration('0002', second)]
'''


@pytest.fixture
def source(tmp_path):
    root = tmp_path / 'project'
    for name, data in project.inputs(STARTER).items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


def package(source, migration_source=None, *, target='0001', entrypoint='starter_app.migrations:get_migrations'):
    if migration_source is not None:
        (source / 'service/starter_app/migrations.py').write_text(migration_source, encoding='utf-8')
    descriptor = json.loads((source / 'application-extension.json').read_text(encoding='utf-8-sig'))
    descriptor['storage'].update(schema_revision=target, migration_entrypoint=entrypoint)
    (source / 'application-extension.json').write_text(json.dumps(descriptor), encoding='utf-8')
    blob = project.build_package(source)
    return blob, validate_module_package(blob)


def run(blob, validated, root):
    root.mkdir()
    with (root / 'local.log').open('w', encoding='utf-8') as log:
        return migrations.run_packaged_migrations(blob, validated, root=root, environment=dict(os.environ), log=log)


def test_actual_official_packaged_migration_passes_and_owns_only_its_temporary_tree(source, tmp_path):
    blob, validated = package(source)
    result = run(blob, validated, tmp_path / 'run')
    assert result == {'status': 'passed', 'target_revision': '0001', 'revision_count': 1,
        'prefix_upgrade_count': 0, 'reopen_verified': True, 'integrity_verified': True,
        'rollback_verified': True, 'rollback_probe_count': 1,
        'scope': 'current packaged migrations on disposable data; not historic-data compatibility'}
    assert [path.name for path in (tmp_path / 'run').iterdir()] == ['local.log']


def test_multistep_exact_wheel_covers_prefix_upgrade_reopen_and_never_starts_service(source, tmp_path):
    # A service factory is irrelevant to migration verification and must not run.
    (source / 'service/starter_app/service.py').write_text("raise AssertionError('SERVICE MUST NOT START')\n")
    blob, validated = package(source, MULTI_STEP, target='0002')
    # Mutable source no longer supplies the migration: use the frozen wheel.
    (source / 'service/starter_app/migrations.py').write_text("raise AssertionError('SOURCE MUST NOT LOAD')\n")
    result = run(blob, validated, tmp_path / 'run')
    assert result['revision_count'] == 2 and result['prefix_upgrade_count'] == 1
    assert 'private fixture row' not in json.dumps(result)


@pytest.mark.parametrize('code,target,entrypoint', [
    ('get_migrations = 1', '0001', 'starter_app.migrations:get_migrations'),
    ('def get_migrations(): return []', '0001', 'starter_app.migrations:get_migrations'),
    ('def get_migrations(): return [object()]', '0001', 'starter_app.migrations:get_migrations'),
    (MULTI_STEP, '0003', 'starter_app.migrations:get_migrations'),
    (MULTI_STEP, '0001', 'starter_app.migrations:get_migrations'),
    (MULTI_STEP, '0002', 'starter_app.migrations:missing'),
    (MULTI_STEP.replace("ApplicationMigration('0002', second)", "ApplicationMigration('0001', second)"),
        '0001', 'starter_app.migrations:get_migrations'),
    (MULTI_STEP.replace("ApplicationMigration('0002', second)", "ApplicationMigration('BAD', second)"),
        '0002', 'starter_app.migrations:get_migrations'),
    (MULTI_STEP.replace("return [ApplicationMigration", 'raise RuntimeError("private error row"); return [ApplicationMigration'),
        '0002', 'starter_app.migrations:get_migrations'),
])
def test_invalid_factory_or_plan_fails_without_public_row_values_and_cleans_owned_tree(source, tmp_path, code, target, entrypoint):
    blob, validated = package(source, code, target=target, entrypoint=entrypoint)
    with pytest.raises(project.ProjectCheckError) as failure:
        run(blob, validated, tmp_path / 'run')
    assert failure.value.stage == 'migrations'
    assert 'private' not in str(failure.value) and 'Traceback' not in str(failure.value)
    assert [path.name for path in (tmp_path / 'run').iterdir()] == ['local.log']


def test_missing_migration_module_refuses_before_starting_process(source, tmp_path, monkeypatch):
    blob, validated = package(source, entrypoint='missing.module:get_migrations')
    monkeypatch.setattr(migrations.subprocess, 'run', lambda *_a, **_k: pytest.fail('process must not start'))
    with pytest.raises(project.ProjectCheckError, match='exact service wheel'):
        run(blob, validated, tmp_path / 'run')


def test_stateful_factory_cannot_introduce_untested_revisions_after_target(source, tmp_path):
    code = MULTI_STEP.split('def get_migrations():', 1)[0] + '''factory_calls = 0

def get_migrations():
    global factory_calls
    factory_calls += 1
    first_revision = ApplicationMigration('0001', first)
    if factory_calls == 1:
        return [first_revision]
    return [first_revision, ApplicationMigration('0002', second)]
'''
    blob, validated = package(source, code, target='0001')
    with pytest.raises(project.ProjectCheckError) as failure:
        run(blob, validated, tmp_path / 'run')
    assert failure.value.stage == 'migrations'
    assert 'Migration revision sequence changed between factory calls' in (tmp_path / 'run/local.log').read_text()
    assert [path.name for path in (tmp_path / 'run').iterdir()] == ['local.log']


def test_migration_failure_uses_real_sdk_rollback_and_retains_previous_revision_and_data(source, tmp_path):
    from three_mm_application_sdk import ApplicationStorage
    import zipfile
    import io

    # Execute only this worker routine directly so its disposable failed database
    # remains inspectable; the public process controller cleans its owned tree.
    code = MULTI_STEP.replace("connection.execute('ALTER TABLE notes ADD COLUMN enabled INTEGER DEFAULT 1')",
        "connection.execute(\"INSERT INTO notes VALUES ('rolled back')\")\n    raise RuntimeError('fixture migration failure')")
    blob, validated = package(source, code, target='0002')
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        wheel = archive.read(validated.application_extension.service.artifact)
    wheel_path = tmp_path / 'application.whl'
    wheel_path.write_bytes(wheel)
    # A separate worker preserves evidence without importing its package into pytest.
    owned, result = tmp_path / 'owned', tmp_path / 'result.json'
    owned.mkdir()
    request = tmp_path / 'request.json'
    request.write_text(json.dumps({'wheel': str(wheel_path), 'work': str(owned),
        'entrypoint': 'starter_app.migrations:get_migrations', 'target': '0002', 'result': str(result)}))
    child = subprocess.run([os.sys.executable, '-I', '-B', '-c', migrations._LAUNCHER, str(project.REPOSITORY),
        '--worker', str(request)], capture_output=True, text=True, timeout=20)
    assert child.returncode != 0 and not result.exists()
    storage = ApplicationStorage(owned / 'clean')
    assert storage.status()['revision'] == '0001'
    with sqlite3.connect(storage.database_path) as connection:
        assert connection.execute('SELECT value FROM notes').fetchall() == [('private fixture row',)]
        assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)


def test_relational_profile_and_changed_package_refuse_before_child(source, tmp_path, monkeypatch):
    blob, validated = package(source)
    monkeypatch.setattr(migrations.subprocess, 'run', lambda *_a, **_k: pytest.fail('process must not start'))
    relational = SimpleNamespace(application_extension=SimpleNamespace(storage=SimpleNamespace(relational=object())))
    with pytest.raises(project.ProjectCheckError, match='relational'):
        run(blob, relational, tmp_path / 'relational')
    with pytest.raises(project.ProjectCheckError, match='validated artifact'):
        run(blob + b'changed', validated, tmp_path / 'changed')


def test_wheel_digest_mismatch_refuses_before_child(source, tmp_path, monkeypatch):
    blob, validated = package(source)
    validated = SimpleNamespace(sha256=validated.sha256,
        application_extension=validated.application_extension.model_copy(update={
            'service': validated.application_extension.service.model_copy(update={'artifact_sha256': 'f' * 64})}))
    monkeypatch.setattr(migrations.subprocess, 'run', lambda *_a, **_k: pytest.fail('process must not start'))
    with pytest.raises(project.ProjectCheckError, match='service artifact'):
        run(blob, validated, tmp_path / 'run')


def test_timeout_is_bounded_real_child_failure_and_never_retried(source, tmp_path, monkeypatch):
    code = 'import time\ndef get_migrations():\n    time.sleep(60)\n'
    blob, validated = package(source, code)
    monkeypatch.setattr(migrations, 'TIMEOUT_SECONDS', 0.5)
    with pytest.raises(project.ProjectCheckError, match='time budget'):
        run(blob, validated, tmp_path / 'run')
    assert [path.name for path in (tmp_path / 'run').iterdir()] == ['local.log']


def test_worker_cannot_report_success_with_invalid_or_missing_result(source, tmp_path, monkeypatch):
    blob, validated = package(source)
    monkeypatch.setattr(migrations.subprocess, 'run', lambda *_a, **_k: SimpleNamespace(returncode=0))
    with pytest.raises(project.ProjectCheckError) as failure:
        run(blob, validated, tmp_path / 'run')
    assert failure.value.stage == 'migrations'


def test_worker_declared_migration_budget_is_finite(source, tmp_path):
    code = ('from three_mm_application_sdk import ApplicationMigration\n'
        'def get_migrations():\n    return [ApplicationMigration(str(i), lambda c: None) for i in range(33)]\n')
    blob, validated = package(source, code, target='0')
    with pytest.raises(project.ProjectCheckError):
        run(blob, validated, tmp_path / 'run')


@pytest.mark.parametrize('transaction_escape', [
    "connection.commit()",
    "connection.executescript(\"INSERT INTO notes VALUES ('escaped')\")",
])
def test_migration_cannot_escape_sdk_rollback_after_callback_returns(source, tmp_path, transaction_escape):
    code = MULTI_STEP.replace("connection.execute('ALTER TABLE notes ADD COLUMN enabled INTEGER DEFAULT 1')",
        "connection.execute(\"INSERT INTO notes VALUES ('must roll back')\")\n    " + transaction_escape)
    blob, validated = package(source, code, target='0002')
    with pytest.raises(project.ProjectCheckError):
        run(blob, validated, tmp_path / 'run')
    assert 'Interrupted migration changed committed' in (tmp_path / 'run/local.log').read_text()
