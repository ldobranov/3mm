import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import languagePack from '../../../../modules/language-bg/language-extension.json'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/language-api', async () => {
  const pack = (await import('../../../../modules/language-bg/language-extension.json')).default
  return { readAvailableLanguages: async () => ['en', 'bg'],
    readFrontendTranslations: async (code: string) => code === pack.code ? pack.frontend : {},
    saveCurrentUserLanguage: vi.fn() }
})
import { i18n } from '@/utils/i18n'
import PlatformRuntimeUpdates from './PlatformRuntimeUpdates.vue'

const OLD = 'a'.repeat(64), NEW = 'b'.repeat(64), REQUEST = 'c'.repeat(32)
const dialogMethods = ['showModal', 'close'].map(name => ({ name,
  descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name) }))
const mounted: ReturnType<typeof mount>[] = []
function state() {
  return { current_build_id: OLD, previous_build_id: null, ready: true, recovery_required: false,
    features: { query_execution_contract: 1, event_delivery_contract: 1 }, reason: null,
    operation: { request_id: REQUEST, action: 'platform_runtime_prepare', state: 'succeeded',
      reason: 'candidate_prepared', updated_at: 1 },
    candidate: { candidate_id: REQUEST, build_id: NEW, sha256: 'd'.repeat(64), bytes: 30720,
      compatible: true, features: { query_execution_contract: 1 } } }
}
function view() {
  const wrapper = mount(PlatformRuntimeUpdates, { props: { maintenanceOverrideRequired: true } })
  mounted.push(wrapper)
  return wrapper
}

describe('Runtime card language-package delivery', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    await i18n.setLanguage('en', false)
    http.get.mockResolvedValue({ data: state() })
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true,
      value: function (this: HTMLDialogElement) { this.open = true } })
    Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true,
      value: function (this: HTMLDialogElement) { this.open = false } })
  })
  afterEach(async () => {
    mounted.splice(0).forEach(wrapper => wrapper.unmount())
    await i18n.setLanguage('en', false)
    for (const { name, descriptor } of dialogMethods) {
      if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
      else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
    }
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('uses actual Bulgarian messages for preparation, declaration gaps and exact-build confirmation', async () => {
    await i18n.setLanguage('bg', false)
    const wrapper = view()
    await flushPromises()
    const bg = languagePack.frontend.runtimeUpdates
    expect(wrapper.text()).toContain(bg.help)
    expect(wrapper.text()).toContain(bg.state.succeeded)
    expect(wrapper.text()).toContain(bg.reason.candidate_prepared)
    expect(wrapper.text()).toContain(bg.notDeclared)
    expect(wrapper.text()).toContain(REQUEST)
    await wrapper.findAll('button').find(button => button.text() === bg.update)!.trigger('click')
    await flushPromises()
    const dialog = wrapper.get('dialog')
    expect(dialog.text()).toContain(bg.confirmTitle)
    expect(dialog.text()).toContain(bg.confirmUpdate)
    expect(dialog.text()).toContain(bg.acknowledge)
    expect(dialog.text()).toContain(bg.override)
    expect(dialog.text()).toContain(NEW)
    expect(dialog.findAll('button').find(button => button.text() === bg.confirm)!.attributes('disabled')).toBeDefined()
    expect(http.post).not.toHaveBeenCalled()
  })

  it('renders the completed update in Bulgarian and can switch back to English without an operation', async () => {
    const completed = state()
    completed.current_build_id = NEW
    completed.candidate.compatible = false
    completed.operation.action = 'platform_runtime_apply'
    completed.operation.reason = 'runtime_updated'
    http.get.mockResolvedValue({ data: completed })
    await i18n.setLanguage('bg', false)
    const wrapper = view()
    await flushPromises()
    const bg = languagePack.frontend.runtimeUpdates
    expect(wrapper.text()).toContain(bg.reason.runtime_updated)
    expect(wrapper.text()).toContain(bg.same)
    expect(wrapper.text()).not.toContain(bg.stale)
    expect(wrapper.findAll('button').find(button => button.text() === bg.update)!.attributes('disabled')).toBeDefined()
    await i18n.setLanguage('en', false)
    await flushPromises()
    expect(wrapper.text()).toContain('Runtime updated and checked; Core stayed running.')
    expect(wrapper.text()).toContain('No update is needed')
    expect(wrapper.text()).not.toContain(bg.same)
    expect(http.post).not.toHaveBeenCalled()
    expect(http.get).toHaveBeenCalledTimes(1)
  })
})
