import { markRaw } from 'vue'

import http from '@/utils/dynamic-http'

export type CompiledUiKind = 'widget' | 'route' | 'editor' | 'component'

export interface CompiledUiEntrypoint {
  entrypoint_id: string
  kind: CompiledUiKind
  source: string
  label: { en: string; translations?: Record<string, string> }
  route?: string | null
  target_entrypoint_id?: string | null
  requires_role?: string | null
  asset_url: string
}

export interface CompiledUiPackage {
  module_id: string
  name: string
  version: string
  source_sha256: string
  styles: string[]
  entrypoints: CompiledUiEntrypoint[]
}

let catalogPromise: Promise<CompiledUiPackage[]> | null = null
const componentPromises = new Map<string, Promise<any>>()
const loadedStyles = new Set<string>()

export function compiledWidgetType(pkg: CompiledUiPackage, entrypoint: CompiledUiEntrypoint): string {
  return `compiled:${pkg.module_id}:${pkg.version}:${entrypoint.entrypoint_id}`
}

export async function getCompiledUiCatalog(refresh = false): Promise<CompiledUiPackage[]> {
  if (refresh || !catalogPromise) {
    catalogPromise = Promise.all([
      http.get('/api/v1/modules/compiled-ui/catalog'),
      http.getCurrentBackendUrl(),
    ]).then(([response, backendUrl]) => {
      const base = backendUrl || window.location.origin
      return (response.data?.items || []).map((pkg: CompiledUiPackage) => ({
        ...pkg,
        styles: pkg.styles.map(url => new URL(url, `${base}/`).toString()),
        entrypoints: pkg.entrypoints.map(entrypoint => ({
          ...entrypoint,
          asset_url: new URL(entrypoint.asset_url, `${base}/`).toString(),
        })),
      }))
    })
  }
  return catalogPromise
}

export async function findCompiledEntrypoint(
  widgetType: string
): Promise<{ pkg: CompiledUiPackage; entrypoint: CompiledUiEntrypoint } | null> {
  const match = /^compiled:([^:]+):([^:]+):([^:]+)$/.exec(widgetType)
  if (!match) return null
  const [, moduleId, version, entrypointId] = match
  for (const pkg of await getCompiledUiCatalog()) {
    if (pkg.module_id !== moduleId || pkg.version !== version) continue
    const entrypoint = pkg.entrypoints.find(item => item.entrypoint_id === entrypointId)
    if (entrypoint) return { pkg, entrypoint }
  }
  return null
}

function loadStyles(urls: string[]): void {
  for (const url of urls) {
    if (loadedStyles.has(url)) continue
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = url
    link.dataset.compiledUiStyle = url
    document.head.appendChild(link)
    loadedStyles.add(url)
  }
}

export async function loadCompiledComponent(
  pkg: CompiledUiPackage,
  entrypoint: CompiledUiEntrypoint
): Promise<any> {
  loadStyles(pkg.styles)
  let promise = componentPromises.get(entrypoint.asset_url)
  if (!promise) {
    promise = import(/* @vite-ignore */ entrypoint.asset_url).then(module => {
      if (!module.default) throw new Error(`Compiled entrypoint has no default export: ${entrypoint.entrypoint_id}`)
      return markRaw(module.default)
    })
    componentPromises.set(entrypoint.asset_url, promise)
  }
  return promise
}

export async function loadCompiledComponentForType(
  widgetType: string,
  kind: CompiledUiKind = 'widget'
): Promise<any | null> {
  const resolved = await findCompiledEntrypoint(widgetType)
  if (!resolved || resolved.entrypoint.kind !== kind) return null
  return loadCompiledComponent(resolved.pkg, resolved.entrypoint)
}
