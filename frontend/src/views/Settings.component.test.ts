import { flushPromises, mount } from '@vue/test-utils'
import { reactive, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
const saves = vi.hoisted(() => ({ upsert: vi.fn(), header: vi.fn(), load: vi.fn(), css: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/settings-api', () => ({ upsertSettings: saves.upsert }))
const language = ref('en')
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ currentLanguage: language, t: (_key: string, fallback: string) => fallback }) }))
const route = reactive({ query: {} as Record<string, string> })
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ getRoutes: () => [
  { path: '/dynamic-page', name: 'DynamicPage', meta: { menuLabel: { en: 'Dynamic page', bg: 'Динамична страница' }, requiresAuth: true } },
  { path: '/user/login', name: 'Login', meta: {} },
  { path: '/users', name: 'Users', meta: { requiresRole: 'admin' } },
] }) }))
vi.mock('@/stores/theme', () => ({ useThemeStore: () => ({ theme: 'light' }) }))
const settings = reactive({
  uiDesign: { components: { card: 'raised', button: 'outline' } },
  activeTheme: null as object | null, isPackagePreview: false,
  headerSettings: { siteName: 'Reference', headerMessage: 'Welcome', logoUrl: '', backgroundColor: '#ffffff', textColor: '#111111' },
  lightStyleSettings: {}, darkStyleSettings: {}, loadSettings: saves.load,
  saveHeaderSettings: saves.header, updateCSSVariables: saves.css,
})
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => settings }))

import Settings from './Settings.vue'
import ApplicationSettingsSection from '@/components/settings/ApplicationSettingsSection.vue'
import HeaderCustomizationSection from '@/components/settings/HeaderCustomizationSection.vue'
import MenuConfigurationSection from '@/components/settings/MenuConfigurationSection.vue'
import LanguageSelector from '@/components/LanguageSelector.vue'
import ThemeSelector from '@/components/ThemeSelector.vue'

const mounted: Array<ReturnType<typeof mount>> = []
const mountView = async () => {
  const wrapper = mount(Settings, { global: { stubs: {
    ThemePackagesSection: { props: ['active'], template: '<div class="package-editor" :data-active="active" />' },
    ThemeCustomizationSection: true, MenuEditor: true, ImageEditorModal: true,
    NetworkConfigurationSection: true, SystemControlSection: true,
    BackupRecoverySection: true, DiagnosticsSection: true,
  } } })
  mounted.push(wrapper)
  await flushPromises()
  return wrapper
}
const selectSection = async (wrapper: ReturnType<typeof mount>, id: string) => {
  await wrapper.get('.settings-mobile-nav select').setValue(id)
  await flushPromises()
}

describe('Settings themed workspace compatibility', () => {
  afterEach(() => { mounted.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks() })
  beforeEach(() => {
    vi.clearAllMocks(); localStorage.clear(); localStorage.setItem('role', 'admin'); localStorage.setItem('authToken', 'test-only')
    route.query = {}; language.value = 'en'; settings.activeTheme = null; settings.isPackagePreview = false
    settings.headerSettings.logoUrl = ''
    http.get.mockImplementation(async (path: string) => {
      if (path === '/language/available') return { data: { languages: ['en', 'bg'] } }
      if (path.startsWith('/settings/language/')) {
        const code = path.endsWith('/bg') ? 'bg' : 'en'
        return { data: { items: [{ key: 'site_name', value: code === 'en' ? 'Reference' : 'Пример', language_code: code }] } }
      }
      if (path === '/menu/read') return { data: { items: [{ id: 3, name: 'Navigation', is_active: true, items: [{ path: '/dynamic-page', label: { en: 'Dynamic page', bg: 'Динамична страница' }, audience: 'authenticated' }] }] } }
      if (path === '/api/admin/session-settings') return { data: { duration_hours: 168, minimum_hours: 1, maximum_hours: 720 } }
      if (path === '/api/admin/ai-settings') return { data: { provider: null, has_groq_key: true, has_openrouter_key: false } }
      return { data: { items: [] } }
    })
    http.put.mockResolvedValue({ data: { duration_hours: 24 } }); http.post.mockResolvedValue({ data: {} })
  })

  it('uses common card/button variants, named navigation and current section without inline styles', async () => {
    const wrapper = await mountView()
    expect(wrapper.attributes('data-card')).toBe('raised')
    expect(wrapper.attributes('data-button')).toBe('outline')
    expect(wrapper.get('.settings-nav').attributes('aria-label')).toBe('Settings')
    expect(wrapper.findAll('.settings-nav-item')).toHaveLength(8)
    expect(wrapper.get('.settings-nav-item.active').attributes('aria-current')).toBe('true')
    expect(wrapper.get('#application-settings .settings-card').classes()).toContain('ui-section')
    expect(wrapper.get('#application-settings h2').text()).toBe('Application Settings')
    expect(wrapper.get('.settings-mobile-nav select').attributes('aria-controls')).toBe('settings-content')
    expect(wrapper.get('.settings-nav').attributes('style')).toBeUndefined()
    expect(wrapper.get('.view-header').attributes('style')).toBeUndefined()
    expect(wrapper.find('.settings-loading').exists()).toBe(false)
  })

  it('keeps unsaved branding when navigating by desktop buttons and mobile selector', async () => {
    const wrapper = await mountView()
    await wrapper.findAll('.settings-nav-item').find(button => button.text() === 'Header Customization')!.trigger('click')
    await wrapper.get('#site-name').setValue('Unsaved identity')
    await selectSection(wrapper, 'menu')
    expect(wrapper.get('#header-settings').isVisible()).toBe(false)
    await selectSection(wrapper, 'header')
    expect(wrapper.get('#site-name').element).toHaveProperty('value', 'Unsaved identity')
    expect(wrapper.get('#settings-content').attributes('aria-label')).toBe('Header Customization')
    expect(saves.upsert).not.toHaveBeenCalled(); expect(http.post).not.toHaveBeenCalled()
  })

  it('keeps localized text drafts separate from shared logo and theme settings', async () => {
    const wrapper = await mountView()
    await selectSection(wrapper, 'header')
    const header = wrapper.findComponent(HeaderCustomizationSection)
    await wrapper.get('#site-name').setValue('English draft')
    await header.findComponent(LanguageSelector).vm.$emit('update:modelValue', 'bg'); await flushPromises()
    expect(wrapper.get('#site-name').element).toHaveProperty('value', 'Пример')
    await wrapper.get('#site-name').setValue('Български текст')
    await selectSection(wrapper, 'theme'); await selectSection(wrapper, 'header')
    await header.findComponent(LanguageSelector).vm.$emit('update:modelValue', 'en'); await flushPromises()
    expect(wrapper.get('#site-name').element).toHaveProperty('value', 'English draft')
    header.vm.$emit('logo-upload', '/uploads/settings/logo.png'); await flushPromises()
    await header.get('form').trigger('submit'); await flushPromises()
    expect(saves.upsert).toHaveBeenCalledWith([expect.objectContaining({ key: 'site_name', value: 'English draft', language_code: 'en' })])
    expect(saves.header).toHaveBeenCalledWith(false)
    expect(settings.headerSettings.logoUrl).toBe('/uploads/settings/logo.png')
    expect(header.find('input[type=color]').exists()).toBe(false)
  })

  it('keeps dynamic route choices and menu save payloads', async () => {
    const wrapper = await mountView(); await selectSection(wrapper, 'menu')
    const menu = wrapper.findComponent(MenuConfigurationSection)
    expect(menu.props('routeOptions')).toContainEqual({ path: '/dynamic-page', label: 'Dynamic page', requiresAuth: true, adminOnly: false })
    expect(menu.props('routeOptions').some((item: { path: string }) => item.path === '/user/login')).toBe(false)
    menu.vm.$emit('save-menu'); await flushPromises()
    expect(http.put).toHaveBeenCalledWith('/menu/update', expect.objectContaining({ id: 3, language: 'en', items: [expect.objectContaining({ audience: 'authenticated' })] }))
  })

  it('preserves non-admin visibility without mounting privileged sections or querying their settings', async () => {
    localStorage.setItem('role', 'user')
    const wrapper = await mountView()
    expect(wrapper.findAll('.settings-nav-item')).toHaveLength(5)
    expect(wrapper.find('#system-settings').exists()).toBe(false)
    expect(wrapper.find('#backup-settings').exists()).toBe(false)
    expect(wrapper.find('#diagnostic-settings').exists()).toBe(false)
    expect(wrapper.find('.package-editor').exists()).toBe(false)
    expect(wrapper.find('#session-duration-hours').exists()).toBe(false)
    expect(http.get).not.toHaveBeenCalledWith('/api/admin/ai-settings')
    expect(http.get).not.toHaveBeenCalledWith('/api/admin/session-settings')
  })

  it('preserves the theme bookmark and active editor signal', async () => {
    route.query = { section: 'theme' }; settings.activeTheme = { theme_extension_version: 2 }
    const wrapper = await mountView()
    expect(wrapper.get('.package-editor').attributes('data-active')).toBe('true')
    expect(wrapper.get('.settings-mobile-nav select').element).toHaveProperty('value', 'theme')
    await selectSection(wrapper, 'header')
    expect(wrapper.get('.package-editor').attributes('data-active')).toBe('false')
    expect(http.post).not.toHaveBeenCalled()
  })

  it('keeps default and session saves unchanged and does not submit blank API keys', async () => {
    const wrapper = await mountView(); const application = wrapper.findComponent(ApplicationSettingsSection)
    application.findComponent(ThemeSelector).vm.$emit('update:modelValue', 'dark'); await flushPromises()
    expect(http.post).toHaveBeenCalledWith('/settings/create', expect.objectContaining({ key: 'default_theme', value: 'dark', language_code: '' }))
    await wrapper.get('#session-duration-hours').setValue(24)
    await application.findAll('button').find(button => button.text() === 'Save session duration')!.trigger('click'); await flushPromises()
    expect(http.put).toHaveBeenCalledWith('/api/admin/session-settings', { duration_hours: 24 })
    await wrapper.get('#ai-provider').setValue('groq')
    await application.findAll('button').find(button => button.text() === 'Save AI settings')!.trigger('click'); await flushPromises()
    expect(http.post).toHaveBeenLastCalledWith('/api/admin/ai-settings', { provider: 'groq' })
    expect(wrapper.get('label[for="groq-api-key"]').text()).toBe('Groq API Key')
  })
})
