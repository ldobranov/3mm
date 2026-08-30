import { describe, expect, it } from 'vitest'
import {
  isMenuRouteEligible,
  isNavigationItemVisible,
  mergeNavigationItems,
  normalizeAvailableLanguages,
} from './menu-navigation'

describe('menu navigation', () => {
  it('keeps custom entries and appends dynamic entries without duplicate paths', () => {
    expect(mergeNavigationItems(
      [{ path: '/settings', label: 'Settings' }, { path: '/main-server', label: 'My devices' }],
      [{ path: '/main-server', label: 'Devices' }, { path: '/automations/proposals', label: 'Automations' }],
    )).toEqual([
      { path: '/settings', label: 'Settings' },
      { path: '/main-server', label: 'My devices' },
      { path: '/automations/proposals', label: 'Automations' },
    ])
  })

  it('does not invent languages that are not installed', () => {
    expect(normalizeAvailableLanguages(['en'])).toEqual(['en'])
    expect(normalizeAvailableLanguages(['bg', 'en', 'bg'])).toEqual(['en', 'bg'])
  })

  it('offers only concrete routes allowed for the current role', () => {
    expect(isMenuRouteEligible('/settings', undefined, 'user')).toBe(true)
    expect(isMenuRouteEligible('/automations/proposals', 'admin', 'user')).toBe(false)
    expect(isMenuRouteEligible('/automations/proposals', 'admin', 'admin')).toBe(true)
    expect(isMenuRouteEligible('/dashboard/:id/edit', undefined, 'admin')).toBe(false)
    expect(isMenuRouteEligible('/user/logout', undefined, 'admin')).toBe(false)
  })

  it('supports explicit public, signed-in and admin menu audiences', () => {
    expect(isNavigationItemVisible(
      { path: '/@demo/status', label: 'Status', audience: 'public' },
      { isLoggedIn: false, currentRole: '' },
    )).toBe(true)
    expect(isNavigationItemVisible(
      { path: '/dashboard', label: 'Dashboards', audience: 'authenticated' },
      { isLoggedIn: false, currentRole: '', routeRequiresAuth: true },
    )).toBe(false)
    expect(isNavigationItemVisible(
      { path: '/system/updates', label: 'Updates', audience: 'admin' },
      { isLoggedIn: true, currentRole: 'user', routeRequiresAuth: true, routeRequiredRole: 'admin' },
    )).toBe(false)
  })

  it('never lets a public menu flag bypass a protected route', () => {
    expect(isNavigationItemVisible(
      { path: '/settings', label: 'Settings', audience: 'public' },
      { isLoggedIn: false, currentRole: '', routeRequiresAuth: true },
    )).toBe(false)
  })

  it('shows kiosk navigation only while a kiosk identity is active', () => {
    const item = { path: '/application/check-in', label: 'Check in', audience: 'kiosk' as const }
    expect(isNavigationItemVisible(item, {
      isLoggedIn: false,
      isKiosk: false,
      currentRole: '',
    })).toBe(false)
    expect(isNavigationItemVisible(item, {
      isLoggedIn: false,
      isKiosk: true,
      currentRole: '',
    })).toBe(true)
  })
})
