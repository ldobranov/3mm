import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, defineComponent, h, provide, ref } from 'vue'
import { extensionUiKey } from '@/extension-ui/context'
import { UiField, UiForm, UiState, UiSurface } from '@/extension-ui/v1'
import ThemeComponentPreview from './ThemeComponentPreview.vue'
import ThemeAppearanceSection from './ThemeAppearanceSection.vue'
import { builtinUiDesign } from '@/utils/ui-design'
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'

const http = vi.hoisted(() => ({ post: vi.fn(), getCurrentBackendUrl: async () => '' }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/settings-api', () => ({ readSettings: async () => [], upsertSettings: vi.fn() }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ currentLanguage: ref('en'), t: (_key: string, fallback: string) => fallback }) }))
const mounted: ReturnType<typeof mount>[] = []
const projection = () => ({ package_sha256: 'a'.repeat(64), theme: {
  theme_extension_version: 2, design_api_version: 2, module_id: 'org.example.theme', version: '2.0.0',
  name: { en: 'Example' }, base_theme: 'builtin.default', design: { ...builtinUiDesign(), header_style: 'theme' }, assets: [],
} })
beforeEach(() => {
  localStorage.clear(); setActivePinia(createPinia()); vi.clearAllMocks()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => JSON.stringify(projection()) }))
  http.post.mockResolvedValue({ data: {} })
})
afterEach(() => {
  mounted.splice(0).forEach(wrapper => wrapper.unmount())
  document.documentElement.style.cssText = ''; vi.unstubAllGlobals()
})

describe('Settings uses the public SDK presentation', () => {
  it('shares fields/forms/tables/states and keeps the draft when palette, density and variants change', async () => {
    const settings = useSettingsStore()
    await settings.loadThemeAppearance()
    const wrapper = mount(ThemeComponentPreview, { props: { mode: 'light' } }); mounted.push(wrapper)
    for (const component of [UiSurface, UiField, UiForm, UiState]) expect(wrapper.findComponent(component).exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'UiTable' }).exists()).toBe(true)
    const field = wrapper.findAllComponents(UiField).find(component => component.props('type') === 'text' && !component.props('disabled'))!
    const input = field.get('input')
    await input.setValue('Unsaved preview draft')
    const design = builtinUiDesign()
    design.components = { button: 'outline', card: 'raised' }; design.layout.density = 'comfortable'
    design.scale.radius_sm = 0; design.typography.base_size = 18; design.header_style = 'theme'
    expect(settings.setDesignPreview(design)).toBe(true)
    await wrapper.setProps({ mode: 'dark' })
    expect(field.get('input').element).toBe(input.element)
    expect(input.element).toHaveProperty('value', 'Unsaved preview draft')
    expect(wrapper.attributes()).toMatchObject({ 'data-button': 'outline', 'data-card': 'raised', 'data-mode': 'dark' })
    expect(wrapper.attributes('style')).toContain('--ui-color-scheme: dark')
    expect(wrapper.attributes('style')).toContain('--ui-control-height: 44px')
    expect(wrapper.attributes('style')).toContain('--ui-radius-sm: 0px')
    expect(wrapper.attributes('style')).toContain('--ui-font-size: 18px')
    expect(http.post).not.toHaveBeenCalled()
    expect(wrapper.findComponent(UiForm).emitted('submit')).toBeUndefined()
  })

  it('keeps application drafts mounted through Settings save and reloading the saved theme', async () => {
    const settings = useSettingsStore(); await settings.loadThemeAppearance()
    const draft = ref('')
    const host = defineComponent({ setup() {
      provide(extensionUiKey, computed(() => settings.uiDesign.components))
      return () => h('div', [h(ThemeAppearanceSection, { sha256: 'a'.repeat(64) }),
        h(UiSurface, { class: 'application-consumer' }, () => h(UiField, { id: 'app-draft', label: 'Application draft',
          modelValue: draft.value, 'onUpdate:modelValue': (value: string | boolean) => { draft.value = String(value) } }))])
    } })
    const wrapper = mount(host); mounted.push(wrapper)
    const input = wrapper.get('#app-draft')
    await input.setValue('Keep after save')
    await wrapper.get('[data-field=button] select').setValue('outline')
    await wrapper.get('[data-field=card] select').setValue('raised')
    await wrapper.get('[data-field=density] select').setValue('comfortable')
    await wrapper.get('[data-color=border] input[type=text]').setValue('#123456')
    expect(http.post).not.toHaveBeenCalled()
    const editor = wrapper.findComponent(ThemeAppearanceSection)
    const preview = editor.findComponent(ThemeComponentPreview).props('design')!
    const saved = { navigation: preview.layout.navigation, density: preview.layout.density, ...preview.components,
      header_style: preview.header_style, header_background_color: settings.headerSettings.backgroundColor,
      header_text_color: settings.headerSettings.textColor, colors: { light: { border: '#123456' } } }
    expect(settings.uiDesign.components.button).toBe('solid')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => JSON.stringify({ ...projection(), customization: saved }) }))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    await settings.loadThemeAppearance(); await flushPromises()
    expect(http.post).toHaveBeenCalledExactlyOnceWith('/api/v1/modules/themes/customization', { sha256: 'a'.repeat(64), preferences: saved })
    for (const surface of wrapper.findAllComponents(UiSurface)) expect(surface.attributes()).toMatchObject({ 'data-button': 'outline', 'data-card': 'raised' })
    expect(settings.uiDesign.light.border).toBe('#123456')
    expect(input.element).toHaveProperty('value', 'Keep after save')
    expect(wrapper.get('#app-draft').element).toBe(input.element)
    useThemeStore().setTheme('dark'); await flushPromises()
    expect(wrapper.get('#app-draft').element).toBe(input.element)
    expect(http.post).toHaveBeenCalledTimes(1)
  })
})
