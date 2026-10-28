import type { RouteRecordRaw, Router } from 'vue-router'
import http from '@/utils/dynamic-http'

export interface RuntimeLocalizedText {
  en: string
  translations?: Record<string, string>
}

export interface RuntimeField {
  field_id: string
  label: RuntimeLocalizedText
  kind: 'text' | 'multiline' | 'integer' | 'number' | 'boolean' | 'date' | 'datetime'
  required: boolean
  read_only: boolean
}

export interface RuntimeEntity {
  entity_id: string
  label: RuntimeLocalizedText
  fields: RuntimeField[]
}

export interface RuntimePage {
  page_id: string
  path: string
  title: RuntimeLocalizedText
  entity_id: string
  view: 'table' | 'form' | 'detail'
  actions: Array<'create' | 'read' | 'update' | 'delete'>
  requires_role?: string | null
}

export interface RuntimeNavigationItem {
  navigation_id: string
  page_id: string
  label: RuntimeLocalizedText
  icon?: string | null
  order: number
}

export interface RuntimeExtensionDefinition {
  runtime_extension_version: 1
  module_id: string
  version: string
  name: RuntimeLocalizedText
  description: RuntimeLocalizedText
  entities: RuntimeEntity[]
  pages: RuntimePage[]
  navigation: RuntimeNavigationItem[]
  permissions: Array<'runtime.data.read' | 'runtime.data.write'>
}

export interface RuntimeDefinitionResponse {
  module_id: string
  version: string
  definition: RuntimeExtensionDefinition
  enabled: boolean
}

export interface RuntimeRecord {
  record_id: string
  data: Record<string, unknown>
  created_at: string
  updated_at: string
}

export function localizedLabels(text: RuntimeLocalizedText): Record<string, string> {
  return { en: text.en, ...(text.translations || {}) }
}

export function localizedText(text: RuntimeLocalizedText, language: string): string {
  return text.translations?.[language] || text.en
}

export function buildRuntimeRouteRecords(
  definitions: RuntimeDefinitionResponse[],
): RouteRecordRaw[] {
  return definitions.flatMap(({ definition }) => {
    const navigationByPage = new Map(
      definition.navigation.map(item => [item.page_id, item]),
    )
    return definition.pages.map((page): RouteRecordRaw => {
      const navigation = navigationByPage.get(page.page_id)
      return {
        path: page.path,
        name: `runtime:${definition.module_id}:${page.page_id}`,
        component: () => import('@/views/RuntimeExtensionPage.vue'),
        props: {
          moduleId: definition.module_id,
          pageId: page.page_id,
        },
        meta: {
          requiresAuth: true,
          ...(page.requires_role ? { requiresRole: page.requires_role } : {}),
          ...(navigation ? {
            menuLabel: localizedLabels(navigation.label),
            menuIcon: navigation.icon || undefined,
            menuOrder: navigation.order,
          } : {}),
          isRuntimeExtensionRoute: true,
          runtimeModuleId: definition.module_id,
          runtimePageId: page.page_id,
        },
      }
    })
  })
}

export async function readRuntimeDefinitions(): Promise<RuntimeDefinitionResponse[]> {
  if (!localStorage.getItem('authToken')) return []
  const response = await http.get('/api/v1/runtime-extensions/definitions')
  return Array.isArray(response.data) ? response.data : []
}

export async function reloadRuntimeExtensionRoutes(router: Router): Promise<void> {
  const routes = buildRuntimeRouteRecords(await readRuntimeDefinitions())

  for (const route of router.getRoutes()) {
    if (route.meta?.isRuntimeExtensionRoute && route.name) router.removeRoute(route.name)
  }

  const occupiedPaths = new Set(router.getRoutes().map(route => route.path))
  for (const route of routes) {
    if (occupiedPaths.has(route.path)) {
      console.warn(`Runtime extension route conflicts with an existing route: ${route.path}`)
      continue
    }
    router.addRoute(route)
    occupiedPaths.add(route.path)
  }
}
