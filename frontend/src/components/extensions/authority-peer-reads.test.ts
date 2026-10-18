import { describe, expect, it } from 'vitest'
import { readAuthorityPlan, readAuthorityStatus } from './authority-management'
import { peerArtifact, peerModuleId, peerOwner, peerPlan, peerResource, peerResources, peerScopes, peerSender, peerStatus } from './authority-peer-reads.fixtures'

const parse = (value: unknown, current = peerStatus(), requested?: string[]) => readAuthorityPlan(value, readAuthorityStatus(current), peerModuleId, requested)
const withResource = (item: unknown) => ({ ...peerPlan(), resources: { ...peerPlan().resources, peer_reads: [item, peerResources()[1]] } })

describe('closed outbound peer-read management contract', () => {
  it.each([[], [peerScopes()[0]!], peerScopes()].map(selected => ({ selected })))('accepts exact optional selection $selected while retaining all public bindings', ({ selected }) => {
    const result = parse(peerPlan(selected), peerStatus(), selected)
    expect(result.scopes).toEqual(selected)
    expect(result.resources.peer_reads).toHaveLength(2)
    expect(result.resources.peer_reads?.map(item => item.peer_version)).toEqual([1, 2])
    expect(result.isolation_proven).toBe(false)
  })

  it('requires the server to echo precisely the requested selection, never a wider or narrower one', () => {
    expect(() => parse(peerPlan(), peerStatus(), [])).toThrow()
    expect(() => parse(peerPlan([]), peerStatus(), peerScopes())).toThrow()
    expect(() => parse(peerPlan(['peer:unknown:read']))).toThrow()
  })

  it.each(['declaration', 'owner', 'package_artifact_sha256', 'service_artifact_sha256', 'application_instance_id',
    'peer_id', 'peer_version', 'sender_identity', 'receiver_identity', 'origin', 'target_module_id', 'consent_revision', 'consent', 'enrollment_metadata'])(
    'refuses a missing %s even on an unselected link', field => {
      const item: Record<string, unknown> = { ...peerResource() }; delete item[field]
      expect(() => parse({ ...withResource(item), scopes: [] })).toThrow()
    })

  it.each(['credential', 'token', 'private_key', 'start_request', 'state', 'generation', 'remote_binding_id', 'path'])(
    'does not render unexpected %s observations or secrets', field => {
      expect(() => parse(withResource({ ...peerResource(), [field]: 'MUST_NOT_RENDER' }))).toThrow()
    })

  it('requires all declared links, unique logical names/config fields/resolved peers and at most 32 links', () => {
    for (const peer_reads of [[], null, {}, [null], [peerResource()], [peerResource(), peerResource()],
      [peerResource(), { ...peerResources()[1], peer_id: peerResource().peer_id }],
      [peerResource(), { ...peerResources()[1], declaration: { ...peerResources()[1]!.declaration, peer_id_config_key: 'REMOTE_LINK' } }]]) {
      expect(() => parse({ ...peerPlan([]), resources: { ...peerPlan().resources, peer_reads } })).toThrow()
    }
    const peers = Array.from({ length: 32 }, (_, index) => ({ ...peerResource(1, `link_${index}`), peer_id: 'peer_' + index.toString(16).padStart(32, '0') }))
    const scopes = peers.map(item => `peer:${item.declaration.binding_id}:read`)
    expect(parse({ ...peerPlan([]), resources: { ...peerPlan().resources, peer_reads: peers } }, { ...peerStatus(), scopes }).resources.peer_reads).toHaveLength(32)
    const extra = { ...peerResource(1, 'extra'), peer_id: 'peer_' + '9'.repeat(32) }
    expect(() => parse({ ...peerPlan([]), resources: { ...peerPlan().resources, peer_reads: [...peers, extra] } },
      { ...peerStatus(), scopes: [...scopes, 'peer:extra:read'] })).toThrow()
  })

  it('refuses foreign owner/package/service/instance and incoherent public identities', () => {
    for (const item of [{ ...peerResource(), owner: { ...peerOwner(), module_id: 'org.example.foreign' } },
      { ...peerResource(), owner: { ...peerOwner(), application_installation_id: '8' } },
      { ...peerResource(), owner: { ...peerOwner(), incarnation: '9'.repeat(32) } },
      { ...peerResource(), package_artifact_sha256: '9'.repeat(64) }, { ...peerResource(), service_artifact_sha256: '9'.repeat(64) },
      { ...peerResource(), application_instance_id: '9'.repeat(24) },
      { ...peerResource(), sender_identity: { ...peerSender(), created_at: '2026-10-17T12:00:00Z' } },
      { ...peerResource(), receiver_identity: peerSender() },
      { ...peerResource(), sender_identity: { ...peerSender(), private_key: 'SECRET' } },
      { ...peerResource(), receiver_identity: { ...peerResource().receiver_identity, proof: {} } }]) {
      expect(() => parse(withResource(item))).toThrow()
    }
  })

  it('refuses inbound, wider actions, malformed configuration references and raw-ID scope substitution', () => {
    for (const declaration of [{ ...peerResource().declaration, direction: 'inbound' },
      { ...peerResource().declaration, operations: ['read', 'report'] }, { ...peerResource().declaration, operations: [] },
      { ...peerResource().declaration, operations: ['enroll'] }, { ...peerResource().declaration, binding_id: '*' },
      { ...peerResource().declaration, binding_id: 'remote_link\n' }, { ...peerResource().declaration, contract_version: true },
      { ...peerResource().declaration, peer_id_config_key: 'remote_link' }, { ...peerResource().declaration, peer_id_config_key: 'REMOTE_LINK\n' },
      { ...peerResource().declaration, extra: true }]) expect(() => parse(withResource({ ...peerResource(), declaration }))).toThrow()
    for (const scope of ['peer:*:read', 'peer:remote_link:write', 'peer:remote_link:report', 'peer:remote_link:read\n']) {
      expect(() => readAuthorityStatus({ ...peerStatus(), scopes: [scope] })).toThrow()
    }
    const substituted = `peer:${peerResource().peer_id}:read`
    expect(() => parse(peerPlan([substituted]), { ...peerStatus(), scopes: [substituted, peerScopes()[1]!] })).toThrow()
  })

  it('requires exact normalized bounded consent and matching version-2 metadata, without claiming hash verification', () => {
    for (const consent of [null, {}, { ...peerResource().consent, extra: [] }, { ...peerResource().consent, consent_version: true },
      { ...peerResource().consent, summary_fields: ['sdk_version', 'core_version'] },
      { ...peerResource().consent, summary_fields: ['core_version', 'core_version'] },
      { ...peerResource().consent, node_fields: ['credential'] }, { ...peerResource().consent, node_ids: [] },
      { ...peerResource().consent, node_fields: [] }, { ...peerResource().consent, node_ids: ['dev_' + 'e'.repeat(32) + '\n'] },
      { ...peerResource().consent, node_ids: Array.from({ length: 65 }, (_, index) => 'dev_' + index.toString(16).padStart(32, '0')) }]) {
      expect(() => parse(withResource({ ...peerResource(), consent }))).toThrow()
    }
    for (const enrollment_metadata of [null, {}, { ...peerResource(2).enrollment_metadata, metadata_version: true },
      { ...peerResource(2).enrollment_metadata, consent_revision: 3 }, { ...peerResource(2).enrollment_metadata, metadata_hash: 'g'.repeat(64) },
      { ...peerResource(2).enrollment_metadata, application_intent: '*' }, { ...peerResource(2).enrollment_metadata, application_intent: 'a'.repeat(257) },
      { ...peerResource(2).enrollment_metadata, application_intent: 'opaque\n' },
      { ...peerResource(2).enrollment_metadata, consent: { ...peerResource().consent, summary_fields: [] } },
      { ...peerResource(2).enrollment_metadata, credential: 'NEVER' }]) {
      expect(() => parse(withResource({ ...peerResource(2), enrollment_metadata }))).toThrow()
    }
    expect(() => parse(withResource({ ...peerResource(), enrollment_metadata: peerResource(2).enrollment_metadata }))).toThrow()
    expect(parse(peerPlan()).resources.peer_reads?.[1]?.enrollment_metadata?.metadata_hash).toBe('7'.repeat(64))
  })

  it('refuses noncanonical origins, booleans, invalid public dates and whitespace identities', () => {
    for (const origin of ['http://receiver.example', 'https://receiver.example/', 'https://receiver.example:443',
      'https://user:pass@receiver.example', 'https://UPPER.example', 'https://receiver.example?x=1', 'https://bad..example']) {
      expect(() => parse(withResource({ ...peerResource(), origin }))).toThrow()
    }
    for (const changes of [{ peer_version: true }, { consent_revision: true }, { consent_revision: 0 },
      { consent_revision: Number.MAX_SAFE_INTEGER + 1 }, { peer_id: peerResource().peer_id + '\n' },
      { application_instance_id: 'd'.repeat(24) + '\n' }, { target_module_id: 'org.example.receiver\n' },
      { sender_identity: { ...peerSender(), installation_id: peerSender().installation_id + '\n' } },
      { sender_identity: { ...peerSender(), created_at: '2025-02-29T00:00:00Z' } }]) {
      expect(() => parse(withResource({ ...peerResource(), ...changes }))).toThrow()
    }
  })

  it('requires earlier families in full and their exact shared owner/identity/link data', () => {
    const resource = peerResource()
    const statusScope = `status:${resource.peer_id}:read`
    const statusProjection = { owner: peerOwner(), package_artifact_sha256: peerArtifact, operation: 'installation.status.read',
      link_id: resource.peer_id, application_instance_id: resource.application_instance_id, sender_identity: resource.sender_identity,
      receiver_identity: resource.receiver_identity, origin: resource.origin, target_module_id: resource.target_module_id,
      consent_revision: resource.consent_revision, consent: resource.consent }
    const identity = { owner: peerOwner(), package_artifact_sha256: peerArtifact, operation: 'installation.identity.read', identity: peerSender() }
    const checkpoint = { owner: peerOwner(), package_artifact_sha256: peerArtifact, operation: 'read',
      declaration: { contract_version: 1, checkpoint_id: 'progress', mode: 'read', max_value_bytes: 128 } }
    const required = [statusScope, 'platform:installation.identity.read', 'checkpoint:progress:read']
    const current = { ...peerStatus(), scopes: [...peerScopes(), ...required] }
    const value = { ...peerPlan(required), resources: { ...peerPlan().resources, status_projections: [statusProjection], identities: [identity], checkpoints: [checkpoint] } }
    expect(parse(value, current).scopes).toEqual(required)
    expect(() => parse({ ...value, scopes: required.slice(1) }, current)).toThrow()
    for (const projection of [{ ...statusProjection, origin: 'https://changed.example' }, { ...statusProjection, consent_revision: 3 },
      { ...statusProjection, application_instance_id: 'e'.repeat(24) },
      { ...statusProjection, receiver_identity: { ...statusProjection.receiver_identity, created_at: '2026-10-17T12:00:00Z' } }]) {
      expect(() => parse({ ...value, resources: { ...value.resources, status_projections: [projection] } }, current)).toThrow()
    }
    expect(() => parse({ ...value, resources: { ...value.resources, identities: [{ ...identity, identity: { ...peerSender(), created_at: '2026-10-17T12:00:00Z' } }] } }, current)).toThrow()
    expect(() => parse({ ...value, resources: { ...value.resources, checkpoints: [{ ...checkpoint, owner: { ...peerOwner(), incarnation: '9'.repeat(32) } }] } }, current)).toThrow()
  })

  it('distinguishes current executor support from older unavailable runtimes; rejects SQL/inbound profiles', () => {
    expect(readAuthorityStatus(peerStatus()).grant_effective).toBe(false)
    expect(readAuthorityStatus({ ...peerStatus(), grant_effective: true, runtime_blockers: [] }).grant_effective).toBe(true)
    expect(readAuthorityStatus({ ...peerStatus(), grant_effective: true, runtime_blockers: undefined }).grant_effective).toBe(true)
    for (const changes of [{ grant_effective: true },
      { runtime_blockers: ['relational_runtime_unavailable'] }, { runtime_blockers: ['unknown'] },
      { runtime_blockers: ['peer_read_runtime_unavailable', 'peer_read_runtime_unavailable'] },
      { scopes: [...peerScopes(), 'storage:relational_read'] }]) {
      expect(() => readAuthorityStatus({ ...peerStatus(), ...changes })).toThrow()
    }
    expect(() => readAuthorityStatus({ ...peerStatus(), scopes: [], runtime_blockers: ['peer_read_runtime_unavailable'] })).toThrow()
    expect(() => parse({ ...peerPlan(), historical: true })).toThrow()
    expect(() => parse({ ...peerPlan(), resources: { ...peerPlan().resources, peer_receiver: {} } })).toThrow()
  })

  it('retains old family count ceilings; only exact peer scopes allow the additive 261 ceiling', () => {
    const commands = Array.from({ length: 260 }, (_, index) => `command:binding_${index}`)
    expect(readAuthorityStatus({ ...peerStatus(), scopes: [peerScopes()[0]!, ...commands] }).scopes).toHaveLength(261)
    expect(() => readAuthorityStatus({ ...peerStatus(), scopes: [...peerScopes(), ...commands] })).toThrow()
    expect(() => readAuthorityStatus({ ...peerStatus(), scopes: commands.slice(0, 198), runtime_blockers: [] })).toThrow()
  })
})
