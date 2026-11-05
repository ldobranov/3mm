"""Source-derived metadata is not execution, installed support or authority."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from backend.services.module_packages import validate_module_package
from three_mm_application_sdk import SDK_VERSION
from three_mm_protocol.application_extension import ApplicationLifecycleV1, ApplicationOperationV1
from three_mm_protocol.extension_schemas import extension_schema_catalog
import three_mm_platform_wire as wire
from tools import application_catalog as catalog
from tools import application_migrations, application_project

STARTER = Path(__file__).resolve().parents[2] / 'modules/application-starter'


@pytest.fixture
def source(tmp_path):
    root = tmp_path / 'project'
    for name, data in application_project.inputs(STARTER).items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


def edit_descriptor(source, change):
    path = source / 'application-extension.json'
    definition = json.loads(path.read_text(encoding='utf-8-sig'))
    change(definition)
    path.write_text(json.dumps(definition), encoding='utf-8')


def test_global_catalog_is_deterministic_source_derived_and_not_a_runtime_inventory():
    first = catalog.application_catalog()
    assert first == catalog.application_catalog()
    assert first['catalog_version'] == 1 and 'project' not in first
    current = extension_schema_catalog()['contracts']
    assert set(first['contracts']) == {'module-manifest.v2', 'application-extension.v1', 'compiled-ui.v1'}
    for name, contract in first['contracts'].items():
        assert contract['schema'] == current[name]['schema']
        assert set(contract) == {'document', 'version_field', 'contract_version', 'source_model', 'schema'}
    assert first['models'][f'{ApplicationOperationV1.__module__}.ApplicationOperationV1'] == ApplicationOperationV1.model_json_schema(mode='validation')
    assert first['sdk']['version'] == SDK_VERSION
    assert first['sdk']['platform_error_reasons'] == sorted(wire.ERROR_REASONS)
    assert first['sdk']['transport_limits']['REQUEST_TIMEOUT_SECONDS'] == wire.REQUEST_TIMEOUT_SECONDS
    assert first['profile']['migration_limits']['MAX_MIGRATIONS'] == application_migrations.MAX_MIGRATIONS
    assert first['profile']['migration_limits']['TIMEOUT_SECONDS'] == application_migrations.TIMEOUT_SECONDS
    assert first['sdk']['error_contract']['phase_literals'] == ['execution_unconfirmed', 'not_dispatched']
    assert first['sdk']['error_contract']['automatic_retry'] is False
    assert 'no retry' in first['ui_host']['invoke_semantics']
    assert 'runtime support' in first['scope'] and 'not runtime support' in first['scope']
    assert 'execution_profiles' not in first['contracts']['application-extension.v1']


def test_all_source_hashes_identify_exact_read_sources_without_personal_paths():
    result = catalog.application_catalog()
    paths = [item['path'] for item in result['sources']]
    assert paths == sorted(set(paths))
    assert 'frontend/src/extension-ui/application-v1.ts' in paths
    assert 'three_mm_protocol/application_extension.py' in paths
    assert 'three_mm_protocol/application_commands.py' in paths
    assert 'tools/application_migrations.py' in paths
    assert 'VERSION' in paths and 'backend/version.py' in paths
    for item in result['sources']:
        assert not Path(item['path']).is_absolute()
        assert item['sha256'] == hashlib.sha256(catalog._read_source(item['path'])).hexdigest()
    assert str(catalog.REPOSITORY) not in json.dumps(result)
    assert 'three_mm_protocol.application_extension.ApplicationOperationV1.validate_operation_semantics' in result['validation']['semantic_validator_sources']
    assert 'three_mm_protocol.application_extension.ApplicationPrivateFilesV1.coherent_limits' in result['validation']['semantic_validator_sources']


def test_project_catalog_uses_real_semantic_validator_and_exact_full_declarations(source):
    result = catalog.application_catalog(source)['project']
    blob = application_project.build_package(source)
    validated = validate_module_package(blob)
    assert result['package_sha256'] == validated.sha256
    assert result['package_bytes'] == len(blob)
    assert result['semantic_validation']['core_version'] == (catalog.REPOSITORY / 'VERSION').read_text().strip()
    assert result['application_declarations'] == validated.application_extension.model_dump(mode='json', exclude_none=True)
    assert result['review'] == application_project.declaration_review(validated)
    assert result['lifecycle'] == ApplicationLifecycleV1().model_dump(mode='json')
    assert result['authoring_check_support']['check'] == 'not_run'
    assert result['authoring_check_support']['migration_probe'] == 'not_run'
    assert 'no tests' in result['semantic_validation']['scope']
    assert result['review']['human_permissions'] == ['note_read', 'note_write']
    assert result['review']['optional_resources'] == ['command:resource']


def test_catalog_never_imports_application_code_or_runs_checks_migrations_or_network(source, monkeypatch):
    before = application_project.fingerprint(application_project.inputs(source))
    for name in ('__init__.py', 'service.py', 'migrations.py'):
        (source / 'service/starter_app' / name).write_text("raise RuntimeError('APPLICATION MUST NOT IMPORT')\n")
    for name in ('pytest', 'node_modules', 'dist'):
        assert not (source / name).exists()
    def forbidden(*_args, **_kwargs):
        pytest.fail('Catalog must not execute a process or migration')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(application_project, 'run_check', forbidden)
    monkeypatch.setattr(application_migrations, 'run_packaged_migrations', forbidden)
    existing_modules = {name for name in sys.modules if name == 'starter_app' or name.startswith('starter_app.')}
    frozen = application_project.fingerprint(application_project.inputs(source))
    assert before != frozen
    result = catalog.application_catalog(source)
    assert result['project']['semantic_validation']['status'] == 'passed'
    assert application_project.fingerprint(application_project.inputs(source)) == frozen
    assert {name for name in sys.modules if name == 'starter_app' or name.startswith('starter_app.')} == existing_modules
    assert not (source / 'state.sqlite3').exists()


@pytest.mark.parametrize('change', [
    lambda app: app['permissions'].pop(),
    lambda app: app['operations'][0].update(kind='command'),
    lambda app: app['operations'][1].update(required_permission='missing_permission'),
    lambda app: app['routes'][0].update(required_permissions=['missing_permission']),
    lambda app: app['lifecycle'].update(disable_preserves_data=False),
])
def test_real_semantic_failures_do_not_produce_a_catalog(source, change):
    # Even defaults that are absent in source are validated by the public model.
    edit_descriptor(source, lambda app: app.setdefault('lifecycle', {}))
    edit_descriptor(source, change)
    with pytest.raises(application_project.ProjectCheckError) as failure:
        catalog.application_catalog(source)
    assert failure.value.stage == 'catalog'


def test_valid_scoped_relational_descriptor_is_not_claimed_supported_by_local_migration_profile(source):
    edit_descriptor(source, lambda app: app['storage'].update(relational={
        'contract_version': 1, 'mode': 'read_write', 'limit_class': 'cooperative_v1',
        'max_database_bytes': 65536, 'auxiliary_pause_bytes': 65536,
        'max_statement_bytes': 1024, 'max_value_bytes': 1024, 'max_result_bytes': 1024,
        'max_result_rows': 10, 'max_transaction_ms': 1000, 'max_busy_ms': 100}))
    result = catalog.application_catalog(source)['project']
    assert result['semantic_validation']['status'] == 'passed'
    assert result['authoring_check_support'] == {'profile': 'pure_python_sqlite', 'check': 'not_run',
        'migration_probe': 'unsupported', 'reason': 'scoped_relational'}


def test_changed_project_source_never_gets_a_coherent_catalog(source, monkeypatch):
    original = application_project.build_package
    def changed(snapshot):
        blob = original(snapshot)
        (source / 'source/frontend/Notes.vue').write_text('changed after frozen package')
        return blob
    monkeypatch.setattr(application_project, 'build_package', changed)
    with pytest.raises(application_project.ProjectCheckError, match='source changed'):
        catalog.application_catalog(source)


def test_changed_authoritative_source_never_gets_a_coherent_catalog(monkeypatch):
    original = catalog._read_source
    counts = {}
    def changed(relative):
        counts[relative] = counts.get(relative, 0) + 1
        value = original(relative)
        return value + b'\n' if relative == catalog._UI_SOURCE and counts[relative] > 1 else value
    monkeypatch.setattr(catalog, '_read_source', changed)
    with pytest.raises(application_project.ProjectCheckError, match='sources changed'):
        catalog.application_catalog()


@pytest.mark.parametrize('transform', [
    lambda data: data.replace(b'ApplicationHostErrorCode', b'DifferentErrorCode'),
    lambda data: data.replace(b"'access_denied' | 'unavailable'", b"'access_denied' | OtherType"),
    lambda data: data.replace(b'APPLICATION_HOST_VERSION', b'DifferentVersion'),
    lambda data: data.replace(b'invoke(operationId:', b'otherMethod(operationId:'),
])
def test_ui_contract_reader_fails_closed_on_changed_public_type_grammar(transform):
    with pytest.raises(application_project.ProjectCheckError, match='UI host contract format'):
        catalog._ui_contract(transform(catalog._read_source(catalog._UI_SOURCE)))


def test_ui_error_code_additions_are_read_from_source_not_a_duplicate_list():
    original = catalog._read_source(catalog._UI_SOURCE)
    changed = original.replace(b"'access_denied' | 'unavailable'", b"'new_error' | 'access_denied' | 'unavailable'")
    assert 'new_error' in catalog._ui_contract(changed)['error_codes']


def test_missing_sdk_error_metadata_fails_closed():
    data = catalog._read_source(catalog._SDK_SOURCE).replace(b'self.retryable = False', b'self.retryable = dynamic_value')
    with pytest.raises(application_project.ProjectCheckError, match='SDK error contract format'):
        catalog._sdk_errors(data)


def test_compatibility_version_cannot_diverge_from_captured_source(source, monkeypatch):
    from backend import version
    monkeypatch.setattr(version, 'core_version', lambda: '0.0.1')
    with pytest.raises(application_project.ProjectCheckError, match='compatibility sources changed'):
        catalog.application_catalog(source)


def test_nonapplication_module_does_not_become_an_application_catalog(source):
    path = source / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    manifest.update(runtimes=['core'], entrypoints={'core': 'other-module.json'})
    path.write_text(json.dumps(manifest), encoding='utf-8')
    # The generic package validator also accepts nonapplication module types.
    validated = validate_module_package(application_project.build_package(source))
    assert validated.application_extension is None
    with pytest.raises(application_project.ProjectCheckError, match='requires an application-extension'):
        catalog.application_catalog(source)
