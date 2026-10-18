import { describe, expect, it } from 'vitest'
import { readAuthorityPlan, readAuthorityStatus } from './authority-management'

const moduleId = 'org.example.status-reference'
const link = 'peer_' + 'a'.repeat(32)
const scope = `status:${link}:read`
const artifact = 'a'.repeat(64)
const owner = () => ({ core_installation_id: 'inst_' + 'b'.repeat(32), application_installation_id: '7', incarnation: 'c'.repeat(32), module_id: moduleId })
const sender = () => ({ identity_version: 1, installation_id: owner().core_installation_id, algorithm: 'ed25519',
  key_id: '21fe31dfa154a261626bf854046fd2271b7bed4b6abe45aa58877ef47f9721b9',
  public_key: '11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=', key_generation: 1, created_at: '2026-10-16T12:00:00Z' })
const receiver = () => ({ ...sender(), installation_id: 'inst_' + '8'.repeat(32),
  key_id: '515a733d7320b35b2117893952f93a9400dc4d5ca8bb6972453cae4cab993a07', public_key: 'cnJy'.repeat(10) + 'cnI=' })
const resource = () => ({ owner: owner(), package_artifact_sha256: artifact, operation: 'installation.status.read',
  link_id: link, application_instance_id: 'd'.repeat(24), sender_identity: sender(), receiver_identity: receiver(),
  origin: 'https://receiver.example', target_module_id: 'org.example.receiver', consent_revision: 2,
  consent: { consent_version: 1, summary_fields: ['core_version'], node_ids: ['dev_' + 'e'.repeat(32)], node_fields: ['online', 'display_name'] } })
const status = () => ({ installation_id: 7, mode: 'enforced', installation_status: 'active', installation_enabled: true,
  artifact_sha256: artifact, scopes: [scope], native_reviews: [{ native_review_id: '1'.repeat(32), revision: '2'.repeat(32) }],
  grant_state: 'active', grant_record_revision: '3'.repeat(32), grant_effective: true, isolation_proven: false })
const plan = () => ({ plan_id: '4'.repeat(32), revision: '5'.repeat(32), fingerprint: '6'.repeat(64),
  state: 'review_required', artifact_sha256: artifact, scopes: [scope], expires_in_seconds: 900, isolation_proven: false,
  resources: { commands: [], connectors: [], status_projections: [resource()] } })
const parse = (value: unknown, current = status()) => readAuthorityPlan(value, readAuthorityStatus(current), moduleId)
const withResource = (item: unknown) => ({ ...plan(), resources: { ...plan().resources, status_projections: [item] } })

describe('exact existing local status projection response', () => {
  it('accepts one exact public binding without claiming remote trust or isolation', () => {
    expect(parse(plan()).resources.status_projections?.[0]?.receiver_identity).toEqual(receiver())
    expect(parse(plan()).isolation_proven).toBe(false)
  })

  it('keeps older empty and identity responses closed to implicit status rights', () => {
    const current = { ...status(), scopes: [] }
    expect(parse({ ...plan(), scopes: [], resources: { commands: [], connectors: [] } }, current).scopes).toEqual([])
    expect(() => parse({ ...plan(), resources: { commands: [], connectors: [] } })).toThrow()
    expect(() => parse({ ...plan(), scopes: [], resources: plan().resources }, current)).toThrow()
  })

  it('rejects foreign owner/package/instance, wider operations and hidden credential fields', () => {
    const original = resource()
    for (const changed of [{ ...original, credential: {} }, { ...original, path: '/etc/3mm' }, { ...original, token: 'never' },
      { ...original, operation: 'installation.peers.report' }, { ...original, package_artifact_sha256: 'f'.repeat(64) },
      { ...original, link_id: 'peer_*' }, { ...original, link_id: link + '\n' }, { ...original, application_instance_id: 'd'.repeat(32) },
      { ...original, owner: { ...owner(), module_id: 'org.example.foreign' } },
      { ...original, owner: { ...owner(), application_installation_id: '8' } },
      { ...original, owner: { ...owner(), core_installation_id: 'inst_' + '9'.repeat(32) } },
      { ...original, consent_revision: true }, { ...original, consent_revision: '2' }, { ...original, consent_revision: 0 },
      { ...original, consent_revision: Number.MAX_SAFE_INTEGER + 1 }, { ...original, target_module_id: 'invalid' }]) {
      expect(() => parse(withResource(changed))).toThrow()
    }
    for (const field of Object.keys(original)) {
      const changed: Record<string, unknown> = { ...original }; delete changed[field]
      expect(() => parse(withResource(changed))).toThrow()
    }
  })

  it('requires exact public identities and UTC timestamps, never proofs/private keys', () => {
    for (const name of ['sender_identity', 'receiver_identity'] as const) {
      for (const changes of [{ private_key: 'never' }, { proof: {} }, { key_generation: 2 }, { identity_version: true },
        { public_key: 'invalid' }, { key_id: 'f'.repeat(63) }, { algorithm: 'rsa' },
        { created_at: '2025-02-29T00:00:00Z' }, { created_at: '2026-01-01T00:00:00+02:00' }]) {
        expect(() => parse(withResource({ ...resource(), [name]: { ...resource()[name], ...changes } }))).toThrow()
      }
    }
    expect(() => parse(withResource({ ...resource(), receiver_identity: sender() }))).toThrow()
  })

  it('allows only canonical bounded HTTPS origins, without treating them as remote approval', () => {
    for (const origin of ['http://receiver.example', 'https://receiver.example/path', 'https://receiver.example/',
      'https://user:pass@receiver.example', 'https://receiver.example?x=1', 'https://receiver.example#f',
      'https://receiver.example:443', 'https://receiver.example:0', 'https://UPPER.example',
      'https://bad..example', 'https://under_score.example', 'https://-bad.example', 'https://receiver.example\n']) {
      expect(() => parse(withResource({ ...resource(), origin }))).toThrow()
    }
    for (const origin of ['https://receiver.example', 'https://receiver.example:8443', 'https://127.0.0.1:8443', 'https://[::1]:8443']) {
      expect(parse(withResource({ ...resource(), origin })).resources.status_projections?.[0]?.origin).toBe(origin)
    }
  })

  it('requires exact finite unique consent sets and consistent selected node fields', () => {
    for (const consent of [{}, null, { ...resource().consent, consent_version: true }, { ...resource().consent, extra: [] },
      { ...resource().consent, summary_fields: ['credential'] }, { ...resource().consent, node_ids: ['foreign'] },
      { ...resource().consent, node_ids: [] }, { ...resource().consent, node_fields: [] },
      { ...resource().consent, node_fields: ['online', 'online'] }, { ...resource().consent, summary_fields: ['core_version', 'core_version'] },
      { ...resource().consent, node_fields: 'online' }, { ...resource().consent, node_fields: ['credential'] },
      { ...resource().consent, node_ids: Array.from({ length: 65 }, (_, index) => 'dev_' + index.toString(16).padStart(32, '0')) }]) {
      expect(() => parse(withResource({ ...resource(), consent }))).toThrow()
    }
    const consent = { consent_version: 1, summary_fields: [], node_ids: [], node_fields: [] }
    expect(parse(withResource({ ...resource(), consent })).resources.status_projections?.[0]?.consent).toEqual(consent)
  })

  it('bounds complete link sets and does not reuse a read scope for another link', () => {
    for (const status_projections of [[], null, {}, [null], [resource(), resource()]]) {
      expect(() => parse({ ...plan(), resources: { ...plan().resources, status_projections } })).toThrow()
    }
    for (const changed of [{ historical: true }, { replayed: true }, { isolation_proven: true }]) {
      expect(() => parse({ ...plan(), ...changed })).toThrow()
    }
    const projections = Array.from({ length: 32 }, (_, index) => ({ ...resource(), link_id: 'peer_' + index.toString(16).padStart(32, '0') }))
    const scopes = projections.map(item => `status:${item.link_id}:read`)
    const value = { ...plan(), scopes, resources: { ...plan().resources, status_projections: projections } }
    expect(parse(value, { ...status(), scopes }).resources.status_projections).toHaveLength(32)
    const extra = { ...resource(), link_id: 'peer_' + 'f'.repeat(32) }
    expect(() => parse({ ...value, scopes: [...scopes, `status:${extra.link_id}:read`],
      resources: { ...value.resources, status_projections: [...projections, extra] } },
    { ...status(), scopes: [...scopes, `status:${extra.link_id}:read`] })).toThrow()
    for (const changed of [{ ...projections[1], application_instance_id: 'f'.repeat(24) },
      { ...projections[1], owner: { ...owner(), incarnation: 'foreign' } },
      { ...projections[1], sender_identity: { ...sender(), created_at: '2026-10-17T12:00:00Z' } }]) {
      expect(() => parse({ ...value, resources: { ...value.resources, status_projections: [projections[0], changed, ...projections.slice(2)] } }, { ...status(), scopes })).toThrow()
    }
  })

  it('supports mixed identity/status only with the same exact public Core sender', () => {
    const identities = [{ owner: owner(), package_artifact_sha256: artifact, operation: 'installation.identity.read', identity: sender() }]
    const scopes = [scope, 'platform:installation.identity.read']
    const value = { ...plan(), scopes, resources: { ...plan().resources, identities } }
    expect(parse(value, { ...status(), scopes }).resources.identities).toHaveLength(1)
    expect(() => parse({ ...value, resources: { ...value.resources, identities: [{ ...identities[0], identity: { ...sender(), created_at: '2026-10-17T12:00:00Z' } }] } }, { ...status(), scopes })).toThrow()
  })

  it('retains old scope ceilings and refuses wildcards or new reporting authority', () => {
    for (const unsupported of ['status:*:read', `status:${link}:write`, 'platform:installation.status.read', `${scope}\n`, 'platform:installation.peers.report']) {
      expect(() => readAuthorityStatus({ ...status(), scopes: [unsupported] })).toThrow()
    }
    const maximum = [scope, ...Array.from({ length: 228 }, (_, index) => `command:binding_${index}`)]
    expect(readAuthorityStatus({ ...status(), scopes: maximum }).scopes).toHaveLength(229)
    expect(() => readAuthorityStatus({ ...status(), scopes: [...maximum, 'checkpoint:progress:read'] })).toThrow()
  })
})
