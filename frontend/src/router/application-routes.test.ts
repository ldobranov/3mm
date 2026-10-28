import { describe, expect, it, vi } from 'vitest'

import { compiledRouteRecords, createRouterWithDynamicRoutes } from './index'
import http from '@/utils/dynamic-http'
import * as compiledUi from '@/utils/compiled-ui'
import type { CompiledUiPackage } from '@/utils/compiled-ui'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { useApplicationHost, type ApplicationHost } from '@/extension-ui/application-v1'
import { i18n } from '@/utils/i18n'


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
  it('removes retired built-in products while preserving installed application routes', async () => {
    const api = vi.spyOn(http, 'get').mockResolvedValue({ data: { items: [] } })
    const catalog = vi.spyOn(compiledUi, 'getCompiledUiCatalog').mockResolvedValue([applicationPackage('operator')])
    try {
      const router = await createRouterWithDynamicRoutes()
      for (const path of ['/extensions/ai-builder', '/automations/proposals', '/dashboard', '/dashboard/1/edit', '/@owner/status']) {
        expect(router.resolve(path).name).toBe('NotFound')
      }
      expect(router.resolve('/application/operator').meta.applicationAudience).toBe('operator')
      expect(router.resolve('/extensions').meta.requiresRole).toBe('admin')
    } finally { api.mockRestore(); catalog.mockRestore() }
  })
  it('provides the public host at the actual dynamic route boundary and disposes it on unmount', async () => {
    let host!: ApplicationHost
    const locale = ref('bg-BG'), changed = vi.fn()
    const language = vi.spyOn(i18n, 'getCurrentLanguage').mockImplementation(() => locale.value)
    const child = defineComponent({ props: { locale: String }, setup(props) {
      host = useApplicationHost()
      host.presentation.subscribe(changed)
      return () => h('p', ['Loaded application', h('span', props.locale)])
    } })
    const loader = vi.spyOn(compiledUi, 'loadCompiledComponent').mockResolvedValue(child)
    try {
      const pkg = applicationPackage('operator')
      const route = compiledRouteRecords([pkg])[0]
      const component = await (route.component as () => Promise<ReturnType<typeof defineComponent>>)()
      const wrapper = mount(component)
      expect(wrapper.find('span').text()).toBe('bg-BG')
      expect(host.presentation.getInfo()).toEqual({ locale: 'bg-BG' })
      expect(Object.keys(host)).toEqual(['access', 'delegations', 'presentation', 'getInfo', 'sessions', 'administration', 'files', 'invoke'])
      expect(loader).toHaveBeenCalledWith(pkg, pkg.entrypoints[0])
      locale.value = 'en'
      await nextTick()
      expect(wrapper.find('span').text()).toBe('en')
      expect(changed).toHaveBeenCalledExactlyOnceWith({ locale: 'en' })
      wrapper.unmount()
      locale.value = 'bg'
      expect(changed).toHaveBeenCalledOnce()
      expect(() => host.presentation.getInfo()).toThrowError(expect.objectContaining({ code: 'disposed' }))
      await expect(host.getInfo()).rejects.toMatchObject({ code: 'disposed' })
      await expect(host.sessions!.targets()).rejects.toMatchObject({ code: 'disposed' })
    } finally { loader.mockRestore(); language.mockRestore() }
  })
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
      for (const path of ['/system/updates', '/settings/ui-preview']) {
        const route = router.resolve(path)
        expect(route.meta.requiresAuth).toBe(true)
        expect(route.meta.requiresRole).toBe('admin')
        expect(automatic.some(item => item.path === path)).toBe(false)
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
