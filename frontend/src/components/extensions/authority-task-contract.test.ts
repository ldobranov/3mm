import { describe, expect, it } from 'vitest'
import responses from './authority-task-responses.fixture.json'
import { readConsentPreview } from './application-consent'

describe('current Core consent responses', () => {
  it('accepts the real non-task preview', () => {
    expect(readConsentPreview(responses.general, responses.general.module_id)).toEqual(responses.general)
  })
  it('accepts the real Task Probe preview with its exact bounded handler', () => {
    expect(readConsentPreview(responses.task, responses.task.module_id)).toEqual(responses.task)
  })
  it('preserves a deliberately empty selection of task permissions', () => {
    const value = structuredClone(responses.task)
    value.selected_scopes = []
    expect(readConsentPreview(value, value.module_id).selected_scopes).toEqual([])
  })
  it.each([
    ['foreign application', (value: any) => { value.resources.tasks[0].owner.module_id = 'org.example.foreign' }],
    ['foreign installation', (value: any) => { value.resources.tasks[0].owner.application_installation_id = '2' }],
    ['different artifact', (value: any) => { value.resources.tasks[0].package_artifact_sha256 = 'f'.repeat(64) }],
    ['missing task resource', (value: any) => { delete value.resources.tasks }],
    ['unknown resource field', (value: any) => { value.resources.future_resources = [] }],
    ['duplicate task', (value: any) => { value.resources.tasks.push(structuredClone(value.resources.tasks[0])) }],
    ['unknown handler', (value: any) => { value.resources.tasks[0].operation.operation_id = 'other' }],
    ['external audience', (value: any) => { value.resources.tasks[0].operation.audiences = ['administrator'] }],
    ['command handler', (value: any) => { value.resources.tasks[0].operation.kind = 'command' }],
    ['unbounded runtime', (value: any) => { value.resources.tasks[0].declaration.max_runtime_seconds = 11 }],
    ['mismatched runtime', (value: any) => { value.resources.tasks[0].operation.timeout_seconds = 3 }],
    ['boolean pending limit', (value: any) => { value.resources.tasks[0].declaration.max_pending = true }],
    ['unknown profile', (value: any) => { value.resources.tasks[0].declaration.profile = 'workflow' }],
    ['event side effects', (value: any) => { value.resources.tasks[0].operation.emitted_events = ['example.changed.v1'] }],
    ['nested task input', (value: any) => { value.resources.tasks[0].operation.input_schema.properties.upper = { type: 'object' } }],
    ['null required list', (value: any) => { value.resources.tasks[0].operation.input_schema.required = null }],
    ['unbounded numeric input', (value: any) => { delete value.resources.tasks[0].operation.input_schema.properties.upper.maximum }],
    ['foreign selected scope', (value: any) => { value.selected_scopes = ['task:other'] }],
    ['unsupported scope family', (value: any) => { value.scopes.push('connector:external_api') }],
  ])('rejects %s without exposing an approval choice', (_name, change) => {
    const value = structuredClone(responses.task)
    change(value)
    expect(() => readConsentPreview(value, value.module_id)).toThrow()
  })
})
