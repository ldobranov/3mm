import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ref } from 'vue'
import { builtinUiDesign } from '@/utils/ui-design'
import { designPreferences, parseThemePreferences } from '@/utils/theme-customization'

const mocks = vi.hoisted(() => ({ post: vi.fn(), getCurrentBackendUrl: async () => '' }))
vi.mock('@/utils/dynamic-http', () => ({ default: mocks }))
vi.mock('@/utils/settings-api', () => ({ readSettings: async () => [], upsertSettings: vi.fn() }))
const language = ref('en')
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_key: string, fallback: string) => fallback, currentLanguage: language }) }))
import { useSettingsStore } from '@/stores/settings'
import ThemeAppearanceSection from './ThemeAppearanceSection.vue'

const projection = () => ({ package_sha256: 'a'.repeat(64), theme: {
  theme_extension_version: 2, design_api_version: 2, module_id: 'org.example.theme', version: '2.0.0',
  name: { en: 'Example' }, base_theme: 'builtin.default', design: { ...builtinUiDesign(), header_style: 'theme' }, assets: [],
} })
const mountEditor = () => mount(ThemeAppearanceSection, { props: { sha256: 'a'.repeat(64) },
  global: { stubs: { RouterLink: { template: '<a><slot /></a>' },
    ColorPicker: { props: ['label', 'modelValue'], emits: ['update:modelValue'],
      template: '<label>{{ label }}<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" /></label>' } } },
})
let settings: ReturnType<typeof useSettingsStore>
describe('saved theme appearance controls', () => {
  beforeEach(async () => {
    vi.clearAllMocks(); localStorage.clear(); language.value = 'en'; setActivePinia(createPinia())
    mocks.post.mockResolvedValue({ data: {} })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => JSON.stringify(projection()) }))
    settings = useSettingsStore(); await settings.loadThemeAppearance()
  })
  afterEach(() => { vi.unstubAllGlobals(); document.documentElement.style.cssText = '' })
  it('previews without writes, saves exact-theme preferences and reloads them', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-field=navigation]').setValue('top')
    expect(settings.uiDesign.layout.navigation).toBe('top')
    expect(mocks.post).not.toHaveBeenCalled()
    const saved = { ...designPreferences(settings.baseUiDesign, settings.headerSettings), navigation: 'top' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => JSON.stringify({ ...projection(), customization: saved }) }))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(mocks.post).toHaveBeenCalledWith('/api/v1/modules/themes/customization', { sha256: 'a'.repeat(64), preferences: saved })
    expect(settings.preferencePreview).toBeNull()
    expect(wrapper.text()).toContain('Appearance saved.')
    expect(wrapper.get('[type=submit]').attributes('disabled')).toBeDefined()
    await settings.loadThemeAppearance(); await flushPromises()
    expect(wrapper.text()).toContain('Appearance saved.')
    wrapper.unmount(); await settings.loadThemeAppearance()
    expect(settings.uiDesign.layout.navigation).toBe('top')
    expect(settings.activeTheme?.theme_extension_version).toBe(2)
  })
  it('discards unsaved edits on section exit, and keeps failed saves unsaved', async () => {
    mocks.post.mockRejectedValue(new Error('offline'))
    const wrapper = mountEditor()
    await wrapper.get('[data-field=navigation]').setValue('top')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('Could not save')
    expect(settings.preferencePreview?.navigation).toBe('top')
    wrapper.unmount()
    expect(settings.preferencePreview).toBeNull()
    expect(settings.uiDesign.layout.navigation).toBe('sidebar')
  })
  it('prevents unreadable custom header colors and does not modify branding', async () => {
    const wrapper = mountEditor()
    const original = { ...settings.headerSettings }
    await wrapper.get('[data-field=custom-header]').setValue(true)
    expect(wrapper.get('[type=submit]').attributes('disabled')).toBeDefined()
    await wrapper.findAll('input')[1].setValue('#123456')
    expect(settings.uiDesign.header_style).toBe('saved')
    expect(document.documentElement.style.getPropertyValue('--ui-header-bg')).toBe('#123456')
    expect(settings.headerSettings).toEqual(original)
    expect(mocks.post).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('resets saved preferences and localizes the editor without changing personal mode', async () => {
    settings.themePreferences = { ...designPreferences(settings.baseUiDesign, settings.headerSettings), navigation: 'top' }
    const wrapper = mountEditor()
    await wrapper.findAll('button')[2].trigger('click'); await flushPromises()
    expect(mocks.post).toHaveBeenCalledWith('/api/v1/modules/themes/customization', { sha256: 'a'.repeat(64), preferences: null })
    expect(settings.uiDesign.layout.navigation).toBe('sidebar')
    expect(wrapper.text()).toContain('Theme defaults restored.')
    language.value = 'bg'; await flushPromises()
    expect(wrapper.text()).toContain('Запази оформлението')
    wrapper.unmount()
  })
  it('rejects coercible enum values and keeps legacy colors when preparing built-in controls', async () => {
    const original = { ...settings.headerSettings }
    const prefs = designPreferences(settings.baseUiDesign, settings.headerSettings)
    expect(parseThemePreferences({ ...prefs, navigation: ['top'] })).toBeNull()
    settings.activeTheme = null
    const wrapper = mount(ThemeAppearanceSection, { props: { sha256: null }, global: { stubs: { RouterLink: true, ColorPicker: true } } })
    expect(wrapper.find('[role=alert]').exists()).toBe(false)
    expect(settings.headerSettings).toEqual(original)
    expect(settings.preferencePreview).toBeNull()
    wrapper.unmount()
  })
  it('saves personal mode through existing preferences, separately from installation appearance', async () => {
    localStorage.setItem('authToken', 'fixture')
    const wrapper = mountEditor()
    await wrapper.get('[data-field=mode]').setValue('dark'); await flushPromises()
    expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/settings/create', { key: 'user_theme', value: 'dark', description: 'User theme preference' })
    expect(wrapper.get('[type=submit]').attributes('disabled')).toBeDefined()
    expect(settings.themePreferences).toBeNull()
    expect(localStorage.getItem('theme')).toBe('dark')
    wrapper.unmount()
  })
})
