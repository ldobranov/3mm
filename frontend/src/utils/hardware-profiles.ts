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
  device_id: string; approval_supported: boolean; items: HardwareProfilePackage[]
}
export class HardwareProfileError extends Error {}
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const hex = (v: unknown, n: number): v is string => typeof v === 'string' && new RegExp(`^[0-9a-f]{${n}}$`).test(v)
function fail(): never { throw new HardwareProfileError('unavailable') }
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
  return { device_id: deviceId, approval_supported: value.approval_supported, items }
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
        : code === 409 ? 'conflict' : method !== 'GET' && sent ? 'unconfirmed' : 'unavailable')
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
