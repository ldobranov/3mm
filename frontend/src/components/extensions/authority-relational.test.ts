import { describe, expect, it } from 'vitest'
import { readAuthorityPlan, readAuthorityStatus } from './authority-management'

// Core-redacted review DTOs only; these fixtures grant no runtime authority.
const moduleId = 'org.example.relational-reference'
const artifact = '8'.repeat(64)
const owner = () => ({
  core_installation_id: 'inst_' + 'a'.repeat(32),
  application_installation_id: '5', incarnation: 'b'.repeat(32), module_id: moduleId,
})
const declaration = (mode: 'read' | 'read_write' = 'read_write') => ({
  contract_version: 1, mode, limit_class: 'cooperative_v1', max_database_bytes: 1048576,
  auxiliary_pause_bytes: 262144, max_statement_bytes: 2048, max_value_bytes: 1024,
  max_result_bytes: 4096, max_result_rows: 16, max_transaction_ms: 5000, max_busy_ms: 500,
})
const relational = (operation: 'read' | 'write', mode: 'read' | 'read_write' = 'read_write') => ({
  declaration: declaration(mode), owner: owner(), package_artifact_sha256: artifact,
  service_artifact_sha256: 'c'.repeat(64), schema_revision: '0002',
  migration_entrypoint: 'reference_app.migrations:get_migrations',
  resource_profile: 'owned_sqlite_request_v1', operation,
})
const file = () => ({
  declaration: { file_contract_version: 1, namespace: 'private_files', mode: 'read',
    max_file_bytes: 128, max_total_bytes: 256, max_files: 2 },
  owner: owner(), package_artifact_sha256: artifact, operation: 'read',
})
const status = (mode: 'read' | 'read_write' = 'read_write', files = false) => ({
  installation_id: 5, mode: 'enforced', installation_status: 'active', installation_enabled: true,
  artifact_sha256: artifact,
  scopes: ['storage:relational_read', ...(mode === 'read_write' ? ['storage:relational_write'] : []),
    ...(files ? ['storage:private_files_read'] : [])],
  native_reviews: [{ native_review_id: 'd'.repeat(32), revision: 'e'.repeat(32) }],
  grant_revision: 15, grant_record_revision: 'f'.repeat(32), grant_state: 'active',
  grant_effective: false, review_available: true, review_blockers: [],
  execution_class: 'reviewed_native_only', isolation_proven: false,
  runtime_blockers: ['relational_runtime_unavailable'],
})
const plan = (mode: 'read' | 'read_write' = 'read_write', files = false) => ({
  plan_id: '1'.repeat(32), revision: '2'.repeat(32), fingerprint: '3'.repeat(64),
  state: 'review_required', scopes: status(mode, files).scopes, artifact_sha256: artifact,
  expires_in_seconds: 900, isolation_proven: false,
  resources: { commands: [], connectors: [], events: [], publications: [],
    private_files: files ? [file()] : [],
    relational: mode === 'read' ? [relational('read', mode)] : [relational('read'), relational('write')] },
})
const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T

describe('relational authority response boundaries', () => {
  it.each(['read', 'read_write'] as const)('accepts the exact complete %s profile without inferring effective runtime rights', mode => {
    const current = readAuthorityStatus(status(mode))
    expect(current.grant_effective).toBe(false)
    expect(current.runtime_blockers).toEqual(['relational_runtime_unavailable'])
    expect(current.review_available).toBe(true)
    const reviewed = readAuthorityPlan(plan(mode), current, moduleId)
    expect(reviewed.resources.relational).toHaveLength(mode === 'read' ? 1 : 2)
    expect(reviewed.resources.relational?.[0]?.schema_revision).toBe('0002')
    expect(current.grant_effective).toBe(false)
  })

  it('supports older status DTOs without the additive runtime-blocker field', () => {
    const { runtime_blockers: _omitted, ...older } = status()
    expect(readAuthorityStatus(older).grant_effective).toBe(false)
  })

  it.each(['read', 'read_write'] as const)('accepts an explicitly confirmed %s runtime without inventing grants', mode => {
    const current = readAuthorityStatus({ ...status(mode), grant_effective: true, runtime_blockers: [] })
    expect(current.grant_effective).toBe(true)
    expect(readAuthorityPlan(plan(mode), current, moduleId).resources.relational)
      .toHaveLength(mode === 'read' ? 1 : 2)
  })

  it('rejects malformed, unknown or contradictory runtime evidence', () => {
    for (const blockers of [null, 'relational_runtime_unavailable', [null], [true],
      ['unrecognized'], ['relational_runtime_unavailable', 'relational_runtime_unavailable']]) {
      expect(() => readAuthorityStatus({ ...status(), runtime_blockers: blockers })).toThrow()
    }
    expect(() => readAuthorityStatus({ ...status(), grant_effective: true })).toThrow()
  })

  it('keeps private-file and relational scopes separate while requiring the same owner', () => {
    const current = readAuthorityStatus(status('read_write', true))
    const reviewed = plan('read_write', true)
    expect(readAuthorityPlan(reviewed, current, moduleId).resources.private_files).toHaveLength(1)
    expect(readAuthorityPlan(reviewed, current, moduleId).resources.relational).toHaveLength(2)
    // Both DB operations agree with each other, but not the file namespace.
    for (const key of ['core_installation_id', 'incarnation'] as const) {
      const changed = copy(reviewed)
      changed.resources.relational.forEach(item => { item.owner[key] = 'foreign_' + '9'.repeat(32) })
      expect(() => readAuthorityPlan(changed, current, moduleId)).toThrow()
    }
  })

  it('requires every selected resource once and the whole declared relational mode', () => {
    const current = readAuthorityStatus(status())
    for (const resources of [[], [relational('read')], [relational('write')],
      [relational('read'), relational('read')], [relational('write'), relational('write')]]) {
      expect(() => readAuthorityPlan({ ...plan(), resources: { ...plan().resources, relational: resources } }, current, moduleId)).toThrow()
    }
    const { relational: _omitted, ...missing } = plan().resources
    expect(() => readAuthorityPlan({ ...plan(), resources: missing }, current, moduleId)).toThrow()
    expect(() => readAuthorityPlan({ ...plan(), scopes: ['storage:relational_read'] }, current, moduleId)).toThrow()
    expect(() => readAuthorityPlan({ ...plan(), resources: { ...plan().resources,
      relational: [relational('read', 'read'), relational('write', 'read')] } }, current, moduleId)).toThrow()
  })

  it('rejects foreign, altered, path-bearing or unsupported exact bindings', () => {
    const current = readAuthorityStatus(status())
    const original = relational('write')
    const invalid: unknown[] = [null, { ...original, operation: 'delete' },
      { ...original, path: '/var/lib/3mm/core/3mm.db' },
      { ...original, package_artifact_sha256: '9'.repeat(64) },
      { ...original, service_artifact_sha256: 'invalid' },
      { ...original, service_artifact_sha256: '9'.repeat(64) },
      { ...original, resource_profile: 'unlimited' },
      { ...original, schema_revision: '0003' }, { ...original, schema_revision: '../0002' },
      { ...original, schema_revision: 'a'.repeat(65) },
      { ...original, migration_entrypoint: 'reference_app:other_migrations' },
      { ...original, migration_entrypoint: '/opt/3mm/current:migrations' },
      { ...original, migration_entrypoint: 'a'.repeat(240) + ':m' },
      { ...original, owner: { ...original.owner, application_installation_id: '6' } },
      { ...original, owner: { ...original.owner, module_id: 'org.example.foreign' } },
      { ...original, owner: { ...original.owner, core_installation_id: 'foreign_core' } },
      { ...original, owner: { ...original.owner, incarnation: 'foreign_incarnation' } },
      { ...original, owner: { ...original.owner, path: '/var/lib/3mm' } },
      { ...original, declaration: { ...original.declaration, contract_version: true } },
      { ...original, declaration: { ...original.declaration, limit_class: 'isolated' } },
      { ...original, declaration: { ...original.declaration, mode: 'write' } },
      { ...original, declaration: { ...original.declaration, path: '/tmp/arbitrary.sqlite3' } }]
    for (const changed of invalid) {
      expect(() => readAuthorityPlan({ ...plan(), resources: { ...plan().resources,
        relational: [relational('read'), changed] } }, current, moduleId)).toThrow()
    }
    const { service_artifact_sha256: _omitted, ...missing } = original
    expect(() => readAuthorityPlan({ ...plan(), resources: { ...plan().resources,
      relational: [relational('read'), missing] } }, current, moduleId)).toThrow()
  })

  it('does not coerce JSON arrays into relational enum strings', () => {
    const current = readAuthorityStatus(status())
    const arrayMode = [relational('read'), relational('write')].map(item => ({ ...item,
      declaration: { ...item.declaration, mode: ['read_write'] } }))
    expect(() => readAuthorityPlan({ ...plan(), resources: { ...plan().resources,
      relational: arrayMode } }, current, moduleId)).toThrow()
    expect(() => readAuthorityPlan({ ...plan(), resources: { ...plan().resources,
      relational: [relational('read'), { ...relational('write'), operation: ['write'] }] } }, current, moduleId)).toThrow()
  })

  it('validates every numeric bound and rejects boolean, nonfinite and incoherent limits', () => {
    const current = readAuthorityStatus(status())
    const invalid = {
      max_database_bytes: [65535, 268435457], auxiliary_pause_bytes: [65535, 67108865],
      max_statement_bytes: [0, 65537], max_value_bytes: [0, 1048577],
      max_result_bytes: [0, 1048577], max_result_rows: [0, 1001],
      max_transaction_ms: [99, 30001], max_busy_ms: [-1, 5001],
    }
    for (const [field, values] of Object.entries(invalid)) {
      for (const value of [...values, true, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
        const resources = ['read', 'write'].map(operation => ({ ...relational(operation as 'read' | 'write'),
          declaration: { ...declaration(), [field]: value } }))
        expect(() => readAuthorityPlan({ ...plan(), resources: { ...plan().resources, relational: resources } }, current, moduleId)).toThrow()
      }
    }
    for (const limits of [
      { max_value_bytes: 4097, max_result_bytes: 4096 },
      { max_database_bytes: 65536, max_value_bytes: 65537, max_result_bytes: 65537 },
      { max_transaction_ms: 100, max_busy_ms: 101 },
    ]) {
      const resources = [relational('read'), relational('write')].map(item => ({ ...item,
        declaration: { ...item.declaration, ...limits } }))
      expect(() => readAuthorityPlan({ ...plan(), resources: { ...plan().resources, relational: resources } }, current, moduleId)).toThrow()
    }
  })

  it('accepts inclusive numeric boundaries, including a zero busy-wait budget', () => {
    const current = readAuthorityStatus(status())
    for (const limits of [
      { max_database_bytes: 65536, auxiliary_pause_bytes: 65536, max_statement_bytes: 1,
        max_value_bytes: 1, max_result_bytes: 1, max_result_rows: 1,
        max_transaction_ms: 100, max_busy_ms: 0 },
      { max_database_bytes: 268435456, auxiliary_pause_bytes: 67108864, max_statement_bytes: 65536,
        max_value_bytes: 1048576, max_result_bytes: 1048576, max_result_rows: 1000,
        max_transaction_ms: 30000, max_busy_ms: 5000 },
    ]) {
      const resources = [relational('read'), relational('write')].map(item => ({ ...item,
        declaration: { ...item.declaration, ...limits } }))
      expect(readAuthorityPlan({ ...plan(), resources: { ...plan().resources, relational: resources } }, current, moduleId).resources.relational).toHaveLength(2)
    }
  })

  it('retains exact scope grammar, historical-result and isolation denials', () => {
    for (const scope of ['storage:relational', 'storage:relational_*', 'storage:relational_migrate',
      'storage:relational_write\n', 'storage:any_read']) {
      expect(() => readAuthorityStatus({ ...status(), scopes: [scope] })).toThrow()
    }
    const current = readAuthorityStatus(status())
    for (const changed of [{ historical: true }, { replayed: true }, { isolation_proven: true }]) {
      expect(() => readAuthorityPlan({ ...plan(), ...changed }, current, moduleId)).toThrow()
    }
    expect(() => readAuthorityPlan({ ...plan(), resources: { ...plan().resources, other_databases: [] } }, current, moduleId)).toThrow()
  })
})
