import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import ApplicationRecoveryDialog from './ApplicationRecoveryDialog.vue'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ currentLanguage: ref('en') }) }))
const moduleId = 'org.example.pending'
const initial = { module_id: moduleId, status: 'recovery_required', enabled: false,
  active_version: null, error: 'Application lifecycle outcome is unconfirmed; administrative recovery is required' }
const stopped = { ...initial, status: 'disabled', error: null }
const mounted: ReturnType<typeof mount>[] = []
const nativeMethods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
async function open() {
  const wrapper = mount(ApplicationRecoveryDialog, { props: { moduleId, name: 'Example application' } })
  mounted.push(wrapper); await flushPromises(); return wrapper
}
beforeEach(() => {
  vi.resetAllMocks()
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.open = true } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value() { this.open = false } })
  http.get.mockResolvedValue({ data: [initial] })
  http.post.mockResolvedValue({ data: stopped })
})
afterEach(() => {
  mounted.splice(0).forEach(wrapper => wrapper.unmount())
  for (const { name, descriptor } of nativeMethods) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
  }
})

describe('explicit web lifecycle recovery', () => {
  it('shows the current stage and requires external-effect review before one stop request', async () => {
    const wrapper = await open()
    expect(wrapper.text()).toContain('recovery_required')
    expect(wrapper.text()).toContain('administrative recovery is required')
    expect(wrapper.get('.recover-confirm-btn').attributes('disabled')).toBeDefined()
    expect(http.post).not.toHaveBeenCalled()
    await wrapper.get('input').setValue(true)
    await wrapper.get('.recover-confirm-btn').trigger('click'); await flushPromises()
    expect(http.post).toHaveBeenCalledExactlyOnceWith(`/api/v1/application-extensions/${moduleId}/lifecycle/recover`,
      { confirmed_external_outcome_reviewed: true }, { timeout: 60000 })
    expect(wrapper.emitted('recovered')).toHaveLength(1)
  })

  it.each(['active', 'disabled', 'missing', 'unavailable'])('does not recover an ineligible or unknown stage (%s)', async stage => {
    if (stage === 'unavailable') http.get.mockRejectedValue(new Error('offline'))
    else http.get.mockResolvedValue({ data: stage === 'missing' ? [] : [{ ...initial, status: stage }] })
    const wrapper = await open()
    expect(wrapper.get('.recover-confirm-btn').attributes('disabled')).toBeDefined()
    expect(http.post).not.toHaveBeenCalled()
  })

  it.each(['timeout', 'conflict', 'wrong_module', 'active_reply'])('requires a read-only refresh after an uncertain result (%s)', async mode => {
    if (mode === 'timeout' || mode === 'conflict') http.post.mockRejectedValue({ response: { status: 409 } })
    else http.post.mockResolvedValue({ data: mode === 'wrong_module' ? { ...stopped, module_id: 'org.example.other' } : initial })
    const wrapper = await open()
    await wrapper.get('input').setValue(true)
    await wrapper.get('.recover-confirm-btn').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('Recovery could not be confirmed')
    expect(wrapper.emitted('recovered')).toBeUndefined()
    expect(wrapper.get('.recover-confirm-btn').attributes('disabled')).toBeDefined()
    expect(wrapper.get('input').attributes('disabled')).toBeDefined()
    http.get.mockResolvedValue({ data: [stopped] })
    await wrapper.findAll('button').find(button => button.text() === 'Refresh status')!.trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('Review access before activating a package')
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('recovered')).toBeUndefined()
  })

  it('keeps one request and a stable dialog while recovery is pending', async () => {
    let finish!: (value: unknown) => void
    http.post.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const wrapper = await open()
    await wrapper.get('input').setValue(true)
    await wrapper.get('.recover-confirm-btn').trigger('click')
    await wrapper.get('.recover-confirm-btn').trigger('click')
    await wrapper.get('dialog').trigger('cancel')
    await wrapper.findAll('button').find(button => button.text() === 'Close')!.trigger('click')
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('close')).toBeUndefined()
    expect(wrapper.text()).toContain('Stopping and verifying')
    finish({ data: stopped }); await flushPromises()
    expect(wrapper.emitted('recovered')).toHaveLength(1)
  })
})
