import { flushPromises, mount } from '@vue/test-utils'
import { reactive, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
const saves = vi.hoisted(() => ({ upsert: vi.fn(), read: vi.fn(), header: vi.fn(), load: vi.fn(), css: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/settings-api', () => ({ upsertSettings: saves.upsert, readSettings: saves.read }))
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
  loadSettings: saves.load,
  saveHeaderSettings: saves.header, updateCSSVariables: saves.css,
})
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => settings }))

import Settings from './Settings.vue'
import ApplicationSettingsSection from '@/components/settings/ApplicationSettingsSection.vue'
import HeaderCustomizationSection from '@/components/settings/HeaderCustomizationSection.vue'
import MenuConfigurationSection from '@/components/settings/MenuConfigurationSection.vue'
import ThemeSelector from '@/components/ThemeSelector.vue'

const mounted: Array<ReturnType<typeof mount>> = []
let savedLogo = ''
let savedTexts: Record<string, Record<string, string>>
const mountView = async () => {
  const wrapper = mount(Settings, { global: { stubs: {
    ThemePackagesSection: { props: ['active'], template: '<div class="package-editor" :data-active="active" />' },
    MenuEditor: true, ImageEditorModal: true,
    UiDialog: { props: ['open'], template: '<div v-if="open" role="dialog"><slot /><slot name="actions" /></div>' },
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
    savedLogo = ''; savedTexts = { en: { site_name: 'Reference' }, bg: { site_name: 'Пример' } }
    saves.read.mockImplementation(async () => [{ key: 'logo_url', value: savedLogo, language_code: null }])
    saves.upsert.mockImplementation(async (values: { key: string; value: string; language_code: string | null }[]) => {
      for (const item of values) {
        if (item.key === 'logo_url') savedLogo = item.value
        else if (item.language_code) (savedTexts[item.language_code] ??= {})[item.key] = item.value
      }
    })
    http.get.mockImplementation(async (path: string) => {
      if (path === '/language/available') return { data: { languages: ['en', 'bg'] } }
      if (path.startsWith('/settings/language/')) {
        const code = path.endsWith('/bg') ? 'bg' : 'en'
        return { data: { items: Object.entries(savedTexts[code]!).map(([key, value]) => ({ key, value, language_code: code })) } }
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
    await header.get('#header-language').setValue('bg'); await flushPromises()
    expect(wrapper.get('#site-name').element).toHaveProperty('value', 'Пример')
    await wrapper.get('#site-name').setValue('Български текст')
    await selectSection(wrapper, 'theme'); await selectSection(wrapper, 'header')
    await header.get('#header-language').setValue('en'); await flushPromises()
    expect(wrapper.get('#site-name').element).toHaveProperty('value', 'English draft')
    header.vm.$emit('logo-upload', '/uploads/settings/logo.png'); await flushPromises()
    expect(settings.headerSettings.logoUrl).toBe('')
    await header.get('form').trigger('submit'); await flushPromises()
    expect(saves.upsert).toHaveBeenCalledWith([
      expect.objectContaining({ key: 'site_name', value: 'English draft', language_code: 'en' }),
      expect.objectContaining({ key: 'header_message', language_code: 'en' }),
      expect.objectContaining({ key: 'logo_url', value: '/uploads/settings/logo.png', language_code: null }),
    ])
    expect(saves.header).not.toHaveBeenCalled()
    expect(header.props('state')).toBe('idle')
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

  it('deletes the last active menu and leaves an empty header configuration', async () => {
    const wrapper = await mountView(); await selectSection(wrapper, 'menu')
    http.delete.mockResolvedValue({ data: { deleted: true, menu_id: 3 } })
    const previousGet = http.get.getMockImplementation()!
    http.get.mockImplementation(async (path: string) => path === '/menu/read'
      ? { data: { items: [] } } : previousGet(path))
    await wrapper.get('.menu-delete').trigger('click'); await flushPromises()
    expect(http.delete).not.toHaveBeenCalled()
    await wrapper.get('[role="dialog"] form').trigger('submit'); await flushPromises()
    expect(http.delete).toHaveBeenCalledWith('/menu/3')
    expect(wrapper.find('.menu-delete').exists()).toBe(false)
    expect(wrapper.get('.menu-empty-state').text()).toContain('The header has no navigation links.')
    expect(wrapper.findComponent(MenuConfigurationSection).props('currentMenuItems')).toEqual([])
  })

  it('keeps logo edits in the draft and discards them without writing settings', async () => {
    const wrapper = await mountView(); await selectSection(wrapper, 'header')
    const header = wrapper.findComponent(HeaderCustomizationSection)
    header.vm.$emit('logo-upload', '/uploads/settings/new.png'); await flushPromises()
    expect(header.props('headerSettings').logoUrl).toBe('/uploads/settings/new.png')
    expect(settings.headerSettings.logoUrl).toBe('')
    header.vm.$emit('discard'); await flushPromises()
    expect(header.props('headerSettings').logoUrl).toBe('')
    expect(saves.upsert).not.toHaveBeenCalled()
  })

  it('locks an uncertain header save and preserves the draft if the saved-value read fails', async () => {
    const wrapper = await mountView(); await selectSection(wrapper, 'header')
    const header = wrapper.findComponent(HeaderCustomizationSection)
    saves.upsert.mockRejectedValueOnce(new Error('lost reply'))
    await wrapper.get('#site-name').setValue('Keep this draft')
    await header.get('form').trigger('submit'); await flushPromises()
    expect(header.props('state')).toBe('unconfirmed')
    header.vm.$emit('save-header-settings'); await flushPromises()
    expect(saves.upsert).toHaveBeenCalledTimes(1)
    saves.read.mockRejectedValueOnce(new Error('offline'))
    header.vm.$emit('reload'); await flushPromises()
    expect(wrapper.get('#site-name').element).toHaveProperty('value', 'Keep this draft')
    expect(header.props('state')).toBe('unconfirmed')
    header.vm.$emit('reload'); await flushPromises()
    expect(header.props('state')).toBe('idle')
    expect(wrapper.get('#site-name').element).toHaveProperty('value', 'Reference')
    expect(saves.upsert).toHaveBeenCalledTimes(1)
  })

  it('does not call an old saved snapshot confirmation of a changed header', async () => {
    const wrapper = await mountView(); await selectSection(wrapper, 'header')
    const header = wrapper.findComponent(HeaderCustomizationSection)
    saves.upsert.mockResolvedValueOnce(undefined) // Acknowledged, but read still has the old values.
    await wrapper.get('#site-name').setValue('Unconfirmed new value')
    await header.get('form').trigger('submit'); await flushPromises()
    expect(header.props('state')).toBe('unconfirmed')
    expect(wrapper.get('#site-name').element).toHaveProperty('value', 'Unconfirmed new value')
    expect(wrapper.text()).not.toContain('Header settings saved.')
  })

  it('keeps separate menu drafts and locks mutations after a lost save reply', async () => {
    const wrapper = await mountView(); await selectSection(wrapper, 'menu')
    const menu = wrapper.findComponent(MenuConfigurationSection)
    const original = http.get.getMockImplementation()!
    http.get.mockImplementation(async (path: string) => path === '/menu/read' ? { data: { items: [
      { id: 3, name: 'Navigation', is_active: true, items: [{ path: '/dynamic-page', label: { en: 'Saved' }, audience: 'authenticated' }] },
      { id: 4, name: 'Other', is_active: false, items: [] },
    ] } } : original(path))
    menu.vm.$emit('reload'); await flushPromises()
    const draft = [{ path: '/dynamic-page', label: { en: 'Draft' }, audience: 'authenticated' }]
    menu.vm.$emit('update:currentMenuItems', draft); await flushPromises()
    menu.vm.$emit('update:activeMenuId', 4); await flushPromises()
    expect(menu.props('currentMenuItems')).toEqual([])
    menu.vm.$emit('update:activeMenuId', 3); await flushPromises()
    expect(menu.props('currentMenuItems')).toEqual(draft)
    vi.spyOn(console, 'error').mockImplementation(() => {})
    http.put.mockRejectedValueOnce(new Error('lost reply'))
    menu.vm.$emit('save-menu'); await flushPromises()
    expect(menu.props('state')).toBe('unconfirmed')
    menu.vm.$emit('save-menu'); menu.vm.$emit('create-menu', 'Do not replay'); await flushPromises()
    expect(http.put).toHaveBeenCalledTimes(1); expect(http.post).not.toHaveBeenCalled()
    menu.vm.$emit('reload'); await flushPromises()
    expect(menu.props('state')).toBe('idle')
    expect(menu.props('currentMenuItems')[0].label).toEqual({ en: 'Saved' })
    expect(http.put).toHaveBeenCalledTimes(1)
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

  it('keeps default and session saves after removing the product provider editor', async () => {
    const wrapper = await mountView(); const application = wrapper.findComponent(ApplicationSettingsSection)
    application.findComponent(ThemeSelector).vm.$emit('update:modelValue', 'dark'); await flushPromises()
    expect(http.post).toHaveBeenCalledWith('/settings/create', expect.objectContaining({ key: 'default_theme', value: 'dark', language_code: '' }))
    await wrapper.get('#session-duration-hours').setValue(24)
    await application.findAll('button').find(button => button.text() === 'Save session duration')!.trigger('click'); await flushPromises()
    expect(http.put).toHaveBeenCalledWith('/api/admin/session-settings', { duration_hours: 24 })
    expect(wrapper.find('#ai-provider').exists()).toBe(false)
    expect(wrapper.find('label[for="groq-api-key"]').exists()).toBe(false)
    expect(http.get).not.toHaveBeenCalledWith('/api/admin/ai-settings')
  })
})
