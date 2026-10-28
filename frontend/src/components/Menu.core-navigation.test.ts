import { h, ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Menu from './Menu.vue'
import { createRouterWithDynamicRoutes } from '@/router'
import http from '@/utils/dynamic-http'

const ui = vi.hoisted(() => ({ language: 'en', menus: [] as any[], menuFailure: false }))
vi.mock('@/utils/dynamic-http', () => ({ default: { get: vi.fn(async (url: string) => {
  if (url.startsWith('/menu/read')) {
    if (ui.menuFailure) throw new Error('Menu unavailable')
    return { data: { items: ui.menus } }
  }
  return { data: [{ kind: 'navigation', metadata: { path: '/installed-app', label: 'Installed app' } }] }
}) } }))
vi.mock('@/utils/compiled-ui', () => ({ getCompiledUiCatalog: vi.fn(async () => []), loadCompiledComponent: vi.fn() }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({
  currentLanguage: ref(ui.language),
  t: (_key: string, fallback: string) => fallback,
  setLanguage: vi.fn(), setPreviewLanguage: vi.fn(),
}) }))
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => ({ headerSettings: {}, loadSettings: vi.fn(async () => {}) }) }))
vi.mock('@/utils/language-api', () => ({ readAvailableLanguages: vi.fn(async () => ['en', 'bg']) }))

const mounted: ReturnType<typeof mount>[] = []
beforeEach(() => { ui.language = 'en'; ui.menus = []; ui.menuFailure = false; vi.clearAllMocks() })
afterEach(() => {
  mounted.splice(0).forEach(wrapper => wrapper.unmount())
  localStorage.clear(); window.history.replaceState({}, '', '/')
  vi.restoreAllMocks()
})

async function mountHeader(role = 'admin') {
  if (role) { localStorage.setItem('authToken', 'fixture'); localStorage.setItem('role', role) }
  const router = await createRouterWithDynamicRoutes()
  router.addRoute({ path: '/installed-app', name: 'InstalledApp', component: { render: () => null },
    meta: { menuLabel: { en: 'Installed app' }, requiresAuth: true } })
  await router.push('/user/login')
  const wrapper = mount(Menu, { global: { plugins: [router] }, slots: {
    default: ({ navigation }: any) => h('div', { class: 'saved-links' }, navigation.items.map((item: any) =>
      h('a', { href: item.path }, navigation.label(item)))),
  } })
  mounted.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}

describe('administrator-controlled header navigation', () => {
  it.each(['en', 'bg'].flatMap(language => ['admin', 'registered', ''].map(role => [language, role])))
  ('starts empty for %s/%s while Core and installed routes remain registered', async (language, role) => {
    ui.language = language
    const { wrapper, router } = await mountHeader(role)
    expect(wrapper.findAll('.saved-links a')).toHaveLength(0)
    expect(router.resolve('/settings').meta.requiresRole).toBe('admin')
    expect(router.resolve('/extensions').meta.requiresRole).toBe('admin')
    expect(router.resolve('/installed-app').name).toBe('InstalledApp')
    expect(vi.mocked(http.get).mock.calls.some(([url]) => url === '/api/v1/modules/registrations')).toBe(false)
  })

  it.each(['empty', 'inactive'])('respects an %s menu instead of generating links', async mode => {
    ui.menus = [{ id: 1, is_active: mode === 'empty', items: mode === 'empty' ? [] : [
      { path: '/settings', label: 'Settings' },
    ] }]
    const { wrapper } = await mountHeader()
    expect(wrapper.findAll('.saved-links a')).toHaveLength(0)
  })

  it('shows only saved localized links and keeps them removed after menu refresh', async () => {
    ui.language = 'bg'
    ui.menus = [{ id: 4, is_active: true, items: [
      { path: '/settings', label: { en: 'Settings', bg: 'Настройки' } },
      { path: '/installed-app', label: { en: 'My application', bg: 'Моето приложение' } },
    ] }]
    const { wrapper } = await mountHeader()
    expect(wrapper.findAll('.saved-links a').map(link => link.text())).toEqual(['Настройки', 'Моето приложение'])
    expect(wrapper.findAll('.saved-links a').map(link => link.attributes('href'))).toEqual(['/settings', '/installed-app'])
    ui.menus[0].items = []
    window.dispatchEvent(new Event('menu-refresh'))
    await flushPromises()
    expect(wrapper.findAll('.saved-links a')).toHaveLength(0)
  })

  it('clears links on read failure without adding generated fallback navigation', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    ui.menus = [{ id: 1, is_active: true, items: [{ path: '/settings', label: 'Settings' }] }]
    const { wrapper } = await mountHeader()
    expect(wrapper.findAll('.saved-links a')).toHaveLength(1)
    ui.menuFailure = true
    window.dispatchEvent(new Event('menu-refresh'))
    await flushPromises()
    expect(wrapper.findAll('.saved-links a')).toHaveLength(0)
  })
})
