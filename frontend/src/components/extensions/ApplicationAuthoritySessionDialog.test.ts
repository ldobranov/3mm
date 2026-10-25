import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const locale = vi.hoisted(() => ({ language: 'en' }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  const { movedLanguageLabel } = await import('@/test-utils/language-messages')
  return { useI18n: () => ({ currentLanguage: ref(locale.language), t: (key: string, fallback: string) => movedLanguageLabel(key, fallback, locale.language) }) }
})
import Dialog from './ApplicationAuthorityDialog.vue'
import { consentPreview, consentResult } from './application-consent.fixtures'
import { sessionModuleId, sessionPlan, sessionScope, sessionStatus } from './authority-sessions.fixtures'
let wrapper: VueWrapper
const methods = ['showModal', 'close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
beforeEach(() => {
  vi.resetAllMocks(); locale.language = 'en'
  http.get.mockResolvedValue({ data: sessionStatus() })
  http.post.mockResolvedValue({ data: consentPreview(sessionStatus(), sessionPlan().resources, sessionModuleId) })
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
const choice = () => wrapper.find('.authority-scope-choice input')
it('selects fresh session and own-account permissions before one explicit Allow', async () => {
  await open()
  expect((choice().element as HTMLInputElement).checked).toBe(true)
  expect((wrapper.find('.authority-user-choice input').element as HTMLInputElement).checked).toBe(true)
  for (const text of ['org.example.session-provider', 'console_use', 'resize', '80']) expect(wrapper.text()).toContain(text)
  expect(http.post).toHaveBeenCalledTimes(1)
  const value = consentPreview(sessionStatus(), sessionPlan().resources, sessionModuleId)
  http.post.mockResolvedValueOnce({ data: consentResult(value) })
  await click('Allow access')
  expect(http.post.mock.calls[1]![1]).toMatchObject({ scopes: [sessionScope], user_permissions: ['app_use'], accept_native_code: true })
  expect(wrapper.emitted('changed')).toHaveLength(1)
})
it('can uncheck the session without inventing any fallback or additional rights', async () => {
  await open(); await choice().setValue(false)
  http.post.mockRejectedValueOnce(new Error('lost response'))
  await click('Allow access')
  expect(http.post.mock.calls[1]![1].scopes).toEqual([])
  expect(http.post).toHaveBeenCalledTimes(2)
  expect(wrapper.find('[role=alert]').exists()).toBe(true)
})
it('keeps a saved stopped session selection without another Allow request', async () => {
  const current = { ...sessionStatus(), installation_enabled: false, installation_status: 'disabled' }
  http.get.mockResolvedValue({ data: current })
  http.post.mockResolvedValue({ data: { ...consentPreview(current, sessionPlan().resources, sessionModuleId), access_saved: true } })
  await open(); await click('Refresh status')
  expect((choice().element as HTMLInputElement).checked).toBe(true)
  expect(wrapper.text()).toContain('Rights saved, application stopped')
  expect(http.post.mock.calls.every(call => String(call[0]).endsWith('/consent/preview'))).toBe(true)
})
