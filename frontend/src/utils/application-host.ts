import axios from 'axios'
import { defineComponent, h, onBeforeUnmount, provide, type Component } from 'vue'
import { getBackendUrl } from './runtime-config'
import { getToken } from './auth'
import type { CompiledUiEntrypoint, CompiledUiPackage } from './compiled-ui'
import { createApplicationSessions } from './application-session-host'
import {
  applicationHostKey, ApplicationHostError,
  type ApplicationHost, type ApplicationHostInfo, type ApplicationPayload,
} from '../extension-ui/application-v1'

const identifier = /^[a-z][a-z0-9_]{0,63}$/
const isObject = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)

function copyPayload(payload: ApplicationPayload): ApplicationPayload {
  let nodes = 0
  function copy(value: unknown, depth = 0): unknown {
    if (++nodes > 10_000 || depth > 32) throw new Error()
    if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (Array.isArray(value)) return Array.from(value, item => copy(item, depth + 1))
    if (isObject(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value))) {
      return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, copy(item, depth + 1)]))
    }
    throw new Error()
  }
  try {
    const result = copy(payload) as ApplicationPayload
    if (new TextEncoder().encode(JSON.stringify(result)).length > 512 * 1024) throw new Error()
    return result
  } catch { throw new ApplicationHostError('invalid_request') }
}

// Core-only factory: no URL, credential, transport or disposal method is public.
export function createApplicationHost(pkg: CompiledUiPackage, entrypoint: CompiledUiEntrypoint) {
  const binding = Object.freeze({ module: pkg.module_id, version: pkg.version, hash: pkg.source_sha256,
    build: pkg.built_ui_sha256,
    entrypoint: entrypoint.entrypoint_id, audience: entrypoint.application_audience })
  if (!/^[a-z0-9]+(?:[.-][a-z0-9]+)+$/.test(binding.module)
      || !/^[a-f0-9]{64}$/.test(binding.hash) || (binding.build !== undefined && !/^[a-f0-9]{64}$/.test(binding.build)) || !identifier.test(binding.entrypoint)
      || !['public', 'kiosk', 'operator', 'administrator'].includes(binding.audience || '')) {
    throw new ApplicationHostError('invalid_request')
  }
  const prefix = `/api/v1/application-extensions/${encodeURIComponent(binding.module)}`
  let disposed = false
  let backend: string | undefined
  const pending = new Set<AbortController>()
  const live = () => { if (disposed) throw new ApplicationHostError('disposed') }
  async function request(path: string, data?: unknown): Promise<unknown> {
    live()
    const controller = new AbortController()
    pending.add(controller)
    try {
      const base = await getBackendUrl()
      live()
      if (backend !== undefined && backend !== base) throw new ApplicationHostError('unavailable')
      backend = base
      // Deliberately do not use the general client's refresh/replay interceptors.
      const token = binding.audience === 'public' ? '' : binding.audience === 'kiosk'
        ? localStorage.getItem('applicationKioskToken') : getToken()
      if (binding.audience !== 'public' && (!token || ['null', 'undefined'].includes(token))) {
        throw new ApplicationHostError('access_denied')
      }
      const response = await axios.request({
        url: `${base}${prefix}${path}`, method: data === undefined ? 'GET' : 'POST', data,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        timeout: 35_000, signal: controller.signal, withCredentials: false,
      })
      live()
      return response.data
    } catch (error) {
      live()
      if (error instanceof ApplicationHostError) throw error
      const status = axios.isAxiosError(error) ? error.response?.status : undefined
      if (status === 401 || status === 403) throw new ApplicationHostError('access_denied')
      // A failed POST may have executed. Never infer rollback or replay it.
      throw new ApplicationHostError(data === undefined ? 'unavailable' : 'unconfirmed')
    } finally { pending.delete(controller) }
  }
  async function getInfo(): Promise<ApplicationHostInfo> {
    const value = await request(`/ui-host/${encodeURIComponent(binding.entrypoint)}?artifact_sha256=${binding.hash}${binding.build === undefined ? '' : `&built_ui_sha256=${binding.build}`}`)
    if (!isObject(value) || value.host_version !== 1 || value.module_id !== binding.module
        || value.active_version !== binding.version || value.artifact_sha256 !== binding.hash
        || value.built_ui_sha256 !== binding.build
        || value.entrypoint_id !== binding.entrypoint || value.audience !== binding.audience
        || !isObject(value.features) || value.features.operations !== true
        || value.features.resource_authority !== 'separate' || value.features.browser_isolation !== false
        || !Array.isArray(value.operations) || value.operations.length > 256) {
      throw new ApplicationHostError('unavailable')
    }
    const ids = new Set<string>()
    const operations = value.operations.map((operation) => {
      if (!isObject(operation) || typeof operation.operation_id !== 'string'
          || !identifier.test(operation.operation_id)
          || ids.has(operation.operation_id)
          || !['query', 'command'].includes(String(operation.kind))
          || operation.idempotency !== (operation.kind === 'query' ? 'forbidden' : 'required')) {
        throw new ApplicationHostError('unavailable')
      }
      ids.add(operation.operation_id)
      return Object.freeze({ operation_id: operation.operation_id, kind: operation.kind,
        idempotency: operation.idempotency })
    })
    // Reconstruct only public fields; unexpected server fields cannot leak tokens.
    return Object.freeze({ host_version: 1, module_id: binding.module, active_version: binding.version,
      artifact_sha256: binding.hash, entrypoint_id: binding.entrypoint, audience: binding.audience!,
      ...(binding.build === undefined ? {} : { built_ui_sha256: binding.build }),
      features: Object.freeze({ operations: true, resource_authority: 'separate', browser_isolation: false }),
      operations: Object.freeze(operations),
    }) as ApplicationHostInfo
  }
  const ui = Object.freeze({ host_version: 1, entrypoint_id: binding.entrypoint, artifact_sha256: binding.hash,
    ...(binding.build === undefined ? {} : { built_ui_sha256: binding.build }) })
  const sessionHost = createApplicationSessions({ request, live, ui, socketUrl(path) {
    live()
    if (!backend || !['operator', 'administrator'].includes(binding.audience || '')) throw new ApplicationHostError('access_denied')
    const url = new URL(`${backend}${prefix}${path}`, location.href)
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new ApplicationHostError('unavailable')
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    return url.href
  } })
  const host: ApplicationHost = Object.freeze({
    getInfo,
    sessions: sessionHost.sessions,
    async invoke(operationId: string, payload: ApplicationPayload, options?: { readonly idempotencyKey?: string }) {
      live()
      if (typeof operationId !== 'string' || !identifier.test(operationId)
          || !isObject(payload)) throw new ApplicationHostError('invalid_request')
      // Capture JSON now so caller mutation during preflight cannot change dispatch.
      const copy = copyPayload(payload)
      const key = options?.idempotencyKey
      const operation = (await getInfo()).operations.find(item => item.operation_id === operationId)
      if (!operation) throw new ApplicationHostError('access_denied')
      if (operation.idempotency === 'required'
          ? typeof key !== 'string' || key.length < 8 || key.length > 160
          : key !== undefined) throw new ApplicationHostError('invalid_request')
      const segment = binding.audience === 'administrator' ? '' : `/${binding.audience}`
      const value = await request(`${segment}/operations/${encodeURIComponent(operationId)}`, {
        payload: copy, ...(key === undefined ? {} : { idempotency_key: key }),
        ui_context: { host_version: 1, entrypoint_id: binding.entrypoint, artifact_sha256: binding.hash,
          ...(binding.build === undefined ? {} : { built_ui_sha256: binding.build }) },
      })
      if (!isObject(value)) throw new ApplicationHostError('unconfirmed')
      return value as ApplicationPayload
    },
  })
  return { host, dispose() {
    disposed = true
    sessionHost.dispose()
    for (const controller of pending) controller.abort()
    pending.clear()
  } }
}

export function withApplicationHost(pkg: CompiledUiPackage, entrypoint: CompiledUiEntrypoint, component: Component) {
  return defineComponent({
    name: 'ApplicationUiHost', inheritAttrs: false,
    setup(_props, { attrs, slots }) {
      const { host, dispose } = createApplicationHost(pkg, entrypoint)
      provide(applicationHostKey, host)
      onBeforeUnmount(dispose)
      return () => h(component, attrs, slots)
    },
  })
}
