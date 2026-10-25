import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const locale = vi.hoisted(() => ({ language: 'en' }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  const { movedLanguageLabel } = await import('@/test-utils/language-messages')
  return { useI18n: () => ({ currentLanguage: ref(locale.language), t: (key: string, fallback: string) => movedLanguageLabel(key, fallback, locale.language) }) }
})
import ApplicationAuthorityDialog from './ApplicationAuthorityDialog.vue'
import { readAuthorityStatus, readAuthorityPlan, readAuthorityDecision } from './authority-management'
import { consentPreview, consentResult } from './application-consent.fixtures'
import { readConsentPreview } from './application-consent'

const base = '/api/v1/application-extensions/org.example.reference/authority'
const identity = (n: string) => n.repeat(32)
const status = () => ({
  installation_id: 7, mode: 'enforced', installation_status: 'active', installation_enabled: true,
  artifact_sha256: 'a'.repeat(64), scopes: ['command:pulse', 'connector:external_api'],
  native_reviews: [{ native_review_id: identity('1'), revision: identity('2') }],
  grant_state: 'active', grant_record_revision: identity('3'), grant_effective: true, isolation_proven: false,
})
const plan = () => ({
  plan_id: identity('4'), revision: identity('5'), fingerprint: '6'.repeat(64), state: 'review_required',
  artifact_sha256: 'a'.repeat(64), scopes: status().scopes, expires_in_seconds: 900, isolation_proven: false,
  resources: {
    commands: [{ target_device_id: 'dev_' + identity('7'), sensor_device_id: 'dev_' + identity('8'),
      declaration: { binding_id: 'pulse', capability_id: 'gpio.digital.control', channels: ['gpio.output.1'], ttl_seconds: 10 } }],
    connectors: [{ declaration: { connector_id: 'external_api', operations: [{ method: 'GET', path: '/records' }] },
      stored: { destination_origin: 'https://example.test', credential: { secret_ref: 'external-credential', version: '2', credential_kind: 'bearer' } } }],
  },
})
const decision = (state: string, revision = identity('9')) => ({
  plan_id: plan().plan_id, fingerprint: plan().fingerprint, revision, state,
})
const eventResource = () => ({
  source_device_id: 'dev_' + identity('7'), source_revision: 'source_' + 'a'.repeat(64),
  declaration: { subscription_id: 'changes', event_type: 'device.changed.v1', capability_id: 'gpio.digital.control',
    handler_operation_id: 'process_change', device_scope_config_key: 'DEVICE_ID', acknowledgement: 'after_commit', max_backlog: 100 },
  handler: { operation_id: 'process_change', kind: 'command', audiences: ['internal'], idempotency: 'required', timeout_seconds: 10, emitted_events: [] },
})
const mounted: VueWrapper[] = []
const publicationResource = () => ({
  declaration: { publication_id: 'changed', operation_id: 'record', event_type: 'example.record.changed.v1',
    max_payload_bytes: 128, payload_schema: { type: 'object', properties: { value: { type: 'integer', minimum: 0, maximum: 10 } }, additionalProperties: false } },
  operation: { operation_id: 'record', kind: 'command', idempotency: 'required', emitted_events: ['example.record.changed.v1'] },
  service_artifact_sha256: 'c'.repeat(64),
})
const fileResource = (operation: 'read' | 'write' = 'read', mode: 'read' | 'read_write' = 'read_write') => ({
  declaration: { file_contract_version: 1, namespace: 'private_files', mode, max_file_bytes: 128, max_total_bytes: 200, max_files: 2 },
  owner: { core_installation_id: 'installation_' + identity('b'), application_installation_id: '7', incarnation: identity('c'), module_id: 'org.example.reference' },
  package_artifact_sha256: 'a'.repeat(64), operation,
})
const relationalResource = (operation: 'read' | 'write' = 'read', mode: 'read' | 'read_write' = 'read_write') => ({
  declaration: { contract_version: 1, mode, limit_class: 'cooperative_v1', max_database_bytes: 1048576,
    auxiliary_pause_bytes: 262144, max_statement_bytes: 2048, max_value_bytes: 1024,
    max_result_bytes: 4096, max_result_rows: 16, max_transaction_ms: 5000, max_busy_ms: 500 },
  owner: fileResource().owner, package_artifact_sha256: 'a'.repeat(64), service_artifact_sha256: 'c'.repeat(64),
  schema_revision: '0002', migration_entrypoint: 'reference_app.migrations:get_migrations',
  resource_profile: 'owned_sqlite_request_v1', operation,
})
const relationalStatus = (mode: 'read' | 'read_write' = 'read_write', files = false) => ({
  ...status(), scopes: ['storage:relational_read', ...(mode === 'read_write' ? ['storage:relational_write'] : []),
    ...(files ? ['storage:private_files_read'] : [])],
  grant_effective: false, review_available: true, review_blockers: [], runtime_blockers: ['relational_runtime_unavailable'],
})
const relationalPlan = (mode: 'read' | 'read_write' = 'read_write', files = false) => ({
  ...plan(), scopes: relationalStatus(mode, files).scopes,
  resources: { commands: [], connectors: [], private_files: files ? [fileResource('read', 'read')] : [],
    relational: mode === 'read' ? [relationalResource('read', mode)] : [relationalResource('read'), relationalResource('write')] },
})
const checkpointResource = (operation: 'read' | 'write' = 'read', mode: 'read' | 'read_write' = 'read_write') => ({
  declaration: { contract_version: 1, checkpoint_id: 'progress', mode, max_value_bytes: 4096 },
  owner: fileResource().owner, package_artifact_sha256: 'a'.repeat(64), operation,
})
const identityResource = () => ({
  owner: { ...fileResource().owner, core_installation_id: 'inst_' + identity('b') },
  package_artifact_sha256: 'a'.repeat(64), operation: 'installation.identity.read',
  identity: { identity_version: 1, installation_id: 'inst_' + identity('b'), algorithm: 'ed25519',
    key_id: '21fe31dfa154a261626bf854046fd2271b7bed4b6abe45aa58877ef47f9721b9',
    public_key: '11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=', key_generation: 1,
    created_at: '2026-10-16T00:12:34.123456Z' },
})
const identityStatus = () => ({ ...status(), scopes: ['platform:installation.identity.read'] })
const identityPlan = () => ({ ...plan(), scopes: identityStatus().scopes,
  resources: { commands: [], connectors: [], identities: [identityResource()] } })
const nativeMethods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
beforeEach(() => {
  vi.resetAllMocks()
  locale.language = 'en'
  http.get.mockResolvedValue({ data: status() })
  http.post.mockResolvedValue({ data: consentPreview(status(), plan().resources) })
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false } })
})
afterEach(() => {
  mounted.splice(0).forEach(wrapper => wrapper.unmount())
  vi.useRealTimers()
  for (const { name, descriptor } of nativeMethods) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
  }
  document.body.innerHTML = ''
})
async function open() {
  const wrapper = mount(ApplicationAuthorityDialog, { attachTo: document.body,
    props: { moduleId: 'org.example.reference', name: 'Reference application' } })
  mounted.push(wrapper); await flushPromises(); return wrapper
}
function button(wrapper: VueWrapper, text: string) {
  const found = wrapper.findAll('button').find(control => control.text() === text)
  if (!found) throw new Error('Missing button: ' + text)
  return found
}
describe('single explicit application consent', () => {
  it('opens only a preview, selects all fresh rights and keeps details optional', async () => {
    const wrapper = await open()
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(http.post).toHaveBeenCalledWith(base + '/consent/preview', { request_id: expect.stringMatching(/^[a-f0-9]{32}$/) }, { timeout: 12000 })
    expect(http.post.mock.calls.some(call => String(call[0]).endsWith('/consent/allow'))).toBe(false)
    expect(wrapper.findAll('.authority-scope-choice input')).toHaveLength(2)
    expect(wrapper.findAll('input[type=checkbox]').every(item => (item.element as HTMLInputElement).checked)).toBe(true)
    expect((wrapper.find('details.authority-details').element as HTMLDetailsElement).open).toBe(false)
    expect(wrapper.findAll('select, .authority-acknowledge').length).toBe(0)
    for (const text of ['Compatibility mode', 'Local code review', 'Approve review', 'Apply rights']) expect(wrapper.text()).not.toContain(text)
    for (const text of ['native code', 'https://example.test', 'gpio.output.1', 'external-credential']) expect(wrapper.text()).toContain(text)
    await button(wrapper, 'Close').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(http.post).toHaveBeenCalledTimes(1)
  })

  it('one Allow saves exactly the edited choices and current-account permissions', async () => {
    let saved = false
    const initial = consentPreview(status(), plan().resources)
    http.post.mockImplementation(async (path: string) => {
      if (path.endsWith('/consent/allow')) { saved = true; return { data: consentResult(initial) } }
      return { data: { ...initial, access_saved: saved, selected_scopes: saved ? ['command:pulse'] : initial.scopes,
        selected_user_permissions: saved ? [] : initial.selected_user_permissions } }
    })
    const wrapper = await open()
    await wrapper.find('.authority-scope-choice input[value="connector:external_api"]').setValue(false)
    await wrapper.find('.authority-user-choice input').setValue(false)
    await button(wrapper, 'Allow access').trigger('click'); await flushPromises()
    const requests = http.post.mock.calls.filter(call => String(call[0]).endsWith('/consent/allow'))
    expect(requests).toHaveLength(1)
    expect(requests[0]).toEqual([base + '/consent/allow', { request_id: expect.stringMatching(/^[a-f0-9]{32}$/),
      preview_id: initial.preview_id, expected_revision: initial.revision, fingerprint: initial.fingerprint,
      scopes: ['command:pulse'], user_permissions: [], accept_native_code: true }, { timeout: 30000 }])
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.text()).toContain('Access saved')
    expect((wrapper.find('.authority-scope-choice input[value="connector:external_api"]').element as HTMLInputElement).checked).toBe(false)
    expect(button(wrapper, 'Allow access').attributes('disabled')).toBeDefined()
  })

  it('saved stopped access retains the server subset and needs no repeated approval', async () => {
    const current = { ...status(), installation_status: 'disabled', installation_enabled: false, grant_effective: false }
    http.get.mockResolvedValue({ data: current })
    http.post.mockResolvedValue({ data: { ...consentPreview(current, plan().resources), access_saved: true,
      selected_scopes: ['command:pulse'], selected_user_permissions: [] } })
    const wrapper = await open()
    expect(wrapper.text()).toContain('Rights saved, application stopped')
    expect(button(wrapper, 'Allow access').attributes('disabled')).toBeDefined()
    await button(wrapper, 'Refresh status').trigger('click'); await flushPromises()
    expect(wrapper.findAll('.authority-scope-choice input').filter(item => (item.element as HTMLInputElement).checked)).toHaveLength(1)
    expect(http.post.mock.calls.every(call => String(call[0]).endsWith('/consent/preview'))).toBe(true)
  })

  it('keeps saved approval separate from an unavailable runtime', async () => {
    const current = relationalStatus()
    http.get.mockResolvedValue({ data: current })
    http.post.mockResolvedValue({ data: { ...consentPreview(current, relationalPlan().resources), access_saved: true } })
    const wrapper = await open()
    expect(wrapper.text()).toContain('Access is saved. The application runtime is not available yet.')
    expect(wrapper.findAll('.authority-relational pre')).toHaveLength(2)
    expect(button(wrapper, 'Allow access').attributes('disabled')).toBeDefined()
  })

  it.each(['storage:relational_read', 'storage:relational_write'])('changes the relational profile together through %s only', async toggled => {
    const current = { ...status(), scopes: [...status().scopes, 'storage:relational_read', 'storage:relational_write', 'storage:private_files_read'] }
    const resources = { ...plan().resources, relational: [relationalResource('read'), relationalResource('write')], private_files: [fileResource('read', 'read')] }
    http.get.mockResolvedValue({ data: current })
    http.post.mockResolvedValue({ data: consentPreview(current, resources) })
    const wrapper = await open()
    const read = () => wrapper.find('.authority-scope-choice input[value="storage:relational_read"]')
    const write = () => wrapper.find('.authority-scope-choice input[value="storage:relational_write"]')
    expect(wrapper.find('.authority-relational-profile').text()).toContain('one shared access profile')
    expect((read().element as HTMLInputElement).checked && (write().element as HTMLInputElement).checked).toBe(true)
    await wrapper.find(`.authority-scope-choice input[value="${toggled}"]`).setValue(false)
    expect((read().element as HTMLInputElement).checked).toBe(false)
    expect((write().element as HTMLInputElement).checked).toBe(false)
    for (const scope of [...status().scopes, 'storage:private_files_read']) {
      expect((wrapper.find(`.authority-scope-choice input[value="${scope}"]`).element as HTMLInputElement).checked).toBe(true)
    }
    expect((wrapper.find('.authority-user-choice input').element as HTMLInputElement).checked).toBe(true)
    const other = toggled === 'storage:relational_read' ? write() : read()
    await other.setValue(true)
    expect((read().element as HTMLInputElement).checked && (write().element as HTMLInputElement).checked).toBe(true)
  })

  it.each(['storage:relational_read', 'storage:relational_write'])('rejects a backend preview selecting only %s from the shared profile', scope => {
    const value = { ...consentPreview(relationalStatus(), relationalPlan().resources), selected_scopes: [scope] }
    expect(() => readConsentPreview(value, 'org.example.reference')).toThrow('Partial relational access profile')
    expect(readConsentPreview({ ...value, selected_scopes: [] }, 'org.example.reference').selected_scopes).toEqual([])
  })

  it('does not turn a missing old manual review into a console step', async () => {
    http.get.mockResolvedValue({ data: { ...status(), review_available: false, review_blockers: ['review_key_unavailable'],
      native_reviews: [], scopes: [], grant_effective: false, grant_state: null, grant_record_revision: null } })
    const wrapper = await open()
    expect(wrapper.text()).not.toContain('review key')
    expect(wrapper.text()).not.toContain('trusted reviewer')
    expect(button(wrapper, 'Allow access').attributes('disabled')).toBeUndefined()
  })

  it.each([['private files', () => ({ scopes: ['storage:private_files_read', 'storage:private_files_write'], resources: { commands: [], connectors: [], private_files: [fileResource(), fileResource('write')] } })],
    ['public identity', () => ({ scopes: identityStatus().scopes, resources: identityPlan().resources })]] as const)('retains exact %s resource details before consent', async (_name, fixture) => {
    const value = fixture(), current = { ...status(), scopes: value.scopes }
    http.post.mockResolvedValue({ data: consentPreview(current, value.resources) })
    const wrapper = await open()
    expect(wrapper.find('details.authority-details').exists()).toBe(true)
    expect(wrapper.text()).toContain(current.artifact_sha256)
    expect(http.post).toHaveBeenCalledTimes(1)
  })

  it.each([new Error('lost response'), { response: { status: 409 } }])('never retries uncertain or stale consent', async cause => {
    const wrapper = await open()
    http.post.mockRejectedValueOnce(cause)
    await button(wrapper, 'Allow access').trigger('click'); await flushPromises()
    expect(wrapper.find('[role=alert]').exists()).toBe(true)
    expect(button(wrapper, 'Allow access').attributes('disabled')).toBeDefined()
    await button(wrapper, 'Allow access').trigger('click')
    expect(http.post).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('keeps confirmed saved access when the following preview refresh fails', async () => {
    const wrapper = await open()
    http.post.mockResolvedValueOnce({ data: consentResult(consentPreview(status(), plan().resources)) })
    http.post.mockRejectedValueOnce(new Error('preview offline'))
    await button(wrapper, 'Allow access').trigger('click'); await flushPromises()
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.find('[role=status]').text()).toContain('Access saved')
    expect(wrapper.find('[role=alert]').text()).toContain('could not be loaded')
    expect(wrapper.text()).not.toContain('Saved access could not be confirmed')
    expect(http.post.mock.calls.filter(call => String(call[0]).endsWith('/consent/allow'))).toHaveLength(1)
  })

  it('expires the preview locally without approval or automatic refresh', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    http.post.mockResolvedValueOnce({ data: { ...consentPreview(status(), plan().resources), expires_in_seconds: 2 } })
    const wrapper = await open()
    await vi.advanceTimersByTimeAsync(3000)
    expect(button(wrapper, 'Allow access').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('details expired')
    expect(http.post).toHaveBeenCalledTimes(1)
  })

  it('keeps revocation as a separate explicit danger confirmation', async () => {
    const wrapper = await open()
    await button(wrapper, 'Revoke rights').trigger('click')
    expect(http.post).toHaveBeenCalledTimes(1)
    await button(wrapper, 'Cancel').trigger('click')
    expect(http.post).toHaveBeenCalledTimes(1)
    await button(wrapper, 'Revoke rights').trigger('click')
    http.post.mockResolvedValueOnce({ data: { state: 'revoked' } })
    await button(wrapper, 'Confirm revocation').trigger('click'); await flushPromises()
    expect(http.post).toHaveBeenCalledWith(base + '/revoke', { request_id: expect.stringMatching(/^[a-f0-9]{32}$/), expected_revision: identity('3') }, { timeout: 12000 })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('prevents double consent and ignores completion after unmount', async () => {
    const wrapper = await open()
    let resolve!: (value: unknown) => void
    http.post.mockImplementationOnce(() => new Promise(done => { resolve = done }))
    await button(wrapper, 'Allow access').trigger('click')
    await button(wrapper, 'Allow access').trigger('click')
    expect(http.post).toHaveBeenCalledTimes(2)
    await button(wrapper, 'Close').trigger('click'); expect(wrapper.emitted('close')).toBeUndefined()
    wrapper.unmount(); mounted.pop()
    resolve({ data: consentResult(consentPreview(status(), plan().resources)) }); await flushPromises()
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(http.post).toHaveBeenCalledTimes(2)
  })
})

describe('authority response boundaries', () => {
  it('refuses missing, duplicate, foreign, unbounded or injected private-file bindings', () => {
    const current = readAuthorityStatus({ ...status(), scopes: [...status().scopes, 'storage:private_files_read', 'storage:private_files_write'] })
    const value = { ...plan(), scopes: current.scopes, resources: { ...plan().resources, private_files: [fileResource('read'), fileResource('write')] } }
    expect(readAuthorityPlan(value, current, 'org.example.reference').resources.private_files).toHaveLength(2)
    const original = fileResource('write')
    for (const wrong of [null, { ...original, operation: 'delete' }, { ...original, path: '/opt/3mm/current' },
      { ...original, package_artifact_sha256: 'd'.repeat(64) },
      { ...original, owner: { ...original.owner, application_installation_id: '8' } },
      { ...original, owner: { ...original.owner, module_id: 'org.example.foreign' } },
      { ...original, owner: { ...original.owner, incarnation: identity('d') } },
      { ...original, owner: { ...original.owner, core_installation_id: 'foreign' } },
      { ...original, declaration: { ...original.declaration, mode: 'read' } },
      { ...original, declaration: { ...original.declaration, namespace: 'other' } },
      { ...original, declaration: { ...original.declaration, file_contract_version: true } },
      { ...original, declaration: { ...original.declaration, max_file_bytes: 1048577 } },
      { ...original, declaration: { ...original.declaration, max_total_bytes: 67108865 } },
      { ...original, declaration: { ...original.declaration, max_files: 1025 } },
      { ...original, declaration: { ...original.declaration, max_files: true } },
      { ...original, declaration: { ...original.declaration, max_file_bytes: 0 } },
      { ...original, declaration: { ...original.declaration, max_file_bytes: 201 } },
      { ...original, declaration: { ...original.declaration, max_files: 3 } },
      { ...original, declaration: { ...original.declaration, path: '/var/lib/3mm/core' } }]) {
      expect(() => readAuthorityPlan({ ...value, resources: { ...value.resources, private_files: [fileResource('read'), wrong] } }, current, 'org.example.reference')).toThrow()
    }
    for (const files of [[], [fileResource('write')], [fileResource('read'), fileResource('read')]]) {
      expect(() => readAuthorityPlan({ ...value, resources: { ...value.resources, private_files: files } }, current)).toThrow()
    }
    expect(() => readAuthorityPlan({ ...value, resources: plan().resources }, current)).toThrow()
    expect(() => readAuthorityPlan({ ...value, resources: { ...value.resources, arbitrary_files: [] } }, current)).toThrow()
  })
  it.each(['storage:*', 'storage:private_files', 'storage:other_read', 'storage:private_files_delete', 'storage:private_files_write\n'])('refuses unsupported file scope %s', scope => {
    expect(() => readAuthorityStatus({ ...status(), scopes: [scope] })).toThrow()
  })
  it('refuses mismatched publication operations, unbounded schemas and malformed receipts', () => {
    const current = readAuthorityStatus({ ...status(), scopes: [...status().scopes, 'publication:changed'] })
    const value = { ...plan(), scopes: current.scopes, resources: { ...plan().resources, publications: [publicationResource()] } }
    expect(readAuthorityPlan(value, current).resources.publications).toHaveLength(1)
    for (const resource of [null, { ...publicationResource(), service_artifact_sha256: 'wrong' },
      { ...publicationResource(), operation: { ...publicationResource().operation, operation_id: 'foreign' } },
      { ...publicationResource(), declaration: { ...publicationResource().declaration, max_payload_bytes: 61441 } }]) {
      expect(() => readAuthorityPlan({ ...value, resources: { ...value.resources, publications: [resource] } }, current)).toThrow()
    }
    expect(() => readAuthorityPlan({ ...value, resources: plan().resources }, current)).toThrow()
  })
  it('refuses unmatched or malformed event resources without inferring permissions', () => {
    const current = readAuthorityStatus({ ...status(), scopes: [...status().scopes, 'event:changes'] })
    const value = { ...plan(), scopes: current.scopes, resources: { ...plan().resources, events: [eventResource()] } }
    expect(readAuthorityPlan(value, current).resources.events).toHaveLength(1)
    for (const resource of [null, { ...eventResource(), source_device_id: 'wrong' },
      { ...eventResource(), handler: { ...eventResource().handler, operation_id: 'other' } },
      { ...eventResource(), declaration: { ...eventResource().declaration, max_backlog: 100001 } }]) {
      expect(() => readAuthorityPlan({ ...value, resources: { ...value.resources, events: [resource] } }, current)).toThrow()
    }
    expect(() => readAuthorityPlan({ ...value, resources: plan().resources }, current)).toThrow()
  })
  it('accepts current bounded responses and refuses invented isolation or old artifacts', () => {
    const current = readAuthorityStatus(status())
    expect(readAuthorityPlan(plan(), current).plan_id).toBe(identity('4'))
    expect(() => readAuthorityStatus({ ...status(), isolation_proven: true })).toThrow()
    expect(() => readAuthorityPlan({ ...plan(), artifact_sha256: 'b'.repeat(64) }, current)).toThrow()
    expect(() => readAuthorityPlan({ ...plan(), scopes: ['command:pulse', 'command:pulse'] }, current)).toThrow()
    expect(() => readAuthorityPlan({ ...plan(), expires_in_seconds: 901 }, current)).toThrow()
    expect(() => readAuthorityPlan({ ...plan(), resources: { commands: [null], connectors: plan().resources.connectors } }, current)).toThrow()
    expect(() => readAuthorityPlan({ ...plan(), resources: { commands: plan().resources.commands, connectors: [{ declaration: { connector_id: 'other' } }] } }, current)).toThrow()
  })
  it.each(['historical', 'replayed'])('historical %s receipts are not live authority', flag => {
    const reviewed = readAuthorityPlan(plan(), readAuthorityStatus(status()))
    expect(() => readAuthorityPlan({ ...plan(), [flag]: true }, readAuthorityStatus(status()))).toThrow()
    expect(() => readAuthorityDecision({ ...decision('approved_pending_apply'), [flag]: true }, reviewed, 'approve')).toThrow()
  })
  it('requires matching plan, fingerprint and a new decision revision', () => {
    const reviewed = readAuthorityPlan(plan(), readAuthorityStatus(status()))
    expect(() => readAuthorityDecision(decision('approved_pending_apply', identity('5')), reviewed, 'approve')).toThrow()
    expect(() => readAuthorityDecision({ ...decision('approved_pending_apply'), fingerprint: '0'.repeat(64) }, reviewed, 'approve')).toThrow()
    expect(() => readAuthorityDecision(decision('applied'), reviewed, 'approve')).toThrow()
  })
})
