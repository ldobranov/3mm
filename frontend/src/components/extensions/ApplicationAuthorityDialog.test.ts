import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  return { useI18n: () => ({ currentLanguage: ref('en'), t: (_key: string, fallback: string) => fallback }) }
})
import ApplicationAuthorityDialog from './ApplicationAuthorityDialog.vue'
import { readAuthorityStatus, readAuthorityPlan, readAuthorityDecision } from './authority-management'

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
const nativeMethods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
beforeEach(() => {
  vi.resetAllMocks()
  http.get.mockResolvedValue({ data: status() })
  http.post.mockResolvedValue({ data: plan() })
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
async function review(wrapper: VueWrapper) {
  await button(wrapper, 'Review requested access').trigger('click'); await flushPromises()
}

describe('installed authority control', () => {
  it.each(['read', 'read_write'] as const)('shows exact %s file rights without auto approval or apply', async mode => {
    const files = mode === 'read' ? [fileResource('read', mode)] : [fileResource('read'), fileResource('write')]
    const current = { ...status(), scopes: [...status().scopes, ...files.map(file => `storage:private_files_${file.operation}`)] }
    http.get.mockResolvedValue({ data: current })
    http.post.mockResolvedValue({ data: { ...plan(), scopes: current.scopes, resources: { ...plan().resources, private_files: files } } })
    const wrapper = await open()
    expect(http.post).not.toHaveBeenCalled()
    await review(wrapper)
    expect(wrapper.findAll('.authority-file')).toHaveLength(files.length)
    expect(wrapper.text()).toContain('Application-owned private files')
    expect(wrapper.text()).toContain('Read files · get / list')
    expect(wrapper.text().includes('Write files · put / delete')).toBe(mode === 'read_write')
    expect(wrapper.text()).toContain('128 bytes')
    expect(wrapper.text()).toContain('200 bytes')
    expect(wrapper.text()).toContain('org.example.reference · #7')
    expect(wrapper.text()).toContain('installation_' + identity('b'))
    expect(wrapper.text()).toContain(identity('c'))
    expect(wrapper.text()).toContain('a'.repeat(64))
    expect(button(wrapper, 'Approve review').attributes('disabled')).toBeDefined()
    expect(http.post.mock.calls[0]?.[1].scopes).toEqual(current.scopes)
    await wrapper.find('input[type=checkbox]').setValue(true)
    http.post.mockResolvedValueOnce({ data: decision('approved_pending_apply') })
    await button(wrapper, 'Approve review').trigger('click'); await flushPromises()
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(button(wrapper, 'Apply rights').exists()).toBe(true)
    expect(http.post).toHaveBeenCalledTimes(2)
  })
  it('does not present an incomplete or foreign file review for approval', async () => {
    const current = { ...status(), scopes: [...status().scopes, 'storage:private_files_read', 'storage:private_files_write'] }
    http.get.mockResolvedValue({ data: current })
    http.post.mockResolvedValue({ data: { ...plan(), scopes: current.scopes, resources: { ...plan().resources, private_files: [fileResource('read')] } } })
    const wrapper = await open(); await review(wrapper)
    expect(wrapper.find('[role=alert]').exists()).toBe(true)
    expect(wrapper.find('.authority-review-plan').exists()).toBe(false)
    expect(wrapper.find('input[type=checkbox]').exists()).toBe(false)
    expect(http.post).toHaveBeenCalledTimes(1)
  })
  it('shows publication schema, limits and artifact independently from device subscriptions', async () => {
    const current = { ...status(), scopes: [...status().scopes, 'publication:changed'] }
    http.get.mockResolvedValue({ data: current })
    http.post.mockResolvedValue({ data: { ...plan(), scopes: current.scopes, resources: { ...plan().resources, publications: [publicationResource()] } } })
    const wrapper = await open(); await review(wrapper)
    expect(wrapper.text()).toContain('Application event publications')
    expect(wrapper.text()).toContain('example.record.changed.v1')
    expect(wrapper.text()).toContain('max_payload_bytes')
    expect(wrapper.text()).toContain('payload_schema')
    expect(wrapper.text()).toContain('c'.repeat(64))
    expect(button(wrapper, 'Approve review').attributes('disabled')).toBeDefined()
  })
  it('shows exact device event and handler limits in the existing permission review', async () => {
    const current = { ...status(), scopes: [...status().scopes, 'event:changes'] }
    http.get.mockResolvedValue({ data: current })
    http.post.mockResolvedValue({ data: { ...plan(), scopes: current.scopes, resources: { ...plan().resources, events: [eventResource()] } } })
    const wrapper = await open(); await review(wrapper)
    expect(wrapper.text()).toContain('Device event subscriptions')
    expect(wrapper.text()).toContain('device.changed.v1')
    expect(wrapper.text()).toContain('process_change')
    expect(wrapper.text()).toContain('after_commit')
    expect(http.post.mock.calls[0]?.[1].scopes).toContain('event:changes')
    expect(button(wrapper, 'Approve review').attributes('disabled')).toBeDefined()
  })
  it('opening is read-only and native trust is only selected from verified Core reviews', async () => {
    const wrapper = await open()
    expect(http.get).toHaveBeenCalledWith(base, { timeout: 12000 })
    expect(http.post).not.toHaveBeenCalled()
    expect(wrapper.findAll('option').map(item => item.attributes('value'))).toEqual([identity('1')])
    expect(wrapper.find('input[type=checkbox]').exists()).toBe(false)
    await review(wrapper)
    expect(http.post.mock.calls[0]?.[1]).toEqual({ request_id: expect.stringMatching(/^[a-f0-9]{32}$/), native_review_id: identity('1'), scopes: status().scopes })
    expect(wrapper.text()).toContain('https://example.test')
    expect(wrapper.text()).toContain('gpio.output.1')
    expect(wrapper.text()).toContain('dev_' + identity('8'))
    expect(wrapper.text()).toContain('external-credential')
  })
  it('approval requires explicit resource acknowledgement and does not apply rights', async () => {
    const wrapper = await open(); await review(wrapper)
    const approve = button(wrapper, 'Approve review')
    expect(approve.attributes('disabled')).toBeDefined()
    await approve.trigger('click'); expect(http.post).toHaveBeenCalledTimes(1)
    await wrapper.find('input[type=checkbox]').setValue(true)
    http.post.mockResolvedValueOnce({ data: decision('approved_pending_apply') })
    await approve.trigger('click'); await flushPromises()
    expect(http.post).toHaveBeenLastCalledWith(base + '/reviews/' + identity('4') + '/approve', {
      request_id: expect.stringMatching(/^[a-f0-9]{32}$/), expected_revision: identity('5'), fingerprint: plan().fingerprint,
    }, { timeout: 12000 })
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(wrapper.text()).toContain('Approved, not applied')
    http.post.mockResolvedValueOnce({ data: decision('applied', identity('a')) })
    await button(wrapper, 'Apply rights').trigger('click'); await flushPromises()
    expect(http.post.mock.calls[2]?.[1].expected_revision).toBe(identity('9'))
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(http.get).toHaveBeenCalledTimes(2)
  })
  it.each(['active', 'installing'])('does not offer applying first adoption while application is %s', async state => {
    http.get.mockResolvedValue({ data: { ...status(), mode: 'compatibility', installation_status: state, installation_enabled: state === 'active' } })
    const wrapper = await open(); await review(wrapper)
    await wrapper.find('input[type=checkbox]').setValue(true)
    http.post.mockResolvedValueOnce({ data: decision('approved_pending_apply') })
    await button(wrapper, 'Approve review').trigger('click'); await flushPromises()
    expect(button(wrapper, 'Apply rights').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Nothing is stopped automatically')
  })
  it('does not invent native trust when no verified review is available', async () => {
    http.get.mockResolvedValue({ data: { ...status(), native_reviews: [] } })
    const wrapper = await open()
    expect(wrapper.text()).toContain('trusted reviewer')
    expect(wrapper.find('select').exists()).toBe(false)
    expect(http.post).not.toHaveBeenCalled()
  })
  it('expires actions locally without changing rights or automatically refreshing', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    http.post.mockResolvedValueOnce({ data: { ...plan(), expires_in_seconds: 2 } })
    const wrapper = await open(); await review(wrapper)
    await wrapper.find('input[type=checkbox]').setValue(true)
    await vi.advanceTimersByTimeAsync(3000)
    expect(button(wrapper, 'Approve review').attributes('disabled')).toBeDefined()
    expect(button(wrapper, 'Deny review').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('review expired')
    expect(http.post).toHaveBeenCalledTimes(1)
  })
  it('denial uses the exact current revision and leaves existing rights untouched', async () => {
    const wrapper = await open(); await review(wrapper)
    http.post.mockResolvedValueOnce({ data: decision('denied') })
    await button(wrapper, 'Deny review').trigger('click'); await flushPromises()
    expect(http.post.mock.calls[1]?.[1].expected_revision).toBe(identity('5'))
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(wrapper.text()).toContain('Existing rights were not changed')
  })
  it.each([
    [{ response: { status: 409, data: { detail: { code: 'stale_review' } } } }, 'review changed'],
    [new Error('lost response'), 'No automatic retry'],
    [{ response: { status: 403 } }, 'administrator login'],
  ])('discards unconfirmed review and never silently retries (%s)', async (cause, message) => {
    const wrapper = await open(); await review(wrapper)
    await wrapper.find('input[type=checkbox]').setValue(true)
    http.post.mockRejectedValueOnce(cause)
    await button(wrapper, 'Approve review').trigger('click'); await flushPromises()
    expect(wrapper.find('[role=alert]').text()).toContain(message)
    expect(wrapper.find('.authority-review-plan').exists()).toBe(false)
    expect(http.post).toHaveBeenCalledTimes(2)
  })
  it('revocation has a separate confirmation and uses current grant revision', async () => {
    const wrapper = await open()
    await button(wrapper, 'Revoke rights').trigger('click')
    expect(http.post).not.toHaveBeenCalled()
    await button(wrapper, 'Cancel').trigger('click')
    expect(http.post).not.toHaveBeenCalled()
    await button(wrapper, 'Revoke rights').trigger('click')
    http.post.mockResolvedValueOnce({ data: { state: 'revoked' } })
    http.get.mockResolvedValueOnce({ data: { ...status(), grant_state: 'revoked', grant_effective: false } })
    await button(wrapper, 'Confirm revocation').trigger('click'); await flushPromises()
    expect(http.post).toHaveBeenCalledWith(base + '/revoke', { request_id: expect.stringMatching(/^[a-f0-9]{32}$/), expected_revision: identity('3') }, { timeout: 12000 })
    expect(wrapper.text()).toContain('Rights revoked')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })
  it('holds the target during pending requests, avoids double sends, ignores late unmounted results', async () => {
    let resolve!: (value: unknown) => void
    http.post.mockImplementationOnce(() => new Promise(done => { resolve = done }))
    const wrapper = await open()
    await button(wrapper, 'Review requested access').trigger('click')
    await wrapper.find('.ui-dialog-heading button').trigger('click')
    await wrapper.trigger('cancel')
    expect(wrapper.emitted('close')).toBeUndefined()
    expect(button(wrapper, 'Review requested access').attributes('disabled')).toBeDefined()
    wrapper.unmount(); mounted.pop()
    resolve({ data: plan() }); await flushPromises()
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(http.post).toHaveBeenCalledTimes(1)
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
