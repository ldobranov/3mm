import { describe, expect, it } from 'vitest'
import {
  isMenuRouteEligible,
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
})
