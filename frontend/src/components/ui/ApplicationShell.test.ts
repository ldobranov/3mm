import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ApplicationShell from './ApplicationShell.vue'
import { builtinUiDesign } from '@/utils/ui-design'
import { useSettingsStore } from '@/stores/settings'

const api = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: { ...api, getCurrentBackendUrl: async () => '' } }))
vi.mock('@/utils/settings-api', () => ({ readSettings: async () => [], upsertSettings: vi.fn() }))
vi.mock('@/utils/language-api', () => ({ readAvailableLanguages: async () => ['en','bg'] }))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  const currentLanguage = ref('en')
  return { useI18n: () => ({ t: (_: string, fallback: string) => fallback, currentLanguage, setLanguage: vi.fn() }) }
})
vi.mock('@/utils/runtime-extensions', () => ({ reloadRuntimeExtensionRoutes: vi.fn() }))
vi.mock('@/router', () => ({ reloadCompiledUiRoutes: vi.fn() }))

beforeEach(() => {
  localStorage.clear(); setActivePinia(createPinia())
  api.get.mockImplementation(async (path: string) => ({ data: path.startsWith('/menu/read') ? { items: [{ id: 1, is_active: true, items: [
    { path: '/dashboard', label: 'Dashboard', audience: 'authenticated' },
    { path: '/settings', label: 'Settings', audience: 'admin' },
    { path: '/public', label: 'Public resource', audience: 'public' },
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
  it.each(['admin','registered',''])('retains audience/route filtering for %s', async role => {
    const wrapper = await shell(role)
    const links = wrapper.findAll('aside a').map(link => link.text())
    expect(links.includes('Settings')).toBe(role === 'admin')
    expect(links.includes('Dashboard')).toBe(Boolean(role))
    expect(links).toContain('Public resource')
    expect(links.includes('Registered module route')).toBe(Boolean(role))
    expect(wrapper.find('.ui-recovery-link').exists()).toBe(role === 'admin')
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
