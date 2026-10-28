// Core administrator transport; never exported through the application SDK.
import axios from 'axios'
import { getBackendUrl } from './runtime-config'
import { getToken } from './auth'

export interface DeviceProvider {
  schema_version: 1 | 2; device_id: string; provider_type: string; provider_id: string
  provider_version: string; revision: number; enabled: boolean
  capabilities: { capability_id: string }[]; configured_capability_ids: string[] | null
}
export interface DeviceCapabilityOffer {
  capability_id: string; provider_type: string | null; provider_id: string | null
  provider_version: string | null; registered: boolean; available: boolean | null
  unavailable_reason: string | null
}
export type CapabilityAdminErrorCode = 'denied' | 'conflict' | 'unavailable' | 'unconfirmed'
export class CapabilityAdminError extends Error {
  constructor(readonly code: CapabilityAdminErrorCode) { super(code) }
}
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const id = (v: unknown): v is string => typeof v === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/.test(v)
const providerType = (v: unknown): v is string => typeof v === 'string' && /^[a-z][a-z0-9_.-]{0,63}$/.test(v)
const revision = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 && v <= 2147483646
const ids = (v: unknown): v is string[] => Array.isArray(v) && v.length <= 64 && v.every(id) && new Set(v).size === v.length
const version = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 64
export const providerKey = (v: { provider_type: string; provider_id: string }) => JSON.stringify([v.provider_type, v.provider_id])
export const sameIds = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every(v => b.includes(v))
function fail(): never { throw new CapabilityAdminError('unavailable') }

export function readDeviceProvider(v: unknown, deviceId: string): DeviceProvider {
  if (!object(v) || ![1, 2].includes(Number(v.schema_version)) || typeof v.schema_version !== 'number'
      || v.device_id !== deviceId || !providerType(v.provider_type) || !id(v.provider_id)
      || !version(v.provider_version) || !revision(v.revision) || typeof v.enabled !== 'boolean'
      || !Array.isArray(v.capabilities) || v.capabilities.length > 64) fail()
  const capabilities = v.capabilities.map(c => { if (!object(c) || !id(c.capability_id)) fail(); return { capability_id: c.capability_id } })
  if (new Set(capabilities.map(c => c.capability_id)).size !== capabilities.length) fail()
  if (v.schema_version === 2 && !ids(v.configured_capability_ids)) fail()
  return { schema_version: v.schema_version as 1 | 2, device_id: deviceId,
    provider_type: v.provider_type, provider_id: v.provider_id, provider_version: v.provider_version,
    revision: v.revision, enabled: v.enabled, capabilities,
    configured_capability_ids: v.schema_version === 2 ? [...v.configured_capability_ids as string[]] : null }
}

export function readDeviceOffers(v: unknown): DeviceCapabilityOffer[] {
  if (!Array.isArray(v) || v.length > 16384) fail()
  const result = v.map(row => {
    if (!object(row) || !id(row.capability_id) || typeof row.registered !== 'boolean'
        || (row.available !== null && typeof row.available !== 'boolean')
        || (row.provider_type !== null && !providerType(row.provider_type))
        || (row.provider_id !== null && !id(row.provider_id))
        || (row.provider_version !== null && !version(row.provider_version))
        || (row.unavailable_reason !== null && (typeof row.unavailable_reason !== 'string'
          || !/^[a-z0-9_.-]{1,120}$/.test(row.unavailable_reason)))
        || (row.provider_type === null) !== (row.provider_id === null)
        || (row.available === true && (row.registered !== true || row.provider_id === null))) fail()
    return { capability_id: row.capability_id, provider_type: row.provider_type as string | null,
      provider_id: row.provider_id as string | null, provider_version: row.provider_version as string | null,
      registered: row.registered, available: row.available as boolean | null,
      unavailable_reason: row.unavailable_reason as string | null }
  })
  if (new Set(result.map(row => JSON.stringify([row.provider_type, row.provider_id, row.capability_id]))).size !== result.length) fail()
  return result
}

export function createDeviceCapabilitiesClient(deviceId: string) {
  if (!/^dev_[a-f0-9]{32}$/.test(deviceId)) fail()
  const basePath = `/api/v1/devices/${deviceId}`
  let origin: string | undefined
  async function request(path: string, body?: object) {
    let dispatched = false
    try {
      const base = await getBackendUrl(), token = getToken()
      if (!token) throw new CapabilityAdminError('denied')
      if (origin !== undefined && origin !== base) fail()
      origin = base; dispatched = true
      // One request only. A lost mutation acknowledgement requires a fresh read.
      return (await axios.request({ url: base + basePath + path, method: body ? 'POST' : 'GET',
        data: body, headers: { Authorization: `Bearer ${token}` }, timeout: 15000, withCredentials: false })).data
    } catch (error) {
      if (error instanceof CapabilityAdminError) throw error
      const status = axios.isAxiosError(error) ? error.response?.status : undefined
      throw new CapabilityAdminError(status === 401 || status === 403 ? 'denied' : status === 409 ? 'conflict'
        : body && dispatched ? 'unconfirmed' : 'unavailable')
    }
  }
  async function mutate(provider: DeviceProvider, selection: string[] | boolean) {
    const configuration = Array.isArray(selection)
    if (provider.device_id !== deviceId || !revision(provider.revision)
        || (configuration && (provider.schema_version !== 2 || !ids(selection)
          || selection.some(value => !provider.capabilities.some(c => c.capability_id === value))))) fail()
    const suffix = configuration ? '/configuration' : '/enabled'
    const body = { expected_revision: provider.revision, ...(configuration ? { capability_ids: selection } : { enabled: selection }) }
    const value = await request(`/capability-providers/${encodeURIComponent(provider.provider_type)}/${encodeURIComponent(provider.provider_id)}${suffix}`, body)
    try {
      const next = readDeviceProvider(value, deviceId)
      if (providerKey(next) !== providerKey(provider) || next.provider_version !== provider.provider_version
          || next.schema_version !== provider.schema_version || next.revision < provider.revision || next.revision > provider.revision + 1
          || !sameIds(next.capabilities.map(c => c.capability_id), provider.capabilities.map(c => c.capability_id))
          || next.enabled !== (configuration ? provider.enabled : selection)
          || !sameIds(next.configured_capability_ids ?? [], configuration ? selection : provider.configured_capability_ids ?? [])) fail()
      return next
    } catch { throw new CapabilityAdminError('unconfirmed') }
  }
  return {
    async inspect() {
      const [value, offers] = await Promise.all([request('/capability-providers'), request('/capabilities?registry_version=3')])
      if (!Array.isArray(value) || value.length > 256) fail()
      const providers = value.map(p => readDeviceProvider(p, deviceId))
      if (new Set(providers.map(providerKey)).size !== providers.length) fail()
      return { providers, offers: readDeviceOffers(offers) }
    },
    async offers() { return readDeviceOffers(await request('/capabilities?registry_version=3')) },
    configure: (provider: DeviceProvider, selection: string[]) => mutate(provider, selection),
    enable: (provider: DeviceProvider, enabled: boolean) => mutate(provider, enabled),
  }
}
