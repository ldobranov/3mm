import { describe, expect, it } from 'vitest'
import { readConsentPreview, readConsentResult } from './application-consent'
import { consentPreview, consentResult } from './application-consent.fixtures'
import { sessionModuleId, sessionPlan, sessionStatus } from './authority-sessions.fixtures'
const preview = () => consentPreview(sessionStatus(), sessionPlan().resources, sessionModuleId)
describe('strict application consent boundary', () => {
  it('validates the exact resources while preserving an empty selected subset', () => {
    const value = { ...preview(), selected_scopes: [], selected_user_permissions: [] }
    expect(readConsentPreview(value, sessionModuleId)).toEqual(value)
  })
  it('accepts an unavailable optional connector without offering or granting it', () => {
    const value = { ...preview(), optional_resources: ['connector:unconfigured_api'],
      unavailable_resources: [{ scope: 'connector:unconfigured_api', reason: 'connector_binding_unavailable' }] }
    expect(readConsentPreview(value, sessionModuleId).optional_resources).toEqual(['connector:unconfigured_api'])
    expect(() => readConsentPreview({ ...value, selected_scopes: ['connector:unconfigured_api'] }, sessionModuleId)).toThrow()
  })
  it('rejects diagnostics for undeclared, offered, duplicate or injected resources', () => {
    const value = { ...preview(), optional_resources: ['event:reader'] }
    for (const items of [null, [{ scope: 'event:other', reason: 'capability_unresolved' }],
      [{ scope: value.scopes[0], reason: 'capability_unresolved' }],
      [{ scope: 'event:reader', reason: 'capability_unresolved', private_data: 'no' }],
      [{ scope: 'event:reader', reason: 'not a code' }],
      Array(2).fill({ scope: 'event:reader', reason: 'capability_unresolved' })]) {
      expect(() => readConsentPreview({ ...value, unavailable_resources: items }, sessionModuleId)).toThrow()
    }
  })
  it.each([null, 'connector:example', [true], ['connector:*'], ['connector:x', 'connector:x'],
    Array.from({ length: 17 }, (_, index) => `connector:example_${index}`)].map(optional => ({ optional })))('rejects invalid optional resource metadata ($optional)', ({ optional }) => {
    expect(() => readConsentPreview({ ...preview(), optional_resources: optional }, sessionModuleId)).toThrow()
  })
  it.each([['consent_version', true], ['preview_id', 'bad'], ['revision', null], ['fingerprint', 'f'],
    ['built_ui_sha256', 'bad'], ['module_id', 'org.example.foreign'], ['installation_id', true], ['expires_in_seconds', 901],
    ['selected_scopes', ['session:foreign:open']], ['selected_scopes', ['session:console:open', 'session:console:open']],
    ['selected_user_permissions', ['foreign']], ['user_permissions', [{ permission_id: '../unsafe', name: 'Invalid' }]],
    ['user_permissions', [{ permission_id: 'app_use', name: {} }]], ['access_saved', 1], ['installation_enabled', 'yes']])('rejects invalid %s', (field, value) => {
    expect(() => readConsentPreview({ ...preview(), [field]: value }, sessionModuleId)).toThrow()
  })
  it('bounds declared account permissions to the backend contract', () => {
    const value = { ...preview(), selected_user_permissions: [],
      user_permissions: Array.from({ length: 97 }, (_, index) => ({ permission_id: `permission_${index}`, name: `Permission ${index}` })) }
    expect(() => readConsentPreview(value, sessionModuleId)).toThrow()
  })
  it('rejects missing/extra envelope fields and foreign/injected session resources', () => {
    const value = preview()
    expect(() => readConsentPreview({ ...value, private_key: 'injected' }, sessionModuleId)).toThrow()
    const missing = { ...value } as Record<string, unknown>; delete missing.built_ui_sha256
    expect(() => readConsentPreview(missing, sessionModuleId)).toThrow()
    const old = { ...value } as Record<string, unknown>; delete old.optional_resources
    expect(() => readConsentPreview(old, sessionModuleId)).toThrow()
    const wrong = preview(); wrong.resources.sessions[0]!.owner.module_id = 'org.example.foreign'
    expect(() => readConsentPreview(wrong, sessionModuleId)).toThrow()
  })
  it('accepts only a fresh saved result for this exact preview and active state', () => {
    const current = readConsentPreview(preview(), sessionModuleId), result = consentResult(preview())
    expect(readConsentResult(result, current).saved).toBe(true)
    for (const changed of [{ preview_id: 'f'.repeat(32) }, { module_id: 'org.example.other' }, { installation_id: 8 },
      { saved: false }, { effective: true, installation_enabled: false }, { historical: true }, { replayed: true },
      { grant_revision: true }, { grant_record_revision: 'bad' }, { authority_epoch: null }]) {
      expect(() => readConsentResult({ ...result, ...changed }, current)).toThrow()
    }
  })
})
