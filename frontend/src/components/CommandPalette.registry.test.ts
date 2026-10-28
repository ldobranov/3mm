import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CommandPalette from './CommandPalette.vue'

const toggles = vi.hoisted(() => ({ theme: vi.fn(), kiosk: vi.fn() }))
vi.mock('@/utils/kiosk-session',()=>({kioskRouteAvailable:toggles.kiosk}))
vi.mock('@/stores/theme', () => ({ useThemeStore: () => ({ toggleTheme: toggles.theme }) }))
vi.mock('@/utils/i18n', async () => {
  const { ref } = await import('vue')
  return { useI18n: () => ({ currentLanguage: ref('bg'), t: (_key: string, fallback: string) => fallback }) }
})
const mounted: ReturnType<typeof mount>[] = []
afterEach(() => { mounted.splice(0).forEach(item => item.unmount()); localStorage.clear(); vi.clearAllMocks() })

async function palette(role: string, kiosk = false) {
  if (role) { localStorage.setItem('authToken', 'test-token'); localStorage.setItem('role', role) }
  toggles.kiosk.mockImplementation(module=>kiosk&&module==='org.example.kiosk')
  const page = { render: () => null }
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', name: 'Home', component: page },
    { path: '/settings', name: 'Settings', component: page, meta: { requiresAuth: true, requiresRole: 'admin' } },
    { path: '/user/profile', name: 'Profile', component: page, meta: { requiresAuth: true } },
    { path: '/user/logout', name: 'Logout', component: page },
    { path: '/app/reports', name: 'reports', component: page, meta: { requiresAuth: true,
      applicationAudience: 'operator', menuLabel: { en: 'Reports', translations: { bg: 'Отчети' } } } },
    { path: '/app/public', name: 'public', component: page, meta: { applicationAudience: 'public', menuLabel: { en: 'Public app' } } },
    { path: '/app/kiosk', name: 'kiosk', component: page, meta: { applicationAudience: 'kiosk', compiledModuleId:'org.example.kiosk', menuLabel: { en: 'Kiosk app' } } },
    { path: '/app/foreign-kiosk', name: 'foreign-kiosk', component: page, meta: { applicationAudience:'kiosk',compiledModuleId:'org.example.foreign',menuLabel:{en:'Foreign kiosk'} } },
    { path: '/:pathMatch(.*)*', name: 'NotFound', component: page },
  ] })
  await router.push('/')
  const wrapper = mount(CommandPalette, { global: { plugins: [router] } }); mounted.push(wrapper)
  await (window as any).openCommandPalette(); await flushPromises()
  return { router, wrapper }
}

describe('command palette after product extraction', () => {
  it.each(['admin', 'registered', ''])('uses current routes, audience and localized labels for %s', async (role) => {
    await palette(role)
    const text = document.body.textContent || ''
    expect(text).toContain('Public app')
    expect(text.includes('Отчети')).toBe(Boolean(role))
    expect(text.includes('Go to Settings')).toBe(role === 'admin')
    expect(text).not.toContain('Dashboard')
    expect(text).not.toContain('Recent Pages')
    expect(text).not.toContain('Kiosk app')
  })

  it('refreshes installed routes on open and keeps kiosk audience separate', async () => {
    const { router, wrapper } = await palette('', true)
    expect(document.body.textContent).toContain('Kiosk app')
    expect(document.body.textContent).not.toContain('Foreign kiosk')
    router.addRoute({ path: '/new-app', name: 'new-app', component: { render: () => null },
      meta: { applicationAudience: 'public', menuLabel: { en: 'Newly installed' } } })
    await (window as any).openCommandPalette(); await flushPromises()
    expect(document.body.textContent).toContain('Newly installed')
    router.removeRoute('new-app')
    await (window as any).openCommandPalette(); await flushPromises()
    expect(document.body.textContent).not.toContain('Newly installed')
    wrapper.unmount(); expect((window as any).openCommandPalette).toBeUndefined()
  })

  it('preserves keyboard navigation and theme actions without retired shortcuts', async () => {
    const { router } = await palette('admin')
    const toggle = Array.from(document.querySelectorAll('.command-item')).find(item => item.textContent?.includes('Toggle Dark Mode'))!
    toggle.dispatchEvent(new MouseEvent('click', { bubbles: true })); await flushPromises()
    expect(toggles.theme).toHaveBeenCalledOnce()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 's', altKey: true, cancelable: true })); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/settings')
    const oldShortcut = new KeyboardEvent('keydown', { key: 'n', ctrlKey: true, cancelable: true })
    document.dispatchEvent(oldShortcut); expect(oldShortcut.defaultPrevented).toBe(false)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, cancelable: true })); await flushPromises()
    expect(document.querySelector('.command-palette')).not.toBeNull()
  })
})
