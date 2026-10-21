import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const locale = vi.hoisted(() => ({ language: 'en' }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  return { useI18n: () => ({ currentLanguage: ref(locale.language), t: (_key: string, fallback: string) => fallback }) }
})
import Dialog from './ApplicationAuthorityDialog.vue'
import { sessionModuleId, sessionPlan, sessionScope, sessionStatus } from './authority-sessions.fixtures'
let wrapper: VueWrapper
const methods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
beforeEach(() => {
  vi.resetAllMocks(); locale.language = 'en'
  http.get.mockResolvedValue({ data: sessionStatus() })
  http.post.mockImplementation(async (_path, body) => ({ data: sessionPlan(body.scopes) }))
  for (const { name } of methods) Object.defineProperty(HTMLDialogElement.prototype, name, { configurable: true, value: function(this: HTMLDialogElement) { this.open = name === 'showModal' } })
})
afterEach(() => {
  wrapper?.unmount(); vi.useRealTimers(); document.body.innerHTML = ''
  for (const { name, descriptor } of methods) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
  }
})
async function open() { wrapper = mount(Dialog, { attachTo: document.body, props: { moduleId: sessionModuleId, name: 'Session reference' } }); await flushPromises() }
async function click(text: string) { const button = wrapper.findAll('button').find(item => item.text() === text); if (!button) throw new Error(text); await button.trigger('click'); await flushPromises() }
const choice = () => wrapper.find('.authority-session-choice input')
it('requires explicit session opt-in, a fresh review, acknowledgment, approve and separate apply', async () => {
  await open(); await click('Review requested access')
  expect(http.post.mock.calls[0]![1].scopes).toEqual([])
  expect((choice().element as HTMLInputElement).checked).toBe(false)
  for (const text of ['org.example.session-provider', 'console_use', 'Read output and send input', 'resize', 'does not launch a process', 'Session transport is not connected']) expect(wrapper.text()).toContain(text)
  await wrapper.find('.authority-acknowledge input').setValue(true)
  await choice().setValue(true)
  expect(wrapper.find('.authority-acknowledge').exists()).toBe(false)
  await click('Review changed selection')
  expect(http.post.mock.calls[1]![1].scopes).toEqual([sessionScope])
  await wrapper.find('.authority-acknowledge input').setValue(true)
  http.post.mockResolvedValueOnce({ data: { ...sessionPlan([sessionScope]), state: 'approved_pending_apply', revision: '8'.repeat(32) } })
  await click('Approve review')
  expect(wrapper.emitted('changed')).toBeUndefined()
  expect(choice().attributes('disabled')).toBeDefined()
  http.post.mockResolvedValueOnce({ data: { ...sessionPlan([sessionScope]), state: 'applied', revision: '9'.repeat(32) } })
  await click('Apply rights')
  expect(wrapper.emitted('changed')).toHaveLength(1)
  expect(wrapper.find('.authority-effective').exists()).toBe(false)
})
it('resets choices on refresh and never retries an uncertain review', async () => {
  await open(); await click('Review requested access'); await choice().setValue(true)
  await click('Refresh status'); await click('Review requested access')
  expect(http.post.mock.calls[1]![1].scopes).toEqual([])
  await choice().setValue(true); http.post.mockRejectedValueOnce(new Error('lost'))
  await click('Review changed selection')
  expect(http.post).toHaveBeenCalledTimes(3)
  expect(wrapper.find('.authority-session').exists()).toBe(false)
  expect(wrapper.text()).toContain('No automatic retry')
})
it('renders the precise Bulgarian approval boundary', async () => {
  locale.language = 'bg'; await open(); await click('Прегледай заявения достъп')
  for (const text of ['Интерактивни сесии', 'Точно устройство', 'console_use', 'не дава root достъп', 'Сесийният транспорт не е свързан', 'започват неизбрани']) expect(wrapper.text()).toContain(text)
})
