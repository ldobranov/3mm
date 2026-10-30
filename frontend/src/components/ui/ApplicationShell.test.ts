import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ApplicationShell from './ApplicationShell.vue'
import { builtinUiDesign } from '@/utils/ui-design'
import { useSettingsStore } from '@/stores/settings'
import { designPreferences } from '@/utils/theme-customization'
import { defaultMenuLayout, type MenuLayout } from '@/utils/menu-layout'

const api = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: { ...api, getCurrentBackendUrl: async () => '' } }))
vi.mock('@/utils/settings-api', () => ({ readSettings: async () => [], upsertSettings: vi.fn() }))
vi.mock('@/utils/language-api', () => ({ readAvailableLanguages: async () => ['en','bg'] }))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  const currentLanguage = ref('en')
  return { useI18n: () => ({ t: (_: string, fallback: string) => fallback, currentLanguage, setLanguage: vi.fn() }) }
})
vi.mock('@/router', () => ({ reloadCompiledUiRoutes: vi.fn() }))

beforeEach(() => {
  localStorage.clear(); setActivePinia(createPinia())
  api.get.mockImplementation(async (path: string) => ({ data: path.startsWith('/menu/read') ? { items: [{ id: 1, is_active: true, items: [
    { path: '/dashboard', label: 'Dashboard', audience: 'authenticated' },
    { path: '/settings', label: 'Settings', audience: 'admin' },
    { path: '/public', label: 'Public resource', audience: 'public' },
    { path: '/dynamic', label: 'Registered module route', audience: 'authenticated' },
  ] }] } : [{ kind: 'navigation', metadata: { path: '/dynamic', label: 'Registered module route' } }] }))
})
afterEach(() => { vi.clearAllMocks(); document.documentElement.style.cssText = '' })
async function shell(role: string, mode: 'application' | 'public' | 'auth' | 'kiosk' | 'display' = 'application') {
  if (role) { localStorage.setItem('authToken', 'fixture-token'); localStorage.setItem('role', role) }
  const page = { render: () => h('p', 'Page') }
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: page }, { path: '/dashboard', component: page, meta: { requiresAuth: true } },
    { path: '/settings', component: page, meta: { requiresAuth: true, requiresRole: 'admin' } },
    { path: '/public', component: page }, { path: '/dynamic', component: page, meta: { requiresAuth: true } },
    { path: '/settings/ui-preview', name: 'UiPreview', component: page },
    { path: '/user/login', component: page }, { path: '/user/register', component: page },
  ] })
  await router.push('/dashboard'); await router.isReady()
  const wrapper = mount(ApplicationShell, { props: { design: builtinUiDesign(), mode }, global: { plugins: [router] }, slots: { default: '<p>Page content</p>' } })
  await flushPromises()
  return wrapper
}
describe('shell uses the existing dynamic navigation and action boundary', () => {
  const placedMenus = [
    { id: 1, name: 'Main', is_active: true, items: [{ path: '/dashboard', label: 'Dashboard', audience: 'authenticated' }] },
    { id: 2, name: 'Administration', is_active: false, items: [
      { path: '/settings', label: 'Settings', audience: 'admin' }, { path: '/retired', label: 'Retired page' },
    ] },
    { id: 3, name: 'Information', is_active: false, items: [{ path: '/public', label: 'Public resource', audience: 'public' }] },
  ]
  const place = (layout: MenuLayout) => {
    const settings = useSettingsStore()
    settings.themePreferences = { ...designPreferences(settings.baseUiDesign, settings.headerSettings), menu_layout: layout }
  }
  it.each(['admin', 'registered', ''])('filters every placed menu for %s and keeps footer after the main content', async role => {
    api.get.mockResolvedValue({ data: { items: placedMenus } })
    const wrapper = await shell(role)
    place({ ...defaultMenuLayout(), placements: [
      { menu_id: 1, location: 'sidebar' }, { menu_id: 2, location: 'header' }, { menu_id: 3, location: 'footer' },
    ] }); await flushPromises()
    expect(wrapper.find('aside [data-menu-id="1"]').exists()).toBe(Boolean(role))
    expect(wrapper.find('header [data-menu-id="2"]').exists()).toBe(role === 'admin')
    expect(wrapper.find('footer [data-menu-id="3"]').text()).toBe('Public resource')
    expect(wrapper.text()).not.toContain('Retired page')
    const main = wrapper.get('main').element, footer = wrapper.get('footer').element
    expect(main.compareDocumentPosition(footer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    wrapper.unmount()
  })
  it('supports sidebar and header together, sticky zones and an explicit empty selection without remounting content', async () => {
    api.get.mockResolvedValue({ data: { items: placedMenus } })
    const wrapper = await shell('admin'), main = wrapper.get('main').element
    const design = builtinUiDesign(); design.layout.navigation = 'top'
    await wrapper.setProps({ design })
    place({ placements: [
      { menu_id: 1, location: 'sidebar' }, { menu_id: 2, location: 'header' }, { menu_id: 3, location: 'footer' },
    ], sticky: { header: true, sidebar: true, footer: true } }); await flushPromises()
    expect(wrapper.find('.ui-sidebar-content--sticky').exists()).toBe(true)
    expect(wrapper.find('.ui-toolbar--sticky').exists()).toBe(true)
    expect(wrapper.find('.ui-footer--sticky').exists()).toBe(true)
    expect(wrapper.find('header [data-menu-id="2"]').exists()).toBe(true)
    expect(wrapper.find('aside [data-menu-id="1"]').exists()).toBe(true)
    const drawer = wrapper.get('#ui-mobile-navigation')
    expect(drawer.findAll('nav').map(nav => nav.attributes('data-menu-id'))).toEqual(['2', '1'])
    place({ ...defaultMenuLayout(), placements: [] }); await flushPromises()
    expect(wrapper.findAll('.ui-nav-item')).toHaveLength(0)
    expect(wrapper.find('footer').exists()).toBe(false)
    expect(wrapper.get('main').element).toBe(main)
    wrapper.unmount()
  })
  it.each(['kiosk', 'display'] as const)('does not leak placed menus into %s pages', async mode => {
    api.get.mockResolvedValue({ data: { items: placedMenus } })
    const wrapper = await shell('admin', mode)
    place({ placements: [{ menu_id: 2, location: 'header' }, { menu_id: 3, location: 'footer' }],
      sticky: { header: true, sidebar: true, footer: true } }); await flushPromises()
    expect(wrapper.findAll('[data-menu-id]')).toHaveLength(0)
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.find('footer').exists()).toBe(false)
    wrapper.unmount()
  })
  it.each(['admin','registered',''])('retains audience/route filtering for %s', async role => {
    const wrapper = await shell(role)
    const links = wrapper.findAll('aside a').map(link => link.text())
    expect(links.includes('Settings')).toBe(role === 'admin')
    expect(links.includes('Dashboard')).toBe(Boolean(role))
    expect(links).toContain('Public resource')
    expect(links.includes('Registered module route')).toBe(Boolean(role))
    expect(wrapper.find('.ui-recovery-link').exists()).toBe(false)
    wrapper.unmount()
  })
  it.each(['sidebar', 'top'] as const)('leaves %s navigation empty without adding compulsory recovery links', async layout => {
    api.get.mockResolvedValue({ data: { items: [] } })
    const wrapper = await shell('admin')
    const design = builtinUiDesign(); design.layout.navigation = layout
    await wrapper.setProps({ design })
    expect(wrapper.findAll('.ui-nav-item')).toHaveLength(0)
    expect(wrapper.findAll('a[href*="ui-preview"]')).toHaveLength(0)
    wrapper.unmount()
  })
  it.each(['auth','public','kiosk','display'] as const)('does not impose a sidebar on %s', async mode => {
    const wrapper = await shell('', mode)
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.find('.ui-toolbar').exists()).toBe(mode !== 'display')
    wrapper.unmount()
  })
  it('keeps page state mounted when switching legacy/preview and navigation layouts', async () => {
    const mounted = vi.fn(), unmounted = vi.fn()
    const child = defineComponent({ mounted, unmounted, render: () => h('input', { value: 'Preserved' }) })
    const wrapper = await shell('admin')
    // Stable main exists in either shell, and the layout switch preserves it.
    const main = wrapper.find('main').element
    await wrapper.setProps({ active: false })
    expect(wrapper.find('main').element).toBe(main)
    expect(wrapper.find('.navbar').exists()).toBe(true)
    const design = builtinUiDesign(); design.layout.navigation = 'top'
    await wrapper.setProps({ active: true, design })
    expect(wrapper.find('main').element).toBe(main)
    expect(wrapper.find('.ui-top-navigation').exists()).toBe(true)
    expect(wrapper.find('.ui-sidebar').exists()).toBe(false)
    wrapper.unmount()
    // Actual slot lifecycle proof, independent of the navigation fixture.
    const settings = useSettingsStore()
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: child }, { path: '/settings/ui-preview', name: 'UiPreview', component: child }] })
    await router.push('/')
    const stable = mount(ApplicationShell, { props: { active: false, design: settings.uiDesign, mode: 'application' }, global: { plugins: [router] }, slots: { default: () => h(child) } })
    await flushPromises()
    await stable.setProps({ active: true }); await nextTick()
    expect(mounted).toHaveBeenCalledTimes(1); expect(unmounted).not.toHaveBeenCalled()
    stable.unmount()
  })
})
