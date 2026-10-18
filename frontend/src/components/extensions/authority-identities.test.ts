import { describe, expect, it } from 'vitest'
import { readAuthorityPlan, readAuthorityStatus } from './authority-management'

const moduleId = 'org.example.identity-reference'
const artifact = 'a'.repeat(64)
const scope = 'platform:installation.identity.read'
const owner = () => ({ core_installation_id: 'inst_' + 'b'.repeat(32), application_installation_id: '7',
  incarnation: 'c'.repeat(32), module_id: moduleId })
// Public RFC 8032 test-vector key with matching SHA-256. No private key/proof.
const publicIdentity = () => ({ identity_version: 1, installation_id: owner().core_installation_id,
  algorithm: 'ed25519', key_id: '21fe31dfa154a261626bf854046fd2271b7bed4b6abe45aa58877ef47f9721b9',
  public_key: '11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=', key_generation: 1, created_at: '2026-10-16T00:12:34.123456Z' })
const resource = () => ({ owner: owner(), package_artifact_sha256: artifact,
  operation: 'installation.identity.read', identity: publicIdentity() })
const status = () => ({ installation_id: 7, mode: 'enforced', installation_status: 'active', installation_enabled: true,
  artifact_sha256: artifact, scopes: [scope], native_reviews: [{ native_review_id: 'd'.repeat(32), revision: 'e'.repeat(32) }],
  grant_state: 'active', grant_record_revision: 'f'.repeat(32), grant_effective: true, isolation_proven: false })
const plan = () => ({ plan_id: '1'.repeat(32), revision: '2'.repeat(32), fingerprint: '3'.repeat(64),
  state: 'review_required', artifact_sha256: artifact, scopes: [scope], expires_in_seconds: 900, isolation_proven: false,
  resources: { commands: [], connectors: [], identities: [resource()] } })
const parse = (value: unknown, current = status()) => readAuthorityPlan(value, readAuthorityStatus(current), moduleId)
const withIdentity = (identity: unknown) => ({ ...plan(), resources: { ...plan().resources, identities: [{ ...resource(), identity }] } })

describe('public installation identity authority response boundaries', () => {
  it('accepts exactly one public own-Core identity read resource without inventing isolation', () => {
    const reviewed = parse(plan())
    expect(reviewed.resources.identities).toHaveLength(1)
    expect(reviewed.resources.identities?.[0]?.identity).toEqual(publicIdentity())
    expect(reviewed.isolation_proven).toBe(false)
  })

  it('preserves older empty resource responses without implicit identity permission', () => {
    const current = { ...status(), scopes: [] }
    expect(parse({ ...plan(), scopes: [], resources: { commands: [], connectors: [] } }, current).scopes).toEqual([])
    expect(() => parse({ ...plan(), resources: { commands: [], connectors: [] } })).toThrow()
    expect(() => parse({ ...plan(), scopes: [], resources: plan().resources }, current)).toThrow()
  })

  it('refuses absent, duplicate, malformed or undeclared identity resources', () => {
    for (const identities of [[], null, {}, [null], [resource(), resource()]]) {
      expect(() => parse({ ...plan(), resources: { ...plan().resources, identities } })).toThrow()
    }
    expect(() => parse({ ...plan(), scopes: [scope, scope] })).toThrow()
    expect(() => parse({ ...plan(), resources: { ...plan().resources, private_identity: [] } })).toThrow()
  })

  it('rejects private/extra data, foreign owners/packages and operations outside read-only scope', () => {
    const original = resource()
    for (const changed of [{ ...original, private_key: 'not-public' }, { ...original, token: 'not-public' },
      { ...original, path: '/etc/3mm' }, { ...original, declaration: {} },
      { ...original, package_artifact_sha256: '9'.repeat(64) },
      { ...original, operation: 'installation.identity.prove' }, { ...original, operation: ['installation.identity.read'] },
      { ...original, owner: { ...owner(), module_id: 'org.example.foreign' } },
      { ...original, owner: { ...owner(), application_installation_id: '8' } },
      { ...original, owner: { ...owner(), core_installation_id: 'inst_' + '9'.repeat(32) } },
      { ...original, owner: { ...owner(), incarnation: '' } },
      { ...original, owner: { ...owner(), token: 'not-public' } }]) {
      expect(() => parse({ ...plan(), resources: { ...plan().resources, identities: [changed] } })).toThrow()
    }
    const { operation: _omitted, ...missing } = original
    expect(() => parse({ ...plan(), resources: { ...plan().resources, identities: [missing] } })).toThrow()
  })

  it('requires exactly the seven public fields and strict versions, algorithm and key shape', () => {
    const original = publicIdentity()
    for (const [field, value] of [
      ['identity_version', true], ['identity_version', '1'], ['identity_version', 2],
      ['key_generation', true], ['key_generation', '1'], ['key_generation', 2],
      ['algorithm', 'rsa'], ['algorithm', ['ed25519']],
      ['installation_id', 'inst_' + '9'.repeat(32)], ['installation_id', 'inst_' + 'b'.repeat(31)],
      ['installation_id', owner().core_installation_id + '\n'],
      ['key_id', 'A'.repeat(64)], ['key_id', 'a'.repeat(63)], ['key_id', ['a'.repeat(64)]],
      ['public_key', original.public_key.slice(0, -1)], ['public_key', original.public_key + '\n'],
      ['public_key', original.public_key.replace('/', '_')],
      ['public_key', original.public_key.slice(0, -2) + 'p='], // Non-zero padding bits.
      ['public_key', original.public_key.slice(0, -2) + '=='], ['public_key', ['A'.repeat(43) + '=']],
    ] as const) {
      expect(() => parse(withIdentity({ ...original, [field]: value }))).toThrow()
    }
    for (const field of ['private_key', 'encrypted_private_key', 'token', 'signature', 'proof']) {
      expect(() => parse(withIdentity({ ...original, [field]: 'not-public' }))).toThrow()
    }
    for (const field of Object.keys(original)) {
      const missing: Record<string, unknown> = { ...original }; delete missing[field]
      expect(() => parse(withIdentity(missing))).toThrow()
    }
  })

  it('accepts calendar-valid UTC ISO strings, including protocol microseconds', () => {
    for (const created_at of ['2026-10-16T00:12:34Z', '2026-10-16T00:12:34+00:00',
      '2026-10-16T00:12:34.123456+00:00', '2024-02-29T23:59:59.1Z', '0001-01-01T00:00:00Z']) {
      expect(parse(withIdentity({ ...publicIdentity(), created_at })).resources.identities?.[0]?.identity.created_at).toBe(created_at)
    }
  })

  it('refuses naive/non-UTC, coerced, malformed or normalized-invalid dates', () => {
    for (const created_at of [null, true, 1792109554, ['2026-10-16T00:12:34Z'],
      '2026-10-16', '2026-10-16T00:12:34', '2026-10-16T00:12:34+02:00', '2026-10-16T00:12:34-00:00',
      '2025-02-29T00:00:00Z', '2026-04-31T00:00:00Z', '2026-10-16T24:00:00Z', '0000-01-01T00:00:00Z',
      '2026-10-16T00:12:60Z', '2026-10-16T00:12:34.1234567Z', '2026-10-16T00:12:34Z\n']) {
      expect(() => parse(withIdentity({ ...publicIdentity(), created_at }))).toThrow()
    }
  })

  it('requires consistent owners across private files, SQL, checkpoints and public identity', () => {
    const files = [{ declaration: { file_contract_version: 1, namespace: 'private_files', mode: 'read',
      max_file_bytes: 128, max_total_bytes: 256, max_files: 2 }, owner: owner(), package_artifact_sha256: artifact, operation: 'read' }]
    const relational = [{ declaration: { contract_version: 1, mode: 'read', limit_class: 'cooperative_v1',
      max_database_bytes: 1048576, auxiliary_pause_bytes: 262144, max_statement_bytes: 2048,
      max_value_bytes: 1024, max_result_bytes: 4096, max_result_rows: 16, max_transaction_ms: 5000, max_busy_ms: 500 },
    owner: owner(), package_artifact_sha256: artifact, service_artifact_sha256: '9'.repeat(64),
    schema_revision: '0001', migration_entrypoint: 'reference_app.migrations:get_migrations',
    resource_profile: 'owned_sqlite_request_v1', operation: 'read' }]
    const checkpoints = [{ declaration: { contract_version: 1, checkpoint_id: 'progress', mode: 'read', max_value_bytes: 4096 },
      owner: owner(), package_artifact_sha256: artifact, operation: 'read' }]
    for (const storage of [{ private_files: files }, { relational }, { checkpoints }, { private_files: files, relational, checkpoints }]) {
      const scopes = [scope, ...('private_files' in storage ? ['storage:private_files_read'] : []),
        ...('relational' in storage ? ['storage:relational_read'] : []), ...('checkpoints' in storage ? ['checkpoint:progress:read'] : [])]
      const current = { ...status(), scopes, grant_effective: false }
      const value = { ...plan(), scopes, resources: { ...plan().resources, ...storage } }
      expect(parse(value, current).resources.identities).toHaveLength(1)
      expect(() => parse({ ...value, resources: { ...value.resources,
        identities: [{ ...resource(), owner: { ...owner(), incarnation: 'other' } }] } }, current)).toThrow()
      const foreign = 'inst_' + '9'.repeat(32)
      expect(() => parse({ ...value, resources: { ...value.resources, identities: [{ ...resource(),
        owner: { ...owner(), core_installation_id: foreign }, identity: { ...publicIdentity(), installation_id: foreign } }] } }, current)).toThrow()
    }
  })

  it('allows only the exact identity read scope and bounds total scopes without accepting history', () => {
    for (const unsupported of ['platform:*', 'platform:installation.identity.prove', 'platform:installation.identity.read\n',
      'platform:installation.peers.read', 'platform:installation.status.read', 'platform:installation.identity.read:write']) {
      expect(() => readAuthorityStatus({ ...status(), scopes: [unsupported] })).toThrow()
    }
    const maximum = [scope, ...Array.from({ length: 196 }, (_, index) => `command:binding_${index}`)]
    expect(readAuthorityStatus({ ...status(), scopes: maximum }).scopes).toHaveLength(197)
    expect(() => readAuthorityStatus({ ...status(), scopes: [...maximum, 'checkpoint:progress:read'] })).toThrow()
    for (const changed of [{ historical: true }, { replayed: true }, { isolation_proven: true }]) {
      expect(() => parse({ ...plan(), ...changed })).toThrow()
    }
    expect(() => readAuthorityPlan(plan(), { ...readAuthorityStatus(status()), review_available: false }, moduleId)).toThrow()
  })
})
