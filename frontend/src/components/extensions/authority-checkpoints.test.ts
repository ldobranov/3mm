import { describe, expect, it } from 'vitest'
import { readAuthorityPlan, readAuthorityStatus } from './authority-management'

// Redacted management metadata, not checkpoint content or executable authority.
const moduleId = 'org.example.checkpoint-reference'
const artifact = 'a'.repeat(64)
const owner = () => ({ core_installation_id: 'inst_' + 'b'.repeat(32), application_installation_id: '7',
  incarnation: 'c'.repeat(32), module_id: moduleId })
const checkpoint = (operation: 'read' | 'write', mode: 'read' | 'read_write' = 'read_write', checkpointId = 'progress') => ({
  declaration: { contract_version: 1, checkpoint_id: checkpointId, mode, max_value_bytes: 4096 },
  owner: owner(), package_artifact_sha256: artifact, operation,
})
const status = (mode: 'read' | 'read_write' = 'read_write') => ({
  installation_id: 7, mode: 'enforced', installation_status: 'active', installation_enabled: true,
  artifact_sha256: artifact, scopes: ['checkpoint:progress:read', ...(mode === 'read_write' ? ['checkpoint:progress:write'] : [])],
  native_reviews: [{ native_review_id: 'd'.repeat(32), revision: 'e'.repeat(32) }],
  grant_state: 'active', grant_record_revision: 'f'.repeat(32), grant_effective: true, isolation_proven: false,
})
const plan = (mode: 'read' | 'read_write' = 'read_write') => ({
  plan_id: '1'.repeat(32), revision: '2'.repeat(32), fingerprint: '3'.repeat(64),
  state: 'review_required', artifact_sha256: artifact, scopes: status(mode).scopes,
  expires_in_seconds: 900, isolation_proven: false,
  resources: { commands: [], connectors: [], checkpoints: mode === 'read' ? [checkpoint('read', mode)] : [checkpoint('read'), checkpoint('write')] },
})
const parse = (value: unknown, current = status()) => readAuthorityPlan(value, readAuthorityStatus(current), moduleId)

describe('checkpoint authority response boundaries', () => {
  it.each(['read', 'read_write'] as const)('accepts exact complete %s bindings', mode => {
    const reviewed = parse(plan(mode), status(mode))
    expect(reviewed.resources.checkpoints).toHaveLength(mode === 'read' ? 1 : 2)
    expect(reviewed.resources.checkpoints?.[0]?.declaration.checkpoint_id).toBe('progress')
  })

  it('preserves older responses without checkpoint declarations', () => {
    const current = { ...status(), scopes: [] }
    expect(parse({ ...plan(), scopes: [], resources: { commands: [], connectors: [] } }, current).scopes).toEqual([])
  })

  it('requires every selected operation once and the whole declared mode per ID', () => {
    for (const entries of [[], [checkpoint('read')], [checkpoint('write')],
      [checkpoint('read'), checkpoint('read')], [checkpoint('write'), checkpoint('write')],
      [checkpoint('read', 'read'), checkpoint('write', 'read')],
      [checkpoint('read'), checkpoint('write', 'read_write', 'foreign')]]) {
      expect(() => parse({ ...plan(), resources: { ...plan().resources, checkpoints: entries } })).toThrow()
    }
    const { checkpoints: _omitted, ...missing } = plan().resources
    expect(() => parse({ ...plan(), resources: missing })).toThrow()
    expect(() => parse({ ...plan(), scopes: ['checkpoint:progress:read'] })).toThrow()
  })

  it('rejects unknown fields, payloads, paths, foreign owners/packages and coerced enums', () => {
    const original = checkpoint('write')
    for (const changed of [null, { ...original, value: { token: 'secret' } }, { ...original, path: '/var/lib/3mm' },
      { ...original, operation: 'delete' }, { ...original, operation: ['write'] },
      { ...original, package_artifact_sha256: '0'.repeat(64) },
      { ...original, owner: { ...owner(), module_id: 'org.example.foreign' } },
      { ...original, owner: { ...owner(), application_installation_id: '8' } },
      { ...original, owner: { ...owner(), core_installation_id: 'foreign' } },
      { ...original, owner: { ...owner(), incarnation: 'foreign' } },
      { ...original, owner: { ...owner(), path: '/tmp' } },
      { ...original, declaration: { ...original.declaration, contract_version: true } },
      { ...original, declaration: { ...original.declaration, contract_version: 2 } },
      { ...original, declaration: { ...original.declaration, mode: ['read_write'] } },
      { ...original, declaration: { ...original.declaration, mode: 'write' } },
      { ...original, declaration: { ...original.declaration, max_value_bytes: 4097 } },
      { ...original, declaration: { ...original.declaration, payload: {} } }]) {
      expect(() => parse({ ...plan(), resources: { ...plan().resources, checkpoints: [checkpoint('read'), changed] } })).toThrow()
    }
    const { owner: _omitted, ...missing } = original
    expect(() => parse({ ...plan(), resources: { ...plan().resources, checkpoints: [checkpoint('read'), missing] } })).toThrow()
  })

  it('validates exact ID grammar and integer value bounds without coercion', () => {
    for (const checkpointId of ['', 'Progress', '_progress', '../progress', '*', 'a'.repeat(97), 'progress\n', ['progress']]) {
      const entries = [checkpoint('read'), checkpoint('write')].map(item => ({ ...item,
        declaration: { ...item.declaration, checkpoint_id: checkpointId } }))
      expect(() => parse({ ...plan(), resources: { ...plan().resources, checkpoints: entries } })).toThrow()
    }
    for (const maximum of [0, 262145, true, '4096', 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
      const entries = [checkpoint('read'), checkpoint('write')].map(item => ({ ...item,
        declaration: { ...item.declaration, max_value_bytes: maximum } }))
      expect(() => parse({ ...plan(), resources: { ...plan().resources, checkpoints: entries } })).toThrow()
    }
    for (const maximum of [1, 262144]) {
      const entries = [checkpoint('read'), checkpoint('write')].map(item => ({ ...item,
        declaration: { ...item.declaration, max_value_bytes: maximum } }))
      expect(parse({ ...plan(), resources: { ...plan().resources, checkpoints: entries } }).resources.checkpoints).toHaveLength(2)
    }
  })

  it('requires one owner across checkpoint IDs, private files and SQL resources', () => {
    const file = { declaration: { file_contract_version: 1, namespace: 'private_files', mode: 'read',
      max_file_bytes: 128, max_total_bytes: 256, max_files: 2 }, owner: owner(), package_artifact_sha256: artifact, operation: 'read' }
    const database = { declaration: { contract_version: 1, mode: 'read', limit_class: 'cooperative_v1',
      max_database_bytes: 1048576, auxiliary_pause_bytes: 262144, max_statement_bytes: 2048,
      max_value_bytes: 1024, max_result_bytes: 4096, max_result_rows: 16, max_transaction_ms: 5000, max_busy_ms: 500 },
    owner: owner(), package_artifact_sha256: artifact, service_artifact_sha256: '9'.repeat(64),
    schema_revision: '0001', migration_entrypoint: 'reference_app.migrations:get_migrations',
    resource_profile: 'owned_sqlite_request_v1', operation: 'read' }
    const current = { ...status(), scopes: [...status().scopes, 'checkpoint:cursor:read', 'storage:private_files_read', 'storage:relational_read'] }
    const entries = [...plan().resources.checkpoints, checkpoint('read', 'read', 'cursor')]
    const resources = { ...plan().resources, checkpoints: entries, private_files: [file], relational: [database] }
    expect(parse({ ...plan(), scopes: current.scopes, resources }, current).resources.checkpoints).toHaveLength(3)
    for (const field of ['core_installation_id', 'incarnation'] as const) {
      const changed = entries.map(item => ({ ...item, owner: { ...item.owner, [field]: 'other' } }))
      expect(() => parse({ ...plan(), scopes: current.scopes, resources: { ...resources, checkpoints: changed } }, current)).toThrow()
      const differentId = [...entries.slice(0, 2), { ...entries[2], owner: { ...owner(), [field]: 'other' } }]
      expect(() => parse({ ...plan(), scopes: current.scopes, resources: { ...resources, checkpoints: differentId } }, current)).toThrow()
    }
    // SQL alone also pins the owner, without depending on a private-file entry.
    const sqlCurrent = { ...current, scopes: current.scopes.filter(key => key !== 'storage:private_files_read') }
    expect(() => parse({ ...plan(), scopes: sqlCurrent.scopes, resources: { ...resources, private_files: [],
      checkpoints: entries.map(item => ({ ...item, owner: { ...owner(), incarnation: 'other' } })) } }, sqlCurrent)).toThrow()
  })

  it('supports at most 32 checkpoint declarations and 64 operation entries', () => {
    const entries = Array.from({ length: 32 }, (_, index) => [checkpoint('read', 'read_write', `value_${index}`), checkpoint('write', 'read_write', `value_${index}`)]).flat()
    const current = { ...status(), scopes: entries.map(item => `checkpoint:${item.declaration.checkpoint_id}:${item.operation}`) }
    expect(parse({ ...plan(), scopes: current.scopes, resources: { ...plan().resources, checkpoints: entries } }, current).resources.checkpoints).toHaveLength(64)
    const overflow = [...entries, checkpoint('read', 'read', 'extra')]
    const overflowStatus = { ...current, scopes: [...current.scopes, 'checkpoint:extra:read'] }
    expect(() => parse({ ...plan(), scopes: overflowStatus.scopes, resources: { ...plan().resources, checkpoints: overflow } }, overflowStatus)).toThrow()
    const tooManyIds = Array.from({ length: 33 }, (_, index) => checkpoint('read', 'read', `value_${index}`))
    const tooManyStatus = { ...status(), scopes: tooManyIds.map(item => `checkpoint:${item.declaration.checkpoint_id}:read`) }
    expect(() => parse({ ...plan(), scopes: tooManyStatus.scopes, resources: { ...plan().resources, checkpoints: tooManyIds } }, tooManyStatus)).toThrow()
  })

  it('retains bounded full-scope grammar, status-only and historical denials', () => {
    for (const scope of ['checkpoint:progress', 'checkpoint:*:read', 'checkpoint:progress:delete', 'checkpoint:Progress:read', 'checkpoint:progress:write\n']) {
      expect(() => readAuthorityStatus({ ...status(), scopes: [scope] })).toThrow()
    }
    const maximum = Array.from({ length: 197 }, (_, index) => `command:binding_${index}`)
    expect(readAuthorityStatus({ ...status(), scopes: maximum }).scopes).toHaveLength(197)
    expect(() => readAuthorityStatus({ ...status(), scopes: [...maximum, 'checkpoint:progress:read'] })).toThrow()
    for (const changed of [{ historical: true }, { replayed: true }, { isolation_proven: true }]) {
      expect(() => parse({ ...plan(), ...changed })).toThrow()
    }
    expect(() => readAuthorityPlan(plan(), { ...readAuthorityStatus(status()), review_available: false }, moduleId)).toThrow()
  })
})
