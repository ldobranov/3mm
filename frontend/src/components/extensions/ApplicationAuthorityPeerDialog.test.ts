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
import { consentPreview } from './application-consent.fixtures'
import { peerModuleId, peerOwner, peerPlan, peerResources, peerScopes, peerStatus } from './authority-peer-reads.fixtures'

const base = `/api/v1/application-extensions/${peerModuleId}/authority`
const wrappers: VueWrapper[] = []
const methods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
beforeEach(() => {
  vi.resetAllMocks(); locale.language = 'en'
  http.get.mockResolvedValue({ data: peerStatus() })
  http.post.mockResolvedValue({ data: consentPreview(peerStatus(), peerPlan().resources, peerModuleId) })
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false } })
})
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.useRealTimers()
  for (const { name, descriptor } of methods) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
  }
  document.body.innerHTML = ''
})
async function open() {
  const wrapper = mount(ApplicationAuthorityDialog, { attachTo: document.body, props: { moduleId: peerModuleId, name: 'Peer reference' } })
  wrappers.push(wrapper); await flushPromises(); return wrapper
}
function button(wrapper: VueWrapper, text: string) {
  const found = wrapper.findAll('button').find(item => item.text() === text)
  if (!found) throw new Error('Missing button: ' + text)
  return found
}
async function click(wrapper: VueWrapper, text: string) { await button(wrapper, text).trigger('click'); await flushPromises() }
const choices = (wrapper: VueWrapper) => wrapper.findAll('.authority-scope-choice input')
describe('peer permissions in one consent', () => {
  it('selects every fresh peer by default without approving it on open', async () => {
    const wrapper = await open()
    expect(choices(wrapper)).toHaveLength(2)
    expect(choices(wrapper).every(item => (item.element as HTMLInputElement).checked)).toBe(true)
    expect(http.post.mock.calls[0]![0]).toBe(base + '/consent/preview')
    for (const text of ['https://receiver.example', 'org.example.receiver', 'remote_link', 'second_link', peerResources()[0]!.receiver_identity.key_id]) expect(wrapper.text()).toContain(text)
    expect(button(wrapper, 'Allow access').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('select').exists()).toBe(false)
  })
  it('keeps an explicitly saved peer subset on refresh', async () => {
    http.post.mockResolvedValue({ data: { ...consentPreview(peerStatus(), peerPlan().resources, peerModuleId),
      access_saved: true, selected_scopes: [peerScopes()[1]] } })
    const wrapper = await open()
    expect((choices(wrapper)[0]!.element as HTMLInputElement).checked).toBe(false)
    expect((choices(wrapper)[1]!.element as HTMLInputElement).checked).toBe(true)
    await click(wrapper, 'Refresh status')
    expect((choices(wrapper)[0]!.element as HTMLInputElement).checked).toBe(false)
    expect(http.post.mock.calls.every(call => String(call[0]).endsWith('/consent/preview'))).toBe(true)
  })
  it('rejects a preview whose peer belongs to another application', async () => {
    const value = consentPreview(peerStatus(), peerPlan().resources, peerModuleId)
    value.resources.peer_reads[0]!.owner = { ...peerOwner(), module_id: 'org.example.foreign' }
    http.post.mockResolvedValue({ data: value })
    const wrapper = await open()
    expect(wrapper.find('[role=alert]').exists()).toBe(true)
    expect(button(wrapper, 'Allow access').attributes('disabled')).toBeDefined()
  })
})
