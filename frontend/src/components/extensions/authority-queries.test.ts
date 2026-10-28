import { describe, expect, it } from 'vitest'
import { readConsentPreview } from './application-consent'
import { queryPreview } from './authority-queries.fixtures'

describe('exact one-hop query consent boundary', () => {
  it('retains all public pins, strict limits and the initially empty selection', () => {
    const value = queryPreview()
    expect(readConsentPreview(value, value.module_id)).toEqual(value)
    expect(value.selected_scopes).toEqual([])
  })
  it.each([
    (v: ReturnType<typeof queryPreview>) => { v.resources.queries[0]!.provider = v.resources.queries[0]!.owner },
    (v: ReturnType<typeof queryPreview>) => { v.resources.queries[0]!.provider_instance_id = v.resources.queries[0]!.owner_instance_id },
    (v: ReturnType<typeof queryPreview>) => { v.resources.queries[0]!.provider.core_installation_id = 'foreign' },
    (v: ReturnType<typeof queryPreview>) => { v.resources.queries[0]!.declaration.contract.timeout_seconds = 30 },
    (v: ReturnType<typeof queryPreview>) => { v.resources.queries[0]!.export.contract.contract_version = '2.0' },
    (v: ReturnType<typeof queryPreview>) => { v.resources.queries[0]!.contract_digest = '*' },
    (v: ReturnType<typeof queryPreview>) => { v.resources.queries[0]!.provider_grant_revision = 0 },
    (v: ReturnType<typeof queryPreview>) => { v.resources.queries[0]!.declaration.contract.input_schema = { type: 'object', additionalProperties: true } },
    (v: ReturnType<typeof queryPreview>) => { v.scopes.push('checkpoint:progress:read') },
    (v: ReturnType<typeof queryPreview>) => { v.resources.queries.push(structuredClone(v.resources.queries[0]!)) },
  ])('refuses malformed or broader resources before any approval (%#)', mutate => {
    const value = queryPreview(); mutate(value)
    expect(() => readConsentPreview(value, value.module_id)).toThrow()
  })
})
