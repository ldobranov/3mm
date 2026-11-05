"""Typed clients remain one-dispatch public-host callers, never authorities."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from three_mm_protocol.application_extension import ApplicationExtensionV1, parse_application_extension
from tools import application_client as client
from tools import application_project
from tools.application_project import ProjectCheckError, REPOSITORY

STARTER = REPOSITORY / 'modules/application-starter'


@pytest.fixture
def definition():
    return parse_application_extension((STARTER / 'application-extension.json').read_bytes())


@pytest.fixture
def source(tmp_path):
    root = tmp_path / 'project'
    for name, data in application_project.inputs(STARTER).items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


def change(definition, modify):
    value = definition.model_dump(mode='json')
    modify(value)
    return ApplicationExtensionV1.model_validate_json(json.dumps(value))


def query_schema(definition, schema):
    return change(definition, lambda value: next(operation for operation in value['operations']
        if operation['operation_id'] == 'read_note').update(input_schema=schema))


def object_schema(properties, required=()):
    return {'type': 'object', 'additionalProperties': False, 'properties': properties, 'required': list(required)}


def test_render_is_stable_pinned_and_excludes_internal_operations(definition):
    rendered = client.render_client(definition)
    assert rendered == client.render_client(change(definition, lambda value: value['operations'].reverse()))
    assert rendered.startswith(client.MARKER + '\n')
    assert client.contract_digest(definition) in rendered
    assert client._owned(rendered.encode(), definition.module_id)
    assert not client._owned((rendered + '// user edit').encode(), definition.module_id)
    assert "from '@3mm/application-ui/v1'" in rendered
    assert 'export function createApplicationClient' in rendered
    assert '"health"(' not in rendered
    assert 'export type ReadNoteInput = Record<string, never>' in rendered
    assert '"read_note"(payload: ReadNoteInput): Promise<ReadNoteOutput>' in rendered
    assert '"save_note"(payload: SaveNoteInput, options: { readonly idempotencyKey: string })' in rendered
    assert 'Runtime validation remains authoritative' in rendered
    assert 'fetch(' not in rendered and 'getInfo(' not in rendered and 'catch' not in rendered
    assert 'any' not in rendered and 'crypto' not in rendered and 'setTimeout' not in rendered
    assert str(REPOSITORY) not in rendered


def test_ui_audiences_are_explicit_and_do_not_create_current_access_claims(definition):
    def add(value):
        original = next(operation for operation in value['operations'] if operation['operation_id'] == 'read_note')
        for audience in ('public', 'kiosk', 'administrator'):
            value['operations'].append({**original, 'operation_id': audience + '_read', 'audiences': [audience]})
    rendered = client.render_client(change(definition, add))
    for audience in ('public', 'kiosk', 'administrator'):
        assert '"' + audience + '_read"(payload:' in rendered
    assert 'No code trust or access is granted.' in rendered


@pytest.mark.parametrize('schema', [
    {'$ref': '#/$defs/Node'}, {'type': 'string', 'anyOf': [{'type': 'null'}]},
    {'type': 'string', 'oneOf': [{'type': 'null'}]}, {'type': 'string', 'const': 'x'},
    {'type': ['string', 'integer']}, {'type': ['string', 'null', 'integer']},
    {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'additionalProperties': {'type': 'integer'}},
    {'type': 'array', 'items': False}, {'type': 'string', 'enum': ['x', 1]},
    {'type': 'object', 'enum': [{}]}, {'type': 'integer', 'enum': [2**53]},
])
def test_unsupported_schema_never_silently_widens_into_any(definition, schema):
    modified = query_schema(definition, object_schema({'value': schema}, ['value']))
    with pytest.raises(ProjectCheckError) as failure:
        client.render_client(modified)
    assert failure.value.stage == 'client'


def test_alias_collisions_refuse_instead_of_mapping_two_different_operations(definition):
    def collision(value):
        original = next(operation for operation in value['operations'] if operation['operation_id'] == 'read_note')
        value['operations'].append({**original, 'operation_id': 'read__note'})
    with pytest.raises(ProjectCheckError, match='collide'):
        client.render_client(change(definition, collision))


def test_generate_is_exclusive_identical_is_unchanged_and_replace_is_explicit(source):
    relative = Path('source/frontend/generated-client.ts')
    first = client.generate_client(source, relative)
    assert first['status'] == 'created' and first['output'] == relative.as_posix()
    target = source / relative
    before = target.read_bytes()
    assert client.generate_client(source, relative)['status'] == 'unchanged'
    # Universal generated LF content remains recognized in a CRLF checkout.
    target.write_bytes(before.replace(b'\n', b'\r\n'))
    assert client.generate_client(source, relative)['status'] == 'unchanged'
    descriptor = source / 'application-extension.json'
    definition = json.loads(descriptor.read_text())
    next(operation for operation in definition['operations'] if operation['operation_id'] == 'save_note')['input_schema']['properties']['text']['maxLength'] = 100
    descriptor.write_text(json.dumps(definition))
    with pytest.raises(ProjectCheckError, match='explicitly replaced'):
        client.generate_client(source, relative)
    replaced = client.generate_client(source, relative, replace=True)
    assert replaced['status'] == 'replaced' and replaced['contract_sha256'] != first['contract_sha256']
    assert target.read_bytes() != before
    assert replaced['checks'] == 'not_run' and replaced['installation'] == replaced['grants'] == 'not_requested'
    recovery = source / replaced['recovery_file']
    assert recovery.read_bytes() == before.replace(b'\n', b'\r\n')
    assert replaced['recovery_file'].startswith('.runtime/client-recovery/')
    assert replaced['recovery_file'] not in application_project.inputs(source)
    assert not list(target.parent.glob('.3mm-client-*'))


@pytest.mark.parametrize('content', ['user source', client.MARKER + '\n// user-written marker'])
def test_replace_never_overwrites_an_arbitrary_or_edited_user_file(source, content):
    relative = Path('source/frontend/generated-client.ts')
    target = source / relative
    target.write_text(content)
    with pytest.raises(ProjectCheckError, match='unedited generated client'):
        client.generate_client(source, relative, replace=True)
    assert target.read_text() == content


@pytest.mark.parametrize('relative', ['../outside.ts', 'source/client.ts', 'source/frontend/types.d.ts',
    'source/frontend/client.vue', 'source/frontend/../client.ts'])
def test_output_paths_cannot_escape_or_replace_other_source_kinds(source, relative):
    with pytest.raises(ProjectCheckError):
        client.generate_client(source, Path(relative))


def test_output_cannot_use_a_symbolic_redirect_even_when_target_is_inside_project(source, monkeypatch):
    target = source / 'source/frontend/generated-client.ts'
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == target or original(path))
    with pytest.raises(ProjectCheckError, match='symbolic'):
        client.generate_client(source, target)
    assert not target.exists()


def test_racing_new_file_is_not_overwritten_and_owned_staging_is_removed(source, monkeypatch):
    target = source / 'source/frontend/generated-client.ts'
    link = os.link
    def race(owned, destination):
        destination.write_text('concurrent user file')
        return link(owned, destination)
    monkeypatch.setattr(client.os, 'link', race)
    with pytest.raises(ProjectCheckError):
        client.generate_client(source, target)
    assert target.read_text() == 'concurrent user file'
    assert not list(target.parent.glob('.3mm-client-*'))


def test_source_change_before_publication_refuses_without_client(source, monkeypatch):
    original = application_project.build_package
    def changed(snapshot):
        blob = original(snapshot)
        (source / 'source/frontend/Notes.vue').write_text('changed source')
        return blob
    monkeypatch.setattr(application_project, 'build_package', changed)
    target = source / 'source/frontend/generated-client.ts'
    with pytest.raises(ProjectCheckError, match='source changed'):
        client.generate_client(source, target)
    assert not target.exists()


def test_unchanged_output_cannot_hide_an_edit_during_source_capture(source, monkeypatch):
    relative = Path('source/frontend/generated-client.ts')
    client.generate_client(source, relative)
    target = source / relative
    original = application_project.inputs
    mutated = False
    def edited(root):
        nonlocal mutated
        if root == source and not mutated:
            mutated = True
            target.write_text('concurrent edit retained')
        return original(root)
    monkeypatch.setattr(application_project, 'inputs', edited)
    with pytest.raises(ProjectCheckError, match='output changed'):
        client.generate_client(source, relative)
    assert target.read_text() == 'concurrent edit retained'


def prepare_replacement(source):
    relative = Path('source/frontend/generated-client.ts')
    client.generate_client(source, relative)
    descriptor = source / 'application-extension.json'
    definition = json.loads(descriptor.read_text())
    next(operation for operation in definition['operations'] if operation['operation_id'] == 'save_note')['input_schema']['properties']['text']['maxLength'] = 100
    descriptor.write_text(json.dumps(definition))
    return relative


def test_replace_preserves_and_exclusively_restores_edit_at_rename_boundary(source, monkeypatch):
    relative = prepare_replacement(source)
    target, rename = source / relative, os.rename
    def writer(original, backup):
        original.write_text('concurrent edit at displacement')
        return rename(original, backup)
    monkeypatch.setattr(client.os, 'rename', writer)
    with pytest.raises(ProjectCheckError, match='Displaced source is retained at'):
        client.generate_client(source, relative, replace=True)
    assert target.read_text() == 'concurrent edit at displacement'
    backups = list((source / '.runtime/client-recovery').glob('previous-*/client.ts.bak'))
    assert len(backups) == 1 and backups[0].read_text() == target.read_text()
    assert not list(target.parent.glob('.3mm-client-*'))


def test_replace_never_overwrites_new_target_after_displacement(source, monkeypatch):
    relative = prepare_replacement(source)
    target, link = source / relative, os.link
    before = target.read_bytes()
    def writer(staged, destination, **options):
        if staged.suffix == '.tmp':
            destination.write_text('concurrent new target retained')
        return link(staged, destination, **options)
    monkeypatch.setattr(client.os, 'link', writer)
    with pytest.raises(ProjectCheckError, match='Displaced source is retained at'):
        client.generate_client(source, relative, replace=True)
    assert target.read_text() == 'concurrent new target retained'
    backups = list((source / '.runtime/client-recovery').glob('previous-*/client.ts.bak'))
    assert len(backups) == 1 and backups[0].read_bytes() == before
    assert not list(target.parent.glob('.3mm-client-*'))


def test_recovery_redirect_is_refused_before_output_is_displaced(source, monkeypatch):
    relative = prepare_replacement(source)
    target, before = source / relative, (source / relative).read_bytes()
    redirected = source / '.runtime'
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == redirected or original(path))
    with pytest.raises(ProjectCheckError, match='recovery directories'):
        client.generate_client(source, relative, replace=True)
    assert target.read_bytes() == before


def test_late_output_change_keeps_displaced_source_and_reports_recovery(source, monkeypatch):
    relative = prepare_replacement(source)
    target, link = source / relative, os.link
    before = target.read_bytes()
    def edited(staged, destination, **options):
        result = link(staged, destination, **options)
        if staged.suffix == '.tmp':
            destination.write_text('later edit retained')
        return result
    monkeypatch.setattr(client.os, 'link', edited)
    with pytest.raises(ProjectCheckError, match='Displaced source is retained at'):
        client.generate_client(source, relative, replace=True)
    assert target.read_text() == 'later edit retained'
    backup, = (source / '.runtime/client-recovery').glob('previous-*/client.ts.bak')
    assert backup.read_bytes() == before


def test_generator_does_not_import_app_or_run_checks_migrations_or_network(source, monkeypatch):
    for name in ('__init__.py', 'service.py', 'migrations.py'):
        (source / 'service/starter_app' / name).write_text("raise RuntimeError('APPLICATION MUST NOT IMPORT')\n")
    def forbidden(*_args, **_kwargs): pytest.fail('No subprocess or checks during client generation')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    existing = {name for name in sys.modules if name == 'starter_app' or name.startswith('starter_app.')}
    assert client.generate_client(source, Path('source/frontend/generated-client.ts'))['status'] == 'created'
    assert {name for name in sys.modules if name == 'starter_app' or name.startswith('starter_app.')} == existing


@pytest.fixture
def typescript():
    frontend = REPOSITORY / 'frontend'
    node = os.getenv('COMPILED_UI_NODE') or shutil.which('node')
    if not node or not (frontend / 'node_modules/typescript/bin/tsc').is_file():
        pytest.fail('Explicit toolchain acceptance requires existing Node/TypeScript; nothing was installed')
    return node, frontend


def accept_real_typescript_enforces_nullable_nested_arrays_enums_maps_and_original_keys(definition, tmp_path, typescript):
    node, frontend = typescript
    filters = object_schema({
        'term': {'type': ['string', 'null']}, 'category': {'type': 'string', 'enum': ['one', 'two']},
        'entries': {'type': 'array', 'items': object_schema({'id': {'type': 'integer'}}, ['id'])},
        'free': {'type': 'object', 'additionalProperties': True, 'properties': {'label': {'type': 'string'}}},
        'index': {'type': 'object', 'additionalProperties': {'type': 'string'}},
    }, ['category', 'entries', 'free', 'index'])
    modified = query_schema(definition, object_schema({'filters': filters}, ['filters']))
    (tmp_path / 'client.ts').write_text(client.render_client(modified), encoding='utf-8')
    (tmp_path / 'usage.ts').write_text('''import { createApplicationClient } from './client'
import type { ApplicationHost } from '@3mm/application-ui/v1'
declare const host: Pick<ApplicationHost, 'invoke'>
const client = createApplicationClient(host)
const filters = { category: 'one' as const, entries: [{ id: 1 }], free: { arbitrary: [true, null] }, index: { x: 'yes' } }
client.read_note({ filters })
client.read_note({ filters: { ...filters, term: null } })
client.save_note({ text: 'hello', revision: 1 }, { idempotencyKey: 'original-key' })
// @ts-expect-error command requires the caller's original idempotency key
client.save_note({ text: 'hello', revision: 1 })
// @ts-expect-error keys are strings, never invented options
client.save_note({ text: 'hello', revision: 1 }, { idempotencyKey: 2 })
// @ts-expect-error query does not accept command options
client.read_note({ filters }, { idempotencyKey: 'forbidden' })
// @ts-expect-error missing required nested field
client.read_note({ filters: { ...filters, entries: [{}] } })
// @ts-expect-error scalar enum is exact
client.read_note({ filters: { ...filters, category: 'three' } })
// @ts-expect-error nullable string is not boolean
client.read_note({ filters: { ...filters, term: false } })
// @ts-expect-error typed map values are strings
client.read_note({ filters: { ...filters, index: { x: false } } })
// @ts-expect-error closed object has no extra literal fields
client.read_note({ filters, unknown: 'field' })
// @ts-expect-error internal health is not a UI client method
client.health({})
async function lookup() {
  const result = await client.lookup_save({ request_id: 'original-key' })
  const revision: number | null = result.revision
  // @ts-expect-error nullable result cannot be assigned to a definite number
  const unsafe: number = result.revision
  return revision
}
void lookup
''', encoding='utf-8')
    config = {'compilerOptions': {'strict': True, 'exactOptionalPropertyTypes': True, 'noEmit': True,
        'skipLibCheck': True, 'target': 'ES2022', 'module': 'ESNext', 'moduleResolution': 'Bundler',
        'lib': ['ES2022', 'DOM', 'DOM.Iterable'], 'baseUrl': str(tmp_path), 'paths': {
            '@3mm/application-ui/v1': [str(frontend / 'src/extension-ui/application-v1.ts')],
            'vue': [str(frontend / 'node_modules/vue')]}}, 'include': [str(tmp_path / '*.ts')]}
    (tmp_path / 'tsconfig.json').write_text(json.dumps(config), encoding='utf-8')
    result = subprocess.run([node, str(frontend / 'node_modules/typescript/bin/tsc'), '--project', str(tmp_path / 'tsconfig.json')],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def accept_real_generated_client_propagates_unconfirmed_without_retry_or_key_replacement(definition, tmp_path, typescript):
    node, frontend = typescript
    path = tmp_path / 'client.ts'
    path.write_text(client.render_client(definition), encoding='utf-8')
    script = '''const assert = require('node:assert/strict'), fs = require('node:fs')
const ts = require(process.argv[1])
const code = ts.transpileModule(fs.readFileSync(process.argv[2], 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
const moduleFixture = { exports: {} }
new Function('exports', 'module', code)(moduleFixture.exports, moduleFixture)
const original = Object.freeze({ code: 'unconfirmed' }), calls = []
const host = { invoke(...args) { calls.push(args); return Promise.reject(original) } }
const client = moduleFixture.exports.createApplicationClient(host)
;(async () => {
  const payload = { text: 'value', revision: 0 }
  await assert.rejects(client.save_note(payload, { idempotencyKey: 'ORIGINAL' }), value => value === original)
  assert.deepEqual(calls, [['save_note', payload, { idempotencyKey: 'ORIGINAL' }]])
  await assert.rejects(client.read_note({}), value => value === original)
  assert.equal(calls.length, 2)
  assert.deepEqual(calls[1], ['read_note', {}])
})().catch(error => { console.error(error); process.exitCode = 1 })
'''
    result = subprocess.run([node, '-e', script, str(frontend / 'node_modules/typescript/lib/typescript.js'), str(path)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


# The tooling CI job has Python only. These two separate, real-toolchain cases
# are collected only for an expressly selected local acceptance run; missing
# tools then fail rather than producing a skip or a simulated pass.
if os.getenv('THREE_MM_CLIENT_TOOLCHAIN_ACCEPTANCE') == '1':
    test_real_typescript_constraints = accept_real_typescript_enforces_nullable_nested_arrays_enums_maps_and_original_keys
    test_real_one_dispatch_unconfirmed = accept_real_generated_client_propagates_unconfirmed_without_retry_or_key_replacement
