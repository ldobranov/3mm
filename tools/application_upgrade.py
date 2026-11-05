"""Exact previous-package upgrade checks on fixture-seeded disposable SQLite.

The fixture and both packages are trusted local developer code. This is not a
live restore, installed upgrade, code isolation or a universal data-loss proof.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import traceback
import zipfile

from tools.application_migrations import (
    MAX_MIGRATIONS, TIMEOUT_SECONDS, _InjectedFailure, _plan, _state,
)
from tools.application_project import ProjectCheckError, REPOSITORY

MAX_EXPECTATION_BYTES = 64 * 1024
MAX_FIXTURE_BYTES = 1024 * 1024
SCOPE = 'explicit fixture on disposable previous-package data; not installed upgrade or universal historical-data compatibility'
_LAUNCHER = ('import sys; sys.path.insert(0, sys.argv[1]); '
             'from tools.application_upgrade import _main; '
             'raise SystemExit(_main(sys.argv[2:]))')


def _newer(previous, candidate):
    """SemVer precedence, excluding build metadata (models validate syntax)."""
    def split(value):
        core, separator, pre = value.split('+', 1)[0].partition('-')
        return tuple(map(int, core.split('.'))), pre.split('.') if separator else None
    old_core, old_pre = split(previous)
    new_core, new_pre = split(candidate)
    if old_core != new_core:
        return new_core > old_core
    if old_pre is None or new_pre is None:
        return old_pre is not None and new_pre is None
    for old, new in zip(old_pre, new_pre):
        if old == new:
            continue
        if old.isdigit() and new.isdigit():
            return int(new) > int(old)
        if old.isdigit() != new.isdigit():
            return old.isdigit()
        return new > old
    return len(new_pre) > len(old_pre)


def _assert_wheel_modules(wheel, module):
    root = module.split('.', 1)[0]
    for name, loaded in list(sys.modules.items()):
        if name != root and not name.startswith(root + '.'):
            continue
        spec = getattr(loaded, '__spec__', None)
        locations = ([spec.origin] if spec and spec.origin else
                     list(spec.submodule_search_locations or ()) if spec else [])
        if not locations or any(wheel.resolve() not in Path(location).resolve().parents for location in locations):
            raise ValueError('Application imports must originate in the exact packaged wheel')


def _load_exact(wheel, entrypoint):
    module, attribute = entrypoint.split(':', 1)
    sys.path.insert(0, str(wheel))
    imported = importlib.import_module(module)
    _assert_wheel_modules(wheel, module)
    factory = getattr(imported, attribute)
    if not callable(factory):
        raise ValueError('Migration factory is not callable')
    return factory


def _fixture(path):
    spec = importlib.util.spec_from_file_location('_application_upgrade_fixture', path)
    if spec is None or spec.loader is None:
        raise ValueError('Upgrade fixture is unavailable')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    if not callable(getattr(fixture, 'seed', None)) or not callable(getattr(fixture, 'verify', None)):
        raise ValueError('Upgrade fixture requires seed and verify callables')
    return fixture


def _json(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8')
    if type(value) is not dict or len(encoded) > MAX_EXPECTATION_BYTES:
        raise ValueError('Upgrade fixture expectation must be a bounded JSON object')
    return encoded


def _context(request, storage):
    from three_mm_application_sdk import ApplicationContext
    return ApplicationContext(request['module_id'], request['version'], storage.data_dir,
                              request['configuration'], storage)


def _copy_database(source, destination):
    from three_mm_application_sdk import ApplicationStorage
    copy = ApplicationStorage(destination)
    destination.mkdir()
    # SQLite backup includes committed WAL content; never copy an arbitrary
    # filename while the source might still have a committed WAL.
    with closing(sqlite3.connect(source.database_path)) as old, closing(sqlite3.connect(copy.database_path)) as new:
        old.backup(new)
    return copy


def _seed(request):
    from three_mm_application_sdk import ApplicationStorage
    factory = _load_exact(Path(request['wheel']), request['entrypoint'])
    migrations = _plan(factory)
    revisions = [item.revision for item in migrations]
    if revisions[-1] != request['target']:
        raise ValueError('Previous declared target must be the final packaged migration')
    storage = ApplicationStorage(Path(request['data']))
    storage.migrate(migrations, request['target'])
    expectation = _fixture(Path(request['fixture'])).seed(_context(request, storage))
    _json(expectation)
    _state(storage, request['target'])
    _assert_wheel_modules(Path(request['wheel']), request['entrypoint'].split(':', 1)[0])
    if [item.revision for item in _plan(factory)] != revisions:
        raise ValueError('Previous migration revision plan changed')
    return {'revisions': revisions, 'expectation': expectation}


def _upgrade(request):
    from three_mm_application_sdk import ApplicationMigration, ApplicationStorage
    seeded = json.loads(Path(request['seeded']).read_text(encoding='utf-8'))
    old_revisions = seeded['revisions']
    expectation = _json(seeded['expectation'])
    factory = _load_exact(Path(request['wheel']), request['entrypoint'])
    migrations = _plan(factory)
    revisions = [item.revision for item in migrations]
    if revisions[-1] != request['target'] or revisions[:len(old_revisions)] != old_revisions:
        raise ValueError('Candidate migration history must extend the exact previous revision sequence')
    storage = ApplicationStorage(Path(request['data']))
    _state(storage, request['previous_target'])
    probes = 0
    for index in range(len(old_revisions), len(revisions)):
        copy = _copy_database(storage, Path(request['work']) / f'rollback-{index:02d}')
        previous = migrations[index - 1].revision
        copy.migrate(_plan(factory, expected_revisions=revisions), previous)
        before = _state(copy, previous)
        current = migrations[index]

        def interrupted(connection):
            current.apply(connection)
            raise _InjectedFailure('Disposable previous-package upgrade interruption')

        try:
            copy.migrate([*migrations[:index], ApplicationMigration(current.revision, interrupted)], current.revision)
        except _InjectedFailure:
            pass
        else:
            raise ValueError('Upgrade interruption was not observed')
        if _state(copy, previous) != before:
            raise ValueError('Interrupted upgrade changed committed data or migration history')
        probes += 1
    storage.migrate(_plan(factory, expected_revisions=revisions), request['target'])
    fixture = _fixture(Path(request['fixture']))
    before = _state(storage, request['target'])
    if fixture.verify(_context(request, storage), json.loads(expectation)) is not None:
        raise ValueError('Upgrade verification must assert and return None')
    if _state(storage, request['target']) != before:
        raise ValueError('Upgrade verification changed the saved logical data or history')
    reopened = ApplicationStorage(storage.data_dir)
    reopened.migrate(_plan(factory, expected_revisions=revisions), request['target'])
    if _state(reopened, request['target']) != before:
        raise ValueError('Reopening upgraded data changed logical data or history')
    if fixture.verify(_context(request, reopened), json.loads(expectation)) is not None:
        raise ValueError('Reopened upgrade verification must return None')
    if _state(reopened, request['target']) != before:
        raise ValueError('Reopened verification changed logical data or history')
    _assert_wheel_modules(Path(request['wheel']), request['entrypoint'].split(':', 1)[0])
    return {'status': 'passed', 'domain_verified': True, 'reopen_verified': True,
            'integrity_verified': True, 'previous_revision_count': len(old_revisions),
            'revision_count': len(revisions), 'rollback_probe_count': probes,
            'rollback_status': 'passed' if probes else 'not_applicable', 'scope': SCOPE}


def _main(arguments):
    if len(arguments) != 2 or arguments[0] != '--worker':
        return 2
    try:
        request = json.loads(Path(arguments[1]).read_text(encoding='utf-8'))
        result = _seed(request) if request['phase'] == 'seed' else _upgrade(request)
        Path(request['result']).write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        return 0
    except Exception:
        traceback.print_exc()  # Only the developer's existing local check log.
        return 1


def _wheel(blob, validated):
    from backend.services.module_packages import MAX_PACKAGE_BYTES
    definition = validated.application_extension
    if definition is None or definition.storage.relational is not None:
        raise ProjectCheckError('upgrade', 'Previous-package upgrade checks require public-SDK SQLite applications.')
    if not 0 < len(blob) <= MAX_PACKAGE_BYTES or hashlib.sha256(blob).hexdigest() != validated.sha256:
        raise ProjectCheckError('upgrade', 'Upgrade package differs from the exact validated artifact.')
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        wheel = archive.read(definition.service.artifact)
    if hashlib.sha256(wheel).hexdigest() != definition.service.artifact_sha256:
        raise ProjectCheckError('upgrade', 'Upgrade wheel differs from the exact service artifact.')
    module = definition.storage.migration_entrypoint.split(':', 1)[0].replace('.', '/')
    with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
        if not {module + '.py', module + '/__init__.py'} & set(archive.namelist()):
            raise ProjectCheckError('upgrade', 'Upgrade migration module must be in the exact service wheel.')
    return wheel


def run_packaged_upgrade(previous_blob, previous_validated, blob, validated, *, fixture: Path,
                         root: Path, environment: dict, log) -> dict:
    """Run old seed and candidate verification in different exact-wheel processes."""
    try:
        old, new = previous_validated.manifest, validated.manifest
        if old.module_id != new.module_id or not _newer(old.version, new.version):
            raise ProjectCheckError('upgrade', 'Select the same application and a strictly newer candidate package version.')
        previous_wheel, candidate_wheel = _wheel(previous_blob, previous_validated), _wheel(blob, validated)
        fixture = Path(fixture)
        if (not fixture.is_file() or fixture.is_symlink() or fixture.suffix != '.py'
                or any(parent.is_symlink() for parent in fixture.parents)):
            raise ProjectCheckError('upgrade', 'Select a regular local Python upgrade fixture.')
        fixture_bytes = fixture.read_bytes()
        if not 0 < len(fixture_bytes) <= MAX_FIXTURE_BYTES:
            raise ProjectCheckError('upgrade', 'Upgrade fixture source exceeds its local budget.')
        fixture_hash = hashlib.sha256(fixture_bytes).hexdigest()
        with tempfile.TemporaryDirectory(prefix='upgrade-', dir=root) as temporary:
            owned = Path(temporary)
            fixture_copy = owned / 'fixture.py'
            fixture_copy.write_bytes(fixture_bytes)
            for name, wheel in [('previous', previous_wheel), ('candidate', candidate_wheel)]:
                (owned / f'{name}.whl').write_bytes(wheel)
            seeded = owned / 'seeded.json'
            request = {'work': str(owned), 'data': str(owned / 'data'), 'fixture': str(fixture_copy),
                       'module_id': new.module_id, 'seeded': str(seeded),
                       'previous_target': previous_validated.application_extension.storage.schema_revision}
            for phase, package, wheel_name, result_path in [
                    ('seed', previous_validated, 'previous', seeded),
                    ('upgrade', validated, 'candidate', owned / 'result.json')]:
                definition = package.application_extension
                request.update(phase=phase, wheel=str(owned / f'{wheel_name}.whl'),
                    entrypoint=definition.storage.migration_entrypoint, target=definition.storage.schema_revision,
                    version=package.manifest.version, configuration=package.manifest.configuration_defaults,
                    result=str(result_path))
                request_path = owned / 'request.json'
                request_path.write_text(json.dumps(request), encoding='utf-8')
                if (hashlib.sha256((owned / 'previous.whl').read_bytes()).hexdigest() != previous_validated.application_extension.service.artifact_sha256
                        or hashlib.sha256((owned / 'candidate.whl').read_bytes()).hexdigest() != validated.application_extension.service.artifact_sha256):
                    raise ProjectCheckError('upgrade', 'An exact upgrade service artifact changed during verification.')
                result = subprocess.run([sys.executable, '-I', '-B', '-c', _LAUNCHER, str(REPOSITORY),
                    '--worker', str(request_path)], cwd=root, env=environment, stdout=log,
                    stderr=subprocess.STDOUT, timeout=TIMEOUT_SECONDS, check=False)
                if result.returncode:
                    raise ProjectCheckError('upgrade', 'Packaged upgrade checks failed. See the local log; no package was published.')
                if result_path.stat().st_size > MAX_EXPECTATION_BYTES + 8192:
                    raise ProjectCheckError('upgrade', 'Upgrade worker evidence exceeds its local budget.')
                value = json.loads(result_path.read_text(encoding='utf-8'))
                if phase == 'seed':
                    if (type(value) is not dict or set(value) != {'revisions', 'expectation'}
                            or type(value['revisions']) is not list or not 1 <= len(value['revisions']) <= MAX_MIGRATIONS
                            or any(type(item) is not str or len(item) > 64 for item in value['revisions'])
                            or len(set(value['revisions'])) != len(value['revisions'])
                            or value['revisions'][-1] != definition.storage.schema_revision):
                        raise ProjectCheckError('upgrade', 'Previous-package seed evidence is invalid.')
                    _json(value['expectation'])
                    old_count = len(value['revisions'])
                elif (type(value) is not dict or set(value) != {'status', 'domain_verified', 'reopen_verified',
                        'integrity_verified', 'previous_revision_count', 'revision_count', 'rollback_probe_count',
                        'rollback_status', 'scope'} or value['status'] != 'passed'
                        or any(value[key] is not True for key in ('domain_verified', 'reopen_verified', 'integrity_verified'))
                        or type(value['previous_revision_count']) is not int or value['previous_revision_count'] != old_count
                        or type(value['revision_count']) is not int or not old_count <= value['revision_count'] <= MAX_MIGRATIONS
                        or type(value['rollback_probe_count']) is not int
                        or value['rollback_probe_count'] != value['revision_count'] - old_count
                        or value['rollback_status'] != ('passed' if value['rollback_probe_count'] else 'not_applicable')
                        or value['scope'] != SCOPE):
                    raise ProjectCheckError('upgrade', 'Candidate upgrade evidence is invalid.')
                if fixture_copy.read_bytes() != fixture_bytes:
                    raise ProjectCheckError('upgrade', 'Upgrade fixture changed during verification.')
                if (hashlib.sha256((owned / 'previous.whl').read_bytes()).hexdigest() != previous_validated.application_extension.service.artifact_sha256
                        or hashlib.sha256((owned / 'candidate.whl').read_bytes()).hexdigest() != validated.application_extension.service.artifact_sha256):
                    raise ProjectCheckError('upgrade', 'An exact upgrade service artifact changed during verification.')
            if fixture.read_bytes() != fixture_bytes:
                raise ProjectCheckError('upgrade', 'Upgrade fixture changed during verification.')
            return {**value, 'previous_version': old.version, 'candidate_version': new.version,
                'previous_revision': previous_validated.application_extension.storage.schema_revision,
                'target_revision': validated.application_extension.storage.schema_revision,
                'previous_package_sha256': previous_validated.sha256, 'package_sha256': validated.sha256,
                'fixture_sha256': fixture_hash}
    except ProjectCheckError:
        raise
    except subprocess.TimeoutExpired as error:
        raise ProjectCheckError('upgrade', 'Packaged upgrade checks exceeded the direct-worker time budget; no package was published.') from error
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        raise ProjectCheckError('upgrade', 'Packaged upgrade verification could not complete; inspect the existing local toolchain and log.') from error


if __name__ == '__main__':
    raise SystemExit(_main(sys.argv[1:]))
