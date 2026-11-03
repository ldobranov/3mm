// Administrator-only host configuration; deliberately outside application SDK.
import axios from 'axios'
import { getBackendUrl } from './runtime-config'
import { getToken } from './auth'

export interface HardwareStatus {
  device_id: string; supported: boolean; reason: string | null; can_enable: boolean
  revision?: string; model?: string; configured?: boolean; ready?: boolean; reboot_required?: boolean
  live?: { adapter_present: boolean; device_node_present: boolean; agent_running: boolean; agent_access: boolean; clock_hz: number | null }
  operation: null | { request_id: string; state: string; reason: string | null; restart_request_id: string | null; restart_state: string | null }
  changes?: string[]
}
export class HardwareError extends Error {}
const hex = (value: unknown, length: number): value is string => typeof value === 'string' && new RegExp(`^[0-9a-f]{${length}}$`).test(value)
const states = ['queued', 'applying', 'pending_reboot', 'verified', 'verification_failed', 'failed', 'recovery_required']
export function parseHardwareStatus(value: unknown, deviceId: string): HardwareStatus {
  const s = value as HardwareStatus | null
  if (!s || s.device_id !== deviceId || typeof s.supported !== 'boolean' || typeof s.can_enable !== 'boolean'
      || !(s.reason === null || typeof s.reason === 'string') || !(s.operation === null ||
        s.operation && hex(s.operation.request_id, 32) && states.includes(s.operation.state))) throw new HardwareError('unavailable')
  if (s.supported && (!hex(s.revision, 64) || typeof s.configured !== 'boolean' || typeof s.ready !== 'boolean'
      || !s.live || ['agent_running', 'agent_access', 'adapter_present', 'device_node_present'].some(k =>
        typeof s.live?.[k as 'agent_running'] !== 'boolean')
      || !Array.isArray(s.changes) || !s.changes.every(p => typeof p === 'string'))) throw new HardwareError('unavailable')
  if (s.can_enable && !s.supported) throw new HardwareError('unavailable')
  return s
}
export function newHardwareRequestId() {
  // LAN HTTP does not expose randomUUID(), but does expose cryptographic bytes.
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('')
}
export function hardwareClient(deviceId: string) {
  if (!/^dev_[0-9a-f]{32}$/.test(deviceId)) throw new HardwareError('unavailable')
  let origin: string | undefined
  async function request(suffix: string, body?: object) {
    let dispatched = false
    try {
      const base = await getBackendUrl(), token = getToken()
      if (!token) throw new HardwareError('denied')
      if (origin !== undefined && origin !== base) throw new HardwareError('unavailable')
      origin = base; dispatched = true
      return (await axios.request({ url: `${base}/api/v1/devices/${deviceId}/hardware-interfaces${suffix}`,
        method: body ? 'POST' : 'GET', data: body, timeout: 15000, withCredentials: false,
        headers: { Authorization: `Bearer ${token}` } })).data
    } catch (error) {
      if (error instanceof HardwareError) throw error
      const status = axios.isAxiosError(error) ? error.response?.status : undefined
      throw new HardwareError(status === 401 || status === 403 ? 'denied' : body && dispatched ? 'unconfirmed' : 'unavailable')
    }
  }
  return {
    async inspect() { return parseHardwareStatus(await request(''), deviceId) },
    async mutate(kind: 'enable' | 'restart', snapshot: HardwareStatus, requestId: string) {
      if (snapshot.device_id !== deviceId || !hex(snapshot.revision, 64) || !hex(requestId, 32)
          || !snapshot.supported || (kind === 'enable' ? !snapshot.can_enable :
            snapshot.operation?.state !== 'pending_reboot' || !!snapshot.operation?.restart_request_id)) throw new HardwareError('unavailable')
      const body = { request_id: requestId, expected_revision: snapshot.revision,
        confirmation: `${kind === 'enable' ? 'ENABLE I2C' : 'RESTART'} ${deviceId}`,
        ...(kind === 'restart' ? { source_request_id: snapshot.operation!.request_id } : {}) }
      const result = await request(kind === 'enable' ? '/i2c/enable' : '/restart', body)
      if (result?.status !== 'queued' || result?.request_id !== requestId) throw new HardwareError('unconfirmed')
    },
  }
}
