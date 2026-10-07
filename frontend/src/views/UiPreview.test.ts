import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({
  route: { query: {} as Record<string, string> }, replace: vi.fn(), post: vi.fn(),
  settings: { appearanceRecovery: false, setDesignPreview: vi.fn(), loadThemeAppearance: vi.fn() },
}))
vi.mock('vue-router', () => ({ useRoute: () => mocks.route, useRouter: () => ({ replace: mocks.replace }) }))
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => mocks.settings }))
vi.mock('@/utils/ui-labels', () => ({ useUiLabels: () => (key: string) => key }))
vi.mock('@/utils/dynamic-http', () => ({ default: { post: mocks.post } }))
import UiPreview from './UiPreview.vue'

describe('legacy preview bookmarks and independent recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks(); mocks.route.query = {}; mocks.settings.appearanceRecovery = false
    mocks.post.mockResolvedValue({ data: {} })
  })
  it('redirects old bookmarks to the integrated theme editor without changing selection', () => {
    const wrapper = mount(UiPreview)
    expect(mocks.replace).toHaveBeenCalledWith({ name: 'Settings', query: { section: 'theme' } })
    expect(mocks.post).not.toHaveBeenCalled()
    expect(wrapper.find('select').exists()).toBe(false)
    wrapper.unmount()
  })
  it('preserves explicit recovery without applying package controls or assets', async () => {
    mocks.route.query = { recovery: '1' }
    const wrapper = mount(UiPreview, { global: { stubs: { RouterLink: true } } })
    expect(mocks.settings.appearanceRecovery).toBe(true)
    expect(mocks.replace).not.toHaveBeenCalled()
    expect(wrapper.find('.ui-recovery').exists()).toBe(true)
    expect(mocks.post).not.toHaveBeenCalled()
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(mocks.post).toHaveBeenCalledWith('/api/v1/modules/themes/selection', { sha256: null })
    expect(mocks.post).toHaveBeenCalledWith('/api/v1/modules/themes/customization', { sha256: null, preferences: null })
    expect(mocks.settings.loadThemeAppearance).toHaveBeenCalledOnce()
    wrapper.unmount()
    expect(mocks.settings.appearanceRecovery).toBe(false)
  })
})
