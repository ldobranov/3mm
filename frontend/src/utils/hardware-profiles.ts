// Administrator module lifecycle, not an application permission or a raw bus API.
import axios from 'axios'
import { getBackendUrl } from './runtime-config'
import { getToken } from './auth'
export { newHardwareRequestId } from './hardware-interfaces'

export interface HardwareProfilePackage {
  module_id: string; name: string; version: string; sha256: string
  profile: { schema_version: 1; profile_sha256: string; simulated: boolean; configuration: Record<string, unknown> }
  installed_exact: boolean; request_id: string | null
  installation: null | { status: string; enabled: boolean; command_id: string | null; error: string | null }
}
export interface HardwareProfileCatalog {
  device_id: string; approval_supported: boolean; items: HardwareProfilePackage[]; templates: HardwareProviderTemplate[]
}
export interface HardwareProviderField {
  key: string; label: string; type: 'text' | 'number' | 'select' | 'checkbox'
  default: string | number | boolean; min?: number; max?: number; maxlength?: number; pattern?: string
  options?: { value: string; label: string }[]
}
export interface HardwareProviderTemplate {
  template_id: string; name: string; simulated: boolean; fields: HardwareProviderField[]; help?: string
}
export class HardwareProfileError extends Error {}
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const hex = (v: unknown, n: number): v is string => typeof v === 'string' && new RegExp(`^[0-9a-f]{${n}}$`).test(v)
function fail(): never { throw new HardwareProfileError('unavailable') }
function readTemplates(value: unknown): HardwareProviderTemplate[] {
  if (!Array.isArray(value) || value.length > 32) fail()
  return value.map((v: unknown) => {
    if (!object(v) || typeof v.template_id !== 'string' || !/^[a-z0-9.-]{1,80}$/.test(v.template_id)
        || typeof v.name !== 'string' || typeof v.simulated !== 'boolean'
        || !Array.isArray(v.fields) || !v.fields.length || v.fields.length > 16) fail()
    if (v.help !== undefined && (typeof v.help !== 'string' || !v.help.length || v.help.length > 1000)) fail()
    const fields = v.fields.map((f: unknown): HardwareProviderField => {
      if (!object(f) || typeof f.key !== 'string' || !/^[a-z][a-z0-9_]{0,63}$/.test(f.key)
          || typeof f.label !== 'string' || !['text', 'number', 'select', 'checkbox'].includes(String(f.type))
          || !['string', 'number', 'boolean'].includes(typeof f.default)) fail()
      if (f.type === 'checkbox' ? typeof f.default !== 'boolean'
          : f.type === 'number' ? typeof f.default !== 'number' || !Number.isInteger(f.default)
          : f.type === 'text' && typeof f.default !== 'string') fail()
      for (const key of ['min', 'max', 'maxlength']) if (f[key] !== undefined && !Number.isInteger(f[key])) fail()
      if (f.pattern !== undefined && (typeof f.pattern !== 'string' || f.pattern.length > 256)) fail()
      if (f.type === 'select' && (!Array.isArray(f.options) || !f.options.length || f.options.length > 256
          || f.options.some(o => !object(o) || typeof o.value !== 'string' || typeof o.label !== 'string'))) fail()
      return f as unknown as HardwareProviderField
    })
    if (new Set(fields.map(f => f.key)).size !== fields.length) fail()
    return { template_id: v.template_id, name: v.name, simulated: v.simulated, fields,
      ...(typeof v.help === 'string' ? { help: v.help } : {}) }
  })
}
export function readHardwareProfiles(value: unknown, deviceId: string): HardwareProfileCatalog {
  if (!object(value) || value.device_id !== deviceId || typeof value.approval_supported !== 'boolean'
      || !Array.isArray(value.items) || value.items.length > 1024) fail()
  const items = value.items.map((item: unknown): HardwareProfilePackage => {
    if (!object(item) || typeof item.module_id !== 'string' || !/^[A-Za-z0-9_.:-]{1,160}$/.test(item.module_id)
        || typeof item.name !== 'string' || typeof item.version !== 'string' || !hex(item.sha256, 64)
        || typeof item.installed_exact !== 'boolean' || !(item.request_id === null || hex(item.request_id, 32))) fail()
    const p = item.profile, i = item.installation
    if (!object(p) || p.schema_version !== 1 || !hex(p.profile_sha256, 64)
        || typeof p.simulated !== 'boolean' || !object(p.configuration)) fail()
    if (i !== null && (!object(i) || typeof i.status !== 'string' || typeof i.enabled !== 'boolean'
        || !(i.command_id === null || typeof i.command_id === 'string')
        || !(i.error === null || typeof i.error === 'string'))) fail()
    return { module_id: item.module_id, name: item.name, version: item.version, sha256: item.sha256,
      profile: p as unknown as HardwareProfilePackage['profile'], installed_exact: item.installed_exact,
      request_id: item.request_id as string | null, installation: i as HardwareProfilePackage['installation'] }
  })
  if (new Set(items.map(i => i.sha256)).size !== items.length) fail()
  return { device_id: deviceId, approval_supported: value.approval_supported, items, templates: readTemplates(value.templates) }
}

export function hardwareProfilesClient(deviceId: string) {
  if (!/^dev_[0-9a-f]{32}$/.test(deviceId)) fail()
  let origin: string | undefined
  async function request(path: string, method = 'GET', data?: unknown, requestId?: string) {
    let sent = false
    try {
      const base = await getBackendUrl(), token = getToken()
      if (!token) throw new HardwareProfileError('denied')
      if (origin !== undefined && origin !== base) fail()
      origin = base; sent = true
      return (await axios.request({ url: base + path, method, data, timeout: 20000,
        headers: { Authorization: `Bearer ${token}`, ...(requestId ? { 'Idempotency-Key': requestId } : {}) },
        withCredentials: false })).data
    } catch (error) {
      if (error instanceof HardwareProfileError) throw error
      const code = axios.isAxiosError(error) ? error.response?.status : undefined
      throw new HardwareProfileError(code === 401 || code === 403 ? 'denied'
        : code === 409 ? 'conflict' : code === 422 ? 'invalidConfiguration'
        : method !== 'GET' && sent ? 'unconfirmed' : 'unavailable')
    }
  }
  return {
    async inspect() {
      return readHardwareProfiles(await request(`/api/v1/modules/devices/${deviceId}/hardware-profiles`), deviceId)
    },
    async upload(file: File) {
      if (!file.size || file.size > 10 * 1024 * 1024) fail()
      const form = new FormData(); form.append('package', file)
      await request('/api/v1/modules/packages', 'POST', form)
    },
    async prepare(templateId: string, configuration: Record<string, string | number | boolean>) {
      if (!/^[a-z0-9.-]{1,80}$/.test(templateId)) fail()
      const value = await request(`/api/v1/modules/devices/${deviceId}/hardware-profiles/prepare`,
        'POST', { template_id: templateId, configuration })
      if (!object(value) || value.device_id !== deviceId || value.activation !== 'not_requested'
          || !hex(value.package_sha256, 64) || !hex(value.profile_sha256, 64)) fail()
      return value.package_sha256
    },
    async mutate(action: 'install' | 'disable', item: HardwareProfilePackage, requestId: string) {
      if (!hex(item.sha256, 64) || !hex(item.profile.profile_sha256, 64) || !hex(requestId, 32)) fail()
      const path = action === 'install' ? `/packages/${item.sha256}/devices/${deviceId}/install`
        : `/${encodeURIComponent(item.module_id)}/devices/${deviceId}/disable`
      const data = action === 'install' && !item.profile.simulated ? { hardware_profile_approval: {
        schema_version: 1, device_id: deviceId, package_sha256: item.sha256,
        profile_sha256: item.profile.profile_sha256 } } : {}
      await request('/api/v1/modules' + path, 'POST', data, requestId)
    },
  }
}
