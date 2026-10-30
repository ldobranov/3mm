import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ref } from 'vue'
import { builtinUiDesign } from '@/utils/ui-design'
import { designPreferences, parseThemePreferences } from '@/utils/theme-customization'
import { UiEditorForm } from '@/extension-ui/v1'
import ThemeComponentPreview from './ThemeComponentPreview.vue'

const mocks = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn(), getCurrentBackendUrl: async () => '' }))
vi.mock('@/utils/dynamic-http', () => ({ default: mocks }))
vi.mock('@/utils/settings-api', () => ({ readSettings: async () => [], upsertSettings: vi.fn() }))
const language = ref('en')
vi.mock('@/utils/i18n', async () => { const { movedLanguageLabel } = await import('@/test-utils/language-messages'); return { useI18n: () => ({ t: (key: string, fallback: string) => movedLanguageLabel(key, fallback, language.value), currentLanguage: language }) } })
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'
import ThemeAppearanceSection from './ThemeAppearanceSection.vue'

const projection = () => ({ package_sha256: 'a'.repeat(64), theme: {
  theme_extension_version: 2, design_api_version: 2, module_id: 'org.example.theme', version: '2.0.0',
  name: { en: 'Example' }, base_theme: 'builtin.default', design: { ...builtinUiDesign(), header_style: 'theme' }, assets: [],
} })
const read = (value: unknown) => vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => JSON.stringify(value) }))
const mounted: ReturnType<typeof mount>[] = []
const mountEditor = (sha256: string | null = 'a'.repeat(64)) => {
  const wrapper = mount(ThemeAppearanceSection, { props: { sha256 },
    global: { stubs: { RouterLink: true, ColorPicker: { props: ['label', 'modelValue'], emits: ['update:modelValue'],
      template: '<label>{{ label }}<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" /></label>' } } },
  })
  mounted.push(wrapper)
  return wrapper
}
const field = (wrapper: ReturnType<typeof mountEditor>, key: string) => wrapper.get(`[data-field="${key}"] select`)
const saveButton = (wrapper: ReturnType<typeof mountEditor>) => wrapper.get('.appearance-workbench > form [type=submit]')
const form = (wrapper: ReturnType<typeof mountEditor>) => wrapper.get('.appearance-workbench > form')
const discard = (wrapper: ReturnType<typeof mountEditor>) => wrapper.get('.appearance-workbench > form .ui-editor-actions button')
let settings: ReturnType<typeof useSettingsStore>

beforeEach(async () => {
  vi.clearAllMocks(); localStorage.clear(); language.value = 'en'; setActivePinia(createPinia())
  mocks.post.mockResolvedValue({ data: {} }); read(projection())
  mocks.get.mockResolvedValue({ data: { items: [] } })
  settings = useSettingsStore(); await settings.loadThemeAppearance()
})
afterEach(() => { mounted.splice(0).forEach(w => w.unmount()); vi.unstubAllGlobals(); document.documentElement.style.cssText = '' })

describe('one theme editor with an isolated CAP09 draft', () => {
  it('saves menu placements and sticky zones only with the appearance; discard restores the saved layout', async () => {
    mocks.get.mockResolvedValue({ data: { items: [
      { id: 1, name: 'Main', is_active: true }, { id: 2, name: 'Footer', is_active: false },
    ] } })
    const wrapper = mountEditor(); await flushPromises()
    await wrapper.get('[data-menu-id="2"] select').setValue('footer')
    await wrapper.get('[data-sticky="header"] input').setValue(true)
    expect(settings.menuLayout).toBeNull()
    expect(mocks.post).not.toHaveBeenCalled()
    expect(wrapper.get('[data-preview-region="footer"]').text()).toContain('Footer')
    await discard(wrapper).trigger('click')
    expect(wrapper.get('[data-menu-id="2"] select').element).toHaveProperty('value', 'hidden')
    expect(wrapper.get('[data-sticky="header"] input').element).toHaveProperty('checked', false)
    await wrapper.get('[data-menu-id="2"] select').setValue('footer')
    await wrapper.get('[data-sticky="footer"] input').setValue(true)
    const menu_layout = { placements: [{ menu_id: 1, location: 'primary' }, { menu_id: 2, location: 'footer' }],
      sticky: { header: false, sidebar: false, footer: true } }
    const saved = { ...designPreferences(settings.baseUiDesign, settings.headerSettings), menu_layout }
    read({ ...projection(), customization: saved })
    await form(wrapper).trigger('submit'); await flushPromises()
    expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/api/v1/modules/themes/customization', { sha256: 'a'.repeat(64), preferences: saved })
    expect(settings.menuLayout).toEqual(menu_layout)
  })
  it('uses the shared editor and previews changes without restyling the installation', async () => {
    const wrapper = mountEditor()
    const original = document.documentElement.style.cssText
    expect(wrapper.findComponent(UiEditorForm).exists()).toBe(true)
    await field(wrapper, 'navigation').setValue('top')
    await field(wrapper, 'button').setValue('outline')
    expect(wrapper.findComponent(ThemeComponentPreview).props('design')).toMatchObject({ layout: { navigation: 'top' }, components: { button: 'outline' } })
    expect(settings.uiDesign.layout.navigation).toBe('sidebar')
    expect(settings.uiDesign.components.button).toBe('solid')
    expect(document.documentElement.style.cssText).toBe(original)
    expect(mocks.post).not.toHaveBeenCalled()
    await discard(wrapper).trigger('click')
    expect(field(wrapper, 'navigation').element).toHaveProperty('value', 'sidebar')
    expect(saveButton(wrapper).attributes('disabled')).toBeDefined()
  })
  it('edits the single built-in palette through the same editor', async () => {
    read({ theme: null }); await settings.loadThemeAppearance()
    const wrapper = mountEditor(null)
    expect(wrapper.findAll('[data-color]')).toHaveLength(17)
    await wrapper.get('[data-color=border] input').setValue('#123456')
    const saved = { ...designPreferences(settings.baseUiDesign, settings.headerSettings), colors: { light: { border: '#123456' } } }
    read({ theme: null, customization: saved })
    await form(wrapper).trigger('submit'); await flushPromises()
    expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/api/v1/modules/themes/customization', { sha256: null, preferences: saved })
    expect(settings.uiDesign.light.border).toBe('#123456')
    expect(saveButton(wrapper).attributes('disabled')).toBeDefined()
  })
  it('offers only declared package choices without another color/default editor', async () => {
    read({ ...projection(), theme: { ...projection().theme, customization_options: { navigation: ['sidebar', 'top'], colors: ['border'] } } })
    await settings.loadThemeAppearance()
    const wrapper = mountEditor()
    expect(field(wrapper, 'navigation').findAll('option')).toHaveLength(2)
    for (const key of ['density', 'button', 'card', 'custom-header']) expect(wrapper.find(`[data-field="${key}"]`).exists()).toBe(false)
    expect(wrapper.findAll('[data-color]')).toHaveLength(1)
  })
  it('saves both palettes once, preserves the package, then reflects a confirmed reload', async () => {
    const wrapper = mountEditor(), before = JSON.stringify(settings.activeTheme)
    await wrapper.get('[data-color=border] input').setValue('#123456')
    await field(wrapper, 'palette-mode').setValue('dark')
    expect(useThemeStore().theme).toBe('light')
    expect(localStorage.getItem('theme')).toBeNull()
    expect(wrapper.get('.component-preview').attributes('data-mode')).toBe('dark')
    await wrapper.get('[data-color=border] input').setValue('#ABCDEF')
    const saved = { ...designPreferences(settings.baseUiDesign, settings.headerSettings),
      colors: { light: { border: '#123456' }, dark: { border: '#ABCDEF' } } }
    read({ ...projection(), customization: saved })
    await form(wrapper).trigger('submit'); await flushPromises()
    expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/api/v1/modules/themes/customization', { sha256: 'a'.repeat(64), preferences: saved })
    expect(settings.uiDesign.light.border).toBe('#123456')
    expect(settings.uiDesign.dark.border).toBe('#ABCDEF')
    expect(JSON.stringify(settings.activeTheme)).toBe(before)
    expect(wrapper.text()).toContain('Appearance saved.')
  })
  it('loads defaults into the draft only; palette reset and discard never write', async () => {
    settings.themePreferences = { ...designPreferences(settings.baseUiDesign, settings.headerSettings),
      navigation: 'top', colors: { light: { border: '#123456' }, dark: { border: '#ABCDEF' } } }
    const wrapper = mountEditor()
    await wrapper.get('[data-action=reset-palette]').trigger('click')
    expect(wrapper.findComponent(ThemeComponentPreview).props('design')).toMatchObject({ light: { border: builtinUiDesign().light.border } })
    expect(settings.uiDesign.light.border).toBe('#123456')
    await wrapper.get('[data-action=reset]').trigger('click')
    expect(field(wrapper, 'navigation').element).toHaveProperty('value', 'sidebar')
    expect(settings.uiDesign.layout.navigation).toBe('top')
    await discard(wrapper).trigger('click')
    expect(field(wrapper, 'navigation').element).toHaveProperty('value', 'top')
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('blocks unreadable colors and keeps the saved appearance in the preview', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-color=text] input').setValue('#ffffff')
    expect(saveButton(wrapper).attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('4.5:1')
    expect(wrapper.findComponent(ThemeComponentPreview).props('design')).toMatchObject({ light: { text: builtinUiDesign().light.text } })
    expect(parseThemePreferences({ ...designPreferences(settings.baseUiDesign, settings.headerSettings), navigation: ['top'] })).toBeNull()
    expect(parseThemePreferences({ ...designPreferences(settings.baseUiDesign, settings.headerSettings), colors: { light: { border: 'url(https://bad.test)' } } })).toBeNull()
    await form(wrapper).trigger('submit')
    expect(mocks.post).not.toHaveBeenCalled()
    await discard(wrapper).trigger('click')
    expect(wrapper.find('.appearance-workbench > form [role=alert]').exists()).toBe(false)
  })
  it('keeps header draft and branding separate from the saved shell', async () => {
    const wrapper = mountEditor(), original = { ...settings.headerSettings }
    await wrapper.get('[data-field=custom-header] input').setValue(true)
    expect(saveButton(wrapper).attributes('disabled')).toBeDefined()
    await wrapper.get('[data-field=header-background] input').setValue('#123456')
    expect(wrapper.findComponent(ThemeComponentPreview).props('design')).toMatchObject({ header_style: 'saved' })
    expect(wrapper.findComponent(ThemeComponentPreview).props('header')).toMatchObject({ backgroundColor: '#123456' })
    expect(settings.headerSettings).toEqual(original)
    expect(settings.uiDesign.header_style).toBe('theme')
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('saves personal mode separately and preserves the palette draft', async () => {
    localStorage.setItem('authToken', 'fixture')
    const wrapper = mountEditor()
    await wrapper.get('[data-color=border] input').setValue('#123456')
    await field(wrapper, 'mode').setValue('dark'); await flushPromises()
    expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/settings/create', { key: 'user_theme', value: 'dark', description: 'User theme preference' })
    expect(field(wrapper, 'palette-mode').element).toHaveProperty('value', 'light')
    expect(wrapper.get('[data-color=border] input').element).toHaveProperty('value', '#123456')
    expect(settings.themePreferences).toBeNull()
  })
  it('locks a lost save reply without replay; explicit read resolves the saved outcome', async () => {
    mocks.post.mockRejectedValue(new Error('lost reply'))
    const wrapper = mountEditor()
    await field(wrapper, 'navigation').setValue('top')
    await form(wrapper).trigger('submit'); await flushPromises()
    expect(wrapper.findComponent(UiEditorForm).props('state')).toBe('unconfirmed')
    expect(saveButton(wrapper).attributes('disabled')).toBeDefined()
    expect(discard(wrapper).attributes('disabled')).toBeDefined()
    await form(wrapper).trigger('submit')
    expect(mocks.post).toHaveBeenCalledTimes(1)
    const saved = { ...designPreferences(settings.baseUiDesign, settings.headerSettings), navigation: 'top' }
    read({ ...projection(), customization: saved })
    await wrapper.get('[data-action=reload]').trigger('click'); await flushPromises()
    expect(wrapper.findComponent(UiEditorForm).props('state')).toBe('idle')
    expect(saveButton(wrapper).attributes('disabled')).toBeDefined()
    expect(settings.uiDesign.layout.navigation).toBe('top')
    expect(mocks.post).toHaveBeenCalledTimes(1)
  })
  it('preserves a conflicting draft and remains locked when the read is unavailable', async () => {
    const wrapper = mountEditor()
    await field(wrapper, 'button').setValue('outline')
    settings.themePreferences = { ...designPreferences(settings.baseUiDesign, settings.headerSettings), navigation: 'top' }
    await flushPromises()
    expect(wrapper.findComponent(UiEditorForm).props('state')).toBe('conflict')
    expect(field(wrapper, 'button').element).toHaveProperty('value', 'outline')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    await wrapper.get('[data-action=reload]').trigger('click'); await flushPromises()
    expect(wrapper.findComponent(UiEditorForm).props('state')).toBe('conflict')
    expect(field(wrapper, 'button').element).toHaveProperty('value', 'outline')
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('keeps drafts while switching language and discards them on section exit', async () => {
    const wrapper = mountEditor()
    await field(wrapper, 'navigation').setValue('top')
    language.value = 'bg'; await flushPromises()
    expect(wrapper.text()).toContain('Запази оформлението')
    expect(field(wrapper, 'navigation').element).toHaveProperty('value', 'top')
    wrapper.unmount()
    expect(settings.uiDesign.layout.navigation).toBe('sidebar')
    expect(mocks.post).not.toHaveBeenCalled()
  })
})
