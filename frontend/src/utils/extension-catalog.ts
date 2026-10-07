import { BootstrapCache, bootstrapJson } from './bootstrap-cache'
import { getBackendUrl } from './runtime-config'

export interface ExtensionCatalogItem {
  name: string
  version: string
  type?: string
  frontend_routes?: Array<{ path: string; meta?: { requiresAuth?: boolean } }>
}

const cache = new BootstrapCache<ExtensionCatalogItem[]>(10 * 60_000)
let generation = 0
export const invalidateExtensionCatalog = () => {
  ++generation
  cache.invalidate()
}

export async function getExtensionCatalog(refresh = false): Promise<ExtensionCatalogItem[]> {
  const current = generation
  const value = await cache
    .load(async () => {
      const base = await getBackendUrl()
      const data = await bootstrapJson(`${base}/api/extensions/public`)
      const items = Array.isArray(data) ? data : (data as { items?: unknown })?.items
      if (
        !Array.isArray(items) ||
        items.length > 10_000 ||
        items.some(
          (item) =>
            !item ||
            typeof item.name !== 'string' ||
            typeof item.version !== 'string' ||
            (item.frontend_routes !== undefined &&
              (!Array.isArray(item.frontend_routes) ||
                item.frontend_routes.some(
                  (route: any) =>
                    !route ||
                    typeof route.path !== 'string' ||
                    (route.meta !== undefined && (!route.meta || typeof route.meta !== 'object')),
                ))),
        )
      ) {
        throw new Error('Invalid public extension catalog')
      }
      return items
    }, refresh)
    .catch((error) => {
      if (current !== generation) return getExtensionCatalog()
      throw error
    })
  return current === generation ? value : getExtensionCatalog()
}

/** Authentication decisions are synchronous and never trigger discovery. */
export function peekPublicEndpoints(): string[] {
  const paths = ['/api/extensions/public']
  for (const item of cache.peek() || []) {
    for (const route of item.frontend_routes || []) {
      if (typeof route.path === 'string' && route.meta?.requiresAuth === false) {
        const path = route.path.replace(/^\/extension(?=\/|$)/, `/api/extension/${item.name}`)
        paths.push(path, `${path}/*`)
      }
    }
  }
  return paths
}

export function isPublicEndpoint(url: string): boolean {
  const path = new URL(url, 'http://transport.invalid').pathname
  return peekPublicEndpoints().some((pattern) =>
    pattern.endsWith('/*') ? path.startsWith(`${pattern.slice(0, -2)}/`) : path === pattern,
  )
}
