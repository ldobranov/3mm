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
