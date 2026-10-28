import { describe, expect, it } from 'vitest'
import { readCommandConfiguration, readCommandDiscovery, readCommandRebindPreview, readCommandRebindStatus, readPendingRebind } from './command-resources'
import { moduleId, sha, first, second, binding, discovery, configuration, preview, status } from './command-resources.fixtures'

describe('Command resource DTO boundaries', () => {
  it('accepts the declared requirement, compatible observation and exact preview', () => {
    expect(readCommandConfiguration(configuration(), moduleId).bindings).toEqual([binding])
    expect(readCommandDiscovery(discovery(), binding).selected_device_id).toBe(first)
    expect(readCommandRebindPreview(preview(), moduleId, sha, binding, second, first).after_provider.device_id).toBe(second)
    expect(readPendingRebind({ pending: status('recovery_required') }, moduleId)?.state).toBe('recovery_required')
  })
  it.each([
    { discovery_version: true }, { access: 'granted' }, { binding_id: 'another' }, { contract_version: '2.0' },
    { observed_at: '2026-10-25' }, { candidates: [{ ...discovery().candidates[0], selectable: 'yes' }] },
    { candidates: [discovery().candidates[0], discovery().candidates[0]] },
  ])('rejects a malformed, duplicate or foreign discovery: %j', change => {
    expect(() => readCommandDiscovery({ ...discovery(), ...change }, binding)).toThrow()
  })
  it.each([
    { artifact_sha256: 'b'.repeat(64) }, { module_id: 'org.other.app' }, { fingerprint: 'invalid' },
    { after_provider: { ...preview().after_provider, device_id: first } }, { restart_required: false },
    { expires_in_seconds: 901 }, { scopes: [] },
  ])('cannot approve an altered preview: %j', change => {
    expect(() => readCommandRebindPreview({ ...preview(), ...change }, moduleId, sha, binding, second, first)).toThrow()
  })
  it('rejects foreign status and cannot turn a completed record into pending work', () => {
    expect(() => readCommandRebindStatus(status(), 'org.other.app')).toThrow()
    expect(() => readCommandRebindStatus(status(), moduleId, 'a'.repeat(32))).toThrow()
    expect(() => readPendingRebind({ pending: status() }, moduleId)).toThrow()
    expect(() => readPendingRebind({ pending: { ...status('recovering'), installation_enabled: true } }, moduleId)).toThrow()
    expect(readPendingRebind({ pending: null }, moduleId)).toBeNull()
  })
})
