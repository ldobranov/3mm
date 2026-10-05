import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

const mocks = vi.hoisted(() => ({
  appearance: vi.fn(), settings: vi.fn(), css: vi.fn(), read: vi.fn(), mode: vi.fn(), language: vi.fn(),
}))
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => reactive({
  appearanceRecovery: false, previewDesign: null, installedDesign: null, uiDesign: {},
  loadThemeAppearance: mocks.appearance, loadSettings: mocks.settings, updateCSSVariables: mocks.css,
}) }))
vi.mock('@/stores/theme', () => ({ useThemeStore: () => ({ setTheme: mocks.mode }) }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ setLanguage: mocks.language }) }))
vi.mock('@/utils/ui-labels', () => ({ useUiLabels: () => () => 'Loading' }))
vi.mock('@/utils/settings-api', () => ({ readSettings: mocks.read }))
vi.mock('@/utils/dynamic-http', () => ({ default: { post: vi.fn() } }))
vi.mock('vue-router', () => ({ useRoute: () => ({ meta: {} }), RouterView: { template: '<main>Page</main>' } }))
vi.mock('./components/ui/ApplicationShell.vue', () => ({ default: { template: '<div data-shell><slot /></div>' } }))
vi.mock('./components/CommandPalette.vue', () => ({ default: { template: '<div data-palette />' } }))
import App from './App.vue'

const wrappers: ReturnType<typeof mount>[] = []
const render = () => { const wrapper = mount(App); wrappers.push(wrapper); return wrapper }

describe('Initial appearance gate', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.resetAllMocks()
    localStorage.clear()
    mocks.appearance.mockResolvedValue(undefined)
    mocks.settings.mockResolvedValue(undefined)
    mocks.read.mockResolvedValue([])
    mocks.language.mockResolvedValue(undefined)
  })
  afterEach(() => {
    wrappers.splice(0).forEach(wrapper => wrapper.unmount())
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('does not mount navigation, pages or palette until appearance resources and settings settle', async () => {
    let finishTheme!: () => void
    let finishSettings!: () => void
    mocks.appearance.mockImplementation(() => new Promise<void>(resolve => { finishTheme = resolve }))
    mocks.settings.mockImplementation(() => new Promise<void>(resolve => { finishSettings = resolve }))
    const wrapper = render()
    await flushPromises()
    expect(wrapper.find('[role="status"]').text()).toBe('Loading…')
    expect(wrapper.find('[data-shell]').exists()).toBe(false)
    expect(wrapper.find('[data-palette]').exists()).toBe(false)
    finishTheme()
    await flushPromises()
    expect(wrapper.find('[data-shell]').exists()).toBe(false)
    finishSettings()
    await flushPromises()
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.find('[data-shell]').text()).toBe('Page')
    expect(mocks.css).toHaveBeenCalled()
  })

  it('opens a usable fallback after eight seconds and retains refresh listeners', async () => {
    mocks.appearance.mockImplementation(() => new Promise(() => {}))
    mocks.read.mockImplementation(() => new Promise(() => {}))
    const wrapper = render()
    await vi.advanceTimersByTimeAsync(8000)
    await flushPromises()
    expect(mocks.appearance.mock.calls[0][0].aborted).toBe(true)
    expect(wrapper.find('[data-shell]').exists()).toBe(true)
    window.dispatchEvent(new Event('settings-updated'))
    expect(mocks.appearance).toHaveBeenCalledTimes(2)
    expect(mocks.settings).toHaveBeenCalledTimes(1)
  })

  it('does not reset a saved dark mode or language when settings fail', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    localStorage.setItem('theme', 'dark')
    localStorage.setItem('preferredLanguage', 'bg')
    mocks.read.mockRejectedValue(new Error('offline'))
    const wrapper = render()
    await flushPromises()
    expect(wrapper.find('[data-shell]').exists()).toBe(true)
    expect(mocks.mode).not.toHaveBeenCalled()
    expect(mocks.language).not.toHaveBeenCalled()
    expect(localStorage.getItem('theme')).toBe('dark')
    expect(localStorage.getItem('preferredLanguage')).toBe('bg')
  })

  it('cancels initialization when unmounted without registering late listeners', async () => {
    let finish!: () => void
    mocks.appearance.mockImplementation(() => new Promise<void>(resolve => { finish = resolve }))
    const wrapper = render()
    await flushPromises()
    wrapper.unmount()
    finish()
    await flushPromises()
    expect(mocks.appearance.mock.calls[0][0].aborted).toBe(true)
    expect(mocks.css).not.toHaveBeenCalled()
    window.dispatchEvent(new Event('settings-updated'))
    expect(mocks.appearance).toHaveBeenCalledTimes(1)
  })
})
