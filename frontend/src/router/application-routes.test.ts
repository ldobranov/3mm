import { describe, expect, it } from 'vitest'

import { compiledRouteRecords } from './index'
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
