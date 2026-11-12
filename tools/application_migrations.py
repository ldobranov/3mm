"""Bounded, disposable checks of a trusted application's packaged migrations.

This is developer code execution, not hostile-code isolation, an installed host
or proof that a previous release's real business data is preserved.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import importlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import traceback
import zipfile

from tools.application_project import ProjectCheckError, REPOSITORY

TIMEOUT_SECONDS = 60
MAX_MIGRATIONS = 32
MAX_DATABASE_BYTES = 16 * 1024 * 1024
MAX_DUMP_BYTES = 32 * 1024 * 1024
_LAUNCHER = ('import sys; sys.path.insert(0, sys.argv[1]); '
             'from tools.application_migrations import _main; '
             'raise SystemExit(_main(sys.argv[2:]))')


def _plan(factory, expected_revisions=None):
    from packages.application_sdk import ApplicationMigration

    migrations = factory()
    if (not isinstance(migrations, (list, tuple)) or not 1 <= len(migrations) <= MAX_MIGRATIONS
            or not all(isinstance(item, ApplicationMigration) and callable(item.apply) for item in migrations)):
        raise ValueError('Migration factory must return a bounded sequence of public migrations')
    if expected_revisions is not None and [item.revision for item in migrations] != expected_revisions:
        raise ValueError('Migration revision sequence changed between factory calls')
    return migrations


def _state(storage, expected_revision):
    if storage.status()['revision'] != expected_revision:
        raise ValueError('Migration did not reach the declared revision')
    if sum(path.stat().st_size for path in storage.data_dir.iterdir() if path.is_file()) > MAX_DATABASE_BYTES:
        raise ValueError('Disposable migration database budget exceeded')
    with closing(sqlite3.connect(storage.database_path)) as connection:
        if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Migration database integrity check failed')
        if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise ValueError('Migration database foreign key check failed')
        # Include all tables, including the SDK's revision history. Never put
        # these row values in the public result or diagnostic exception text.
        logical = '\n'.join(connection.iterdump())
    if len(logical.encode('utf-8')) > MAX_DUMP_BYTES:
        raise ValueError('Disposable migration dump budget exceeded')
    return logical


class _InjectedFailure(RuntimeError):
    pass


def _rollback(migrations, index, work):
    from packages.application_sdk import ApplicationMigration, ApplicationStorage

    storage = ApplicationStorage(work / f'rollback-{index:02d}')
    if index:
        baseline = migrations[:index]
        previous = baseline[-1].revision
        storage.migrate(baseline, previous)
    else:
        # Public migrate() initializes its metadata before applying revision 1.
        # Fail before the first callback to establish that exact empty-history
        # preimage through the public SDK, without copying/editing SDK tables.
        def before_action(_connection):
            raise _InjectedFailure('Disposable migration initialization')
        try:
            storage.migrate([ApplicationMigration(migrations[0].revision, before_action)], migrations[0].revision)
        except _InjectedFailure:
            pass
        else:
            raise ValueError('Disposable migration initialization was not interrupted')
        baseline, previous = [], None
    before = _state(storage, previous)
    current = migrations[index]

    def interrupted(connection):
        current.apply(connection)
        raise _InjectedFailure('Disposable migration interruption')

    try:
        storage.migrate([*baseline, ApplicationMigration(current.revision, interrupted)], current.revision)
    except _InjectedFailure:
        pass
    else:
        raise ValueError('Disposable migration interruption was not observed')
    if _state(storage, previous) != before:
        raise ValueError('Interrupted migration changed committed logical data or history')


def _exercise(wheel, entrypoint, target, work):
    from packages.application_sdk import ApplicationStorage

    module, attribute = entrypoint.split(':', 1)
    sys.path.insert(0, str(wheel))
    imported = importlib.import_module(module)
    for count in range(1, len(module.split('.')) + 1):
        loaded = sys.modules['.'.join(module.split('.')[:count])]
        spec = loaded.__spec__
        locations = ([spec.origin] if spec and spec.origin else
                     list(spec.submodule_search_locations or ()) if spec else [])
        if not locations or any(wheel.resolve() not in Path(location).resolve().parents for location in locations):
            raise ValueError('Migration imports must originate in the exact packaged wheel')
    factory = getattr(imported, attribute)
    if not callable(factory):
        raise ValueError('Migration entrypoint is not callable')
    migrations = _plan(factory)
    revisions = [item.revision for item in migrations]
    if target != revisions[-1]:
        raise ValueError('Declared target must be the final packaged migration revision')

    def fresh_plan():
        # SDK target slicing must not silently omit revisions introduced by a
        # stateful factory after the first validated declaration.
        return _plan(factory, expected_revisions=revisions)

    # The public SDK validates revision syntax, duplicates and forward history.
    clean = ApplicationStorage(work / 'clean')
    clean.migrate(migrations, target)
    initial = _state(clean, target)
    reopened = ApplicationStorage(clean.data_dir)
    reopened.migrate(fresh_plan(), target)
    if _state(reopened, target) != initial:
        raise ValueError('Reopening migrations changed existing logical data or history')

    selected = migrations[:revisions.index(target) + 1]
    for index, migration in enumerate(selected[:-1]):
        # Every prefix gets its own database. This exercises current declared
        # history, not unknown schemas/data from an older published package.
        storage = ApplicationStorage(work / f'prefix-{index:02d}')
        storage.migrate(fresh_plan(), migration.revision)
        _state(storage, migration.revision)
        upgraded = ApplicationStorage(storage.data_dir)
        upgraded.migrate(fresh_plan(), target)
        before = _state(upgraded, target)
        ApplicationStorage(storage.data_dir).migrate(fresh_plan(), target)
        if _state(upgraded, target) != before:
            raise ValueError('Reopening an upgraded database changed logical data or history')
    for index in range(len(selected)):
        _rollback(migrations, index, work)
    return {'status': 'passed', 'target_revision': target, 'revision_count': len(selected),
            'prefix_upgrade_count': len(selected) - 1, 'reopen_verified': True,
            'integrity_verified': True, 'rollback_verified': True,
            'rollback_probe_count': len(selected),
            'scope': 'current packaged migrations on disposable data; not historic-data compatibility'}


def _main(arguments):
    if len(arguments) != 2 or arguments[0] != '--worker':
        return 2
    try:
        request = json.loads(Path(arguments[1]).read_text(encoding='utf-8'))
        work = Path(request['work'])
        result = _exercise(Path(request['wheel']), request['entrypoint'], request['target'], work)
        Path(request['result']).write_text(json.dumps(result), encoding='utf-8')
        return 0
    except Exception:
        # Detailed output belongs only in the developer's existing local log.
        # The parent returns a fixed, row/exception-text-free failure category.
        traceback.print_exc()
        return 1


def run_packaged_migrations(blob, validated, *, root: Path, environment: dict, log):
    """Check the exact validated wheel in an owned process and temporary tree."""
    definition = validated.application_extension
    if definition.storage.relational is not None:
        raise ProjectCheckError('migrations', 'Scoped relational migrations are not supported by this local profile.')
    if hashlib.sha256(blob).hexdigest() != validated.sha256:
        raise ProjectCheckError('migrations', 'Migration package does not match the validated artifact.')
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            wheel = archive.read(definition.service.artifact)
        if hashlib.sha256(wheel).hexdigest() != definition.service.artifact_sha256:
            raise ProjectCheckError('migrations', 'Migration wheel does not match the validated service artifact.')
        module = definition.storage.migration_entrypoint.split(':', 1)[0].replace('.', '/')
        with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
            if not {module + '.py', module + '/__init__.py'} & set(archive.namelist()):
                raise ProjectCheckError('migrations', 'The declared migration module must be in the exact service wheel.')
        with tempfile.TemporaryDirectory(prefix='migrations-', dir=root) as temporary:
            owned = Path(temporary)
            wheel_path = owned / 'application.whl'
            wheel_path.write_bytes(wheel)
            result_path, request_path = owned / 'result.json', owned / 'request.json'
            request_path.write_text(json.dumps({'wheel': str(wheel_path), 'work': str(owned),
                'entrypoint': definition.storage.migration_entrypoint,
                'target': definition.storage.schema_revision, 'result': str(result_path)}), encoding='utf-8')
            result = subprocess.run([sys.executable, '-I', '-B', '-c', _LAUNCHER, str(REPOSITORY),
                                     '--worker', str(request_path)], cwd=owned, env=environment,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=TIMEOUT_SECONDS, check=False)
            if result.returncode:
                raise ProjectCheckError('migrations', 'Packaged migration checks failed. See the local check log; no package was published.')
            summary = json.loads(result_path.read_text(encoding='utf-8'))
            expected = {'status', 'target_revision', 'revision_count', 'prefix_upgrade_count',
                        'reopen_verified', 'integrity_verified', 'rollback_verified', 'rollback_probe_count', 'scope'}
            if (type(summary) is not dict or set(summary) != expected or summary['status'] != 'passed'
                    or summary['target_revision'] != definition.storage.schema_revision
                    or type(summary['revision_count']) is not int or not 1 <= summary['revision_count'] <= MAX_MIGRATIONS
                    or type(summary['prefix_upgrade_count']) is not int
                    or summary['prefix_upgrade_count'] != summary['revision_count'] - 1
                    or summary['reopen_verified'] is not True or summary['integrity_verified'] is not True
                    or summary['rollback_verified'] is not True
                    or type(summary['rollback_probe_count']) is not int
                    or summary['rollback_probe_count'] != summary['revision_count']
                    or summary['scope'] != 'current packaged migrations on disposable data; not historic-data compatibility'):
                raise ProjectCheckError('migrations', 'Packaged migration result evidence is invalid.')
            return summary
    except ProjectCheckError:
        raise
    except subprocess.TimeoutExpired as error:
        raise ProjectCheckError('migrations', 'Packaged migration checks exceeded the local time budget; no package was published.') from error
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise ProjectCheckError('migrations', 'Packaged migration checks could not complete; inspect the local toolchain and log.') from error


if __name__ == '__main__':
    raise SystemExit(_main(sys.argv[1:]))
