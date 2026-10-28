import { h, ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Menu from './Menu.vue'

vi.mock('@/utils/dynamic-http', () => ({ default: { get: vi.fn(async (url: string) => ({ data:
  url.startsWith('/menu/read') ? { items: [{ id: 1, is_active: true, items: [
    { path: '/removed-product', label: 'Retired page' },
    { path: '/settings', label: 'Settings', audience: 'admin' },
    { path: '/@owner/status', label: 'Status', audience: 'public' },
    { path: '/application/example', label: 'Installed app', audience: 'authenticated' },
  ] }] } : [] })) } }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ currentLanguage: ref('en'), t: (_key: string, fallback: string) => fallback,
  setLanguage: vi.fn(), setPreviewLanguage: vi.fn() }) }))
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => ({ headerSettings: {}, loadSettings: vi.fn(async () => {}) }) }))
vi.mock('@/utils/language-api', () => ({ readAvailableLanguages: vi.fn(async () => ['en']) }))
vi.mock('@/router', () => ({ reloadCompiledUiRoutes: vi.fn(async () => {}) }))

afterEach(() => localStorage.clear())
describe('navigation follows the current route registry', () => {
  it.each(['admin', 'registered', 'guest'])('filters retired routes and keeps audiences for %s', async (role) => {
    if (role !== 'guest') { localStorage.setItem('authToken', 'test'); localStorage.setItem('role', role) }
    const page = { render: () => null }
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/settings', component: page, meta: { requiresAuth: true, requiresRole: 'admin' } },
      { path: '/@:username/:slug', component: page },
      { path: '/application/example', component: page, meta: { requiresAuth: true } },
      { path: '/:pathMatch(.*)*', name: 'NotFound', component: page },
    ] })
    const wrapper = mount(Menu, { global: { plugins: [router] }, slots: {
      default: ({ navigation }: any) => h('div', navigation.items.map((item: any) =>
        h('a', { href: item.path }, navigation.label(item)))),
    } })
    await flushPromises()
    const paths = wrapper.findAll('a').map(item => item.attributes('href'))
    expect(paths).not.toContain('/removed-product')
    expect(paths).toContain('/@owner/status')
    expect(paths.includes('/settings')).toBe(role === 'admin')
    expect(paths.includes('/application/example')).toBe(role !== 'guest')
    wrapper.unmount()
  })
})
