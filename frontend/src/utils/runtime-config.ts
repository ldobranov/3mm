import { BootstrapCache, bootstrapJson } from './bootstrap-cache'

const STORAGE_KEY = 'mm_backend_url_override'
const cache = new BootstrapCache<string>(5 * 60_000)
let generation = 0
export const normalizeBaseUrl = (url: string) => url.trim().replace(/\/+$/, '')

function override(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

async function resolveBackendUrl(): Promise<string> {
  const saved = override()
  if (saved !== null) return normalizeBaseUrl(saved) // Empty means same-origin/proxy.
  try {
    const config = (await bootstrapJson('/runtime-config.json')) as Record<string, unknown>
    if (typeof config?.backend_url === 'string') return normalizeBaseUrl(config.backend_url)
    if (
      Number.isInteger(config?.backend_port) &&
      Number(config.backend_port) > 0 &&
      Number(config.backend_port) <= 65535
    ) {
      return `${location.protocol}//${location.hostname}:${config.backend_port}`
    }
  } catch {
    /* Use portable configuration fallbacks, not repeated discovery probes. */
  }
  try {
    const config = (await bootstrapJson('/frontend-config')) as Record<string, unknown>
    if (typeof config?.backend_url === 'string') return normalizeBaseUrl(config.backend_url)
  } catch {
    /* The bounded fallback is also cached. */
  }
  if (cache.peek() !== undefined) {
    // A transient outage must not replace a verified split-origin URL with a
    // guess. Let the shared cache retain it and apply the failure cooldown.
    throw new Error('Runtime configuration is unavailable')
  }
  if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') return ''
  const configured = (globalThis as { __BACKEND_URL__?: string }).__BACKEND_URL__
  const port = configured ? new URL(configured).port || '8887' : '8887'
  return `${location.protocol}//${location.hostname}:${port}`
}

export async function getBackendUrl(): Promise<string> {
  const current = generation
  const value = await cache.load(resolveBackendUrl)
  return current === generation ? value : getBackendUrl()
}

export function invalidateRuntimeConfig() {
  ++generation
  cache.invalidate()
}
export function setBackendOverride(url: string): string {
  const value = normalizeBaseUrl(url)
  localStorage.setItem(STORAGE_KEY, value)
  invalidateRuntimeConfig()
  return value
}
export function clearBackendOverride() {
  localStorage.removeItem(STORAGE_KEY)
  if (override() !== null) throw new Error('Backend URL override could not be cleared')
  invalidateRuntimeConfig()
}
