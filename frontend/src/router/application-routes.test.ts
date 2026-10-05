import { describe, expect, it, vi } from 'vitest'

import { compiledRouteRecords, createRouterWithDynamicRoutes } from './index'
import http from '@/utils/dynamic-http'
import * as compiledUi from '@/utils/compiled-ui'
import { mergeNavigationItems } from '@/utils/menu-navigation'
import type { CompiledUiPackage } from '@/utils/compiled-ui'


function applicationPackage(audience: 'public' | 'kiosk' | 'operator' | 'administrator'): CompiledUiPackage {
  return {
    module_id: `org.3mm.${audience}`,
    name: audience,
    version: '1.0.0',
    source_sha256: 'a'.repeat(64),
    styles: [],
    entrypoints: [{
      entrypoint_id: audience,
      kind: 'route',
      source: `source/frontend/${audience}.vue`,
      label: { en: audience },
      route: `/application/${audience}`,
      application_audience: audience,
      required_permissions: audience === 'operator' ? ['records_manage'] : [],
      navigation: true,
      menu_order: 20,
      asset_url: `/assets/${audience}.mjs`,
    }],
  }
}


describe('application compiled routes', () => {
  it('guards appearance preview and recovery with the existing admin boundary', async () => {
    const api = vi.spyOn(http, 'get').mockResolvedValue({ data: { items: [] } })
    const catalog = vi.spyOn(compiledUi, 'getCompiledUiCatalog').mockResolvedValue([])
    try {
      for (const [role, expected] of [['admin', '/settings/ui-preview'], ['registered', '/user/profile'], ['', '/user/login']]) {
        localStorage.clear()
        if (role) { localStorage.setItem('authToken', 'fixture-token'); localStorage.setItem('role', role) }
        const router = await createRouterWithDynamicRoutes()
        await router.push('/settings/ui-preview?recovery=1')
        expect(router.currentRoute.value.path).toBe(expected)
      }
    } finally { localStorage.clear(); api.mockRestore(); catalog.mockRestore() }
  })
  it('keeps optional Core pages protected without forcing them into the header', async () => {
    const api = vi.spyOn(http, 'get').mockResolvedValue({ data: { items: [] } })
    const catalog = vi.spyOn(compiledUi, 'getCompiledUiCatalog').mockResolvedValue([])
    try {
      const router = await createRouterWithDynamicRoutes()
      const automatic = router.getRoutes()
        .filter(route => route.meta.menuLabel)
        .map(route => ({ path: route.path, label: String(route.meta.menuLabel) }))
      for (const path of ['/automations/proposals', '/system/updates', '/settings/ui-preview']) {
        const route = router.resolve(path)
        expect(route.meta.requiresAuth).toBe(true)
        expect(route.meta.requiresRole).toBe('admin')
        expect(mergeNavigationItems([], automatic).some(item => item.path === path)).toBe(false)
        expect(mergeNavigationItems([{ path, label: 'Custom label' }], automatic))
          .toContainEqual({ path, label: 'Custom label' })
      }
    } finally {
      api.mockRestore()
      catalog.mockRestore()
    }
  })

  it('derives route guards and navigation only from server catalog metadata', () => {
    const routes = compiledRouteRecords([
      applicationPackage('public'),
      applicationPackage('kiosk'),
      applicationPackage('operator'),
      applicationPackage('administrator'),
    ])
    expect(routes.map(route => ({
      path: route.path,
      requiresAuth: route.meta?.requiresAuth,
      requiresKiosk: route.meta?.requiresKiosk,
      requiresRole: route.meta?.requiresRole,
    }))).toEqual([
      { path: '/application/public', requiresAuth: false, requiresKiosk: false, requiresRole: undefined },
      { path: '/application/kiosk', requiresAuth: false, requiresKiosk: true, requiresRole: undefined },
      { path: '/application/operator', requiresAuth: true, requiresKiosk: false, requiresRole: undefined },
      { path: '/application/administrator', requiresAuth: true, requiresKiosk: false, requiresRole: 'admin' },
    ])
    expect(routes[2].meta?.menuLabel).toEqual({ en: 'operator' })
    expect(routes[2].meta?.applicationPermissions).toEqual(['records_manage'])
  })
})
