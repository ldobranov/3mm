// Private Core dialog adapter. Never exported through the application import map.
import axios from 'axios'
import { getBackendUrl } from '@/utils/runtime-config'
import { getToken } from '@/utils/auth'

export interface ConnectorState {
  connector_id: string; artifact_sha256: string; snapshot: string
  authentication: 'none' | 'basic' | 'bearer' | 'api_key'
  allowed_schemes: readonly string[]; path_prefix: string; destination_origin: string | null
  credential: null | { secret_ref: string; label: string; version: number; revoked: boolean }
  affected_connector_ids: readonly string[]; reasons: readonly string[]
  state: 'unconfigured' | 'configured' | 'disabled' | 'unavailable'
  authority: 'not_granted' | 'granted' | 'stale'
}
export interface ConnectorCredential {
  secret_ref: string; label: string; authentication: string; version: number; revoked: boolean
}
export interface ConnectorSettings {
  module_id: string; artifact_sha256: string; snapshot: string; installation_id: number | null
  encryption_available: boolean; connectors: readonly ConnectorState[]; credentials: readonly ConnectorCredential[]
}
export type ConnectorOutcome = { request_id: string; status: 'unknown' } |
  { request_id: string; status: 'applied'; state: ConnectorState }
export interface ConnectorSave {
  request_id: string; expected_snapshot: string; action: 'save' | 'rotate' | 'revoke'
  destination_origin?: string; secret_ref?: string; create_credential?: boolean; credential_label?: string
  credential?: Record<string, string>; confirm_credential_change?: boolean
}
export class ConnectorSettingsError extends Error {
  constructor(readonly code: 'access_denied' | 'conflict' | 'invalid_request' | 'unavailable' | 'unconfirmed' | 'stop_required',
    readonly rejected = false) {
    super(code); this.name = 'ConnectorSettingsError'
  }
}
const object = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v)
const digest = /^[a-f0-9]{64}$/, identifier = /^[a-z][a-z0-9_]{0,63}$/, secretRef = /^secret_[a-f0-9]{32}$/
const strings = (v: unknown, max = 64): v is string[] => Array.isArray(v) && v.length <= max && v.every(s => typeof s === 'string' && s.length <= 512)
function fail(): never { throw new ConnectorSettingsError('unavailable') }
function credential(v: unknown) {
  if (!object(v) || typeof v.secret_ref !== 'string' || !secretRef.test(v.secret_ref) || typeof v.label !== 'string'
      || v.label.length > 120 || !Number.isSafeInteger(v.version) || Number(v.version) < 1 || typeof v.revoked !== 'boolean') fail()
  return { secret_ref: v.secret_ref as string, label: v.label as string, version: v.version as number, revoked: v.revoked as boolean }
}
function state(v: unknown, sha: string): ConnectorState {
  if (!object(v) || v.artifact_sha256 !== sha || typeof v.connector_id !== 'string' || !identifier.test(v.connector_id)
      || typeof v.snapshot !== 'string' || !digest.test(v.snapshot) || !strings(v.allowed_schemes, 2)
      || v.allowed_schemes.some(s => !['http', 'https'].includes(s)) || typeof v.path_prefix !== 'string'
      || !strings(v.affected_connector_ids) || !strings(v.reasons)
      || (v.destination_origin !== null && typeof v.destination_origin !== 'string')
      || !['none','basic','bearer','api_key'].includes(String(v.authentication))
      || !['unconfigured','configured','disabled','unavailable'].includes(String(v.state))
      || !['not_granted','granted','stale'].includes(String(v.authority))) fail()
  return { connector_id: v.connector_id, artifact_sha256: sha, snapshot: v.snapshot,
    authentication: v.authentication as ConnectorState['authentication'], allowed_schemes: [...v.allowed_schemes],
    path_prefix: v.path_prefix, destination_origin: v.destination_origin as string | null,
    credential: v.credential === null ? null : credential(v.credential), affected_connector_ids: [...v.affected_connector_ids],
    reasons: [...v.reasons], state: v.state as ConnectorState['state'], authority: v.authority as ConnectorState['authority'] }
}
export function readConnectorSettings(v: unknown, sha: string): ConnectorSettings {
  if (!object(v) || v.artifact_sha256 !== sha || typeof v.module_id !== 'string'
      || typeof v.snapshot !== 'string' || !digest.test(v.snapshot) || typeof v.encryption_available !== 'boolean'
      || (v.installation_id !== null && (!Number.isSafeInteger(v.installation_id) || Number(v.installation_id) < 1))
      || !Array.isArray(v.connectors) || v.connectors.length > 64 || !Array.isArray(v.credentials) || v.credentials.length > 128) fail()
  const connectors = v.connectors.map(c => state(c, sha))
  if (new Set(connectors.map(c => c.connector_id)).size !== connectors.length || connectors.some(c => c.snapshot !== v.snapshot)) fail()
  return { module_id: v.module_id, artifact_sha256: sha, snapshot: v.snapshot, encryption_available: v.encryption_available,
    installation_id: v.installation_id as number | null, connectors, credentials: v.credentials.map(c => {
      if (!object(c) || !['basic','bearer','api_key'].includes(String(c.authentication))) fail()
      return { ...credential(c), authentication: c.authentication as string }
    }) }
}
export function readConnectorOutcome(v: unknown, sha: string, requestId: string): ConnectorOutcome {
  if (!object(v) || v.request_id !== requestId) fail()
  if (v.status === 'unknown') return { request_id: requestId, status: 'unknown' }
  if (v.status !== 'applied') fail()
  return { request_id: requestId, status: 'applied', state: state(v.state, sha) }
}
export function createConnectorSettingsClient(sha: string) {
  if (!digest.test(sha)) fail()
  const prefix = `/api/v1/application-extensions/packages/${sha}/connector-settings`
  let origin: string | undefined
  async function request(path: string, body?: ConnectorSave) {
    let dispatched = false
    try {
      const base = await getBackendUrl(), token = getToken()
      if (!token) throw new ConnectorSettingsError('access_denied', true)
      if (origin !== undefined && origin !== base) throw new ConnectorSettingsError('unavailable', true)
      origin = base
      // No shared refresh/retry interceptors, especially for credential mutations.
      dispatched = true
      const result = await axios.request({ url: base + prefix + path, method: body ? 'POST' : 'GET',
        data: body, headers: { Authorization: `Bearer ${token}` }, withCredentials: false, timeout: 15_000 })
      return result.data
    } catch (error) {
      if (error instanceof ConnectorSettingsError) throw error
      if (!dispatched) throw new ConnectorSettingsError('unavailable', true)
      const status = axios.isAxiosError(error) ? error.response?.status : undefined
      const code = axios.isAxiosError(error) ? error.response?.data?.detail?.code : undefined
      throw new ConnectorSettingsError(status === 401 || status === 403 ? 'access_denied'
        : status === 422 || status === 413 ? 'invalid_request' : status === 409
          ? code === 'unavailable' ? 'unavailable' : code === 'stop_required' ? 'stop_required' : 'conflict' : body ? 'unconfirmed' : 'unavailable',
        [401, 403, 409, 413, 422].includes(status ?? 0) && ['access_denied', 'invalid_request', 'conflict', 'unavailable', 'stop_required'].includes(code))
    }
  }
  return {
    async inspect() { return readConnectorSettings(await request(''), sha) },
    async save(connectorId: string, body: ConnectorSave) {
      if (!identifier.test(connectorId) || !/^[a-f0-9]{32}$/.test(body.request_id)) fail()
      const value = await request('/' + connectorId, body)
      try { return readConnectorOutcome(value, sha, body.request_id) }
      catch { throw new ConnectorSettingsError('unconfirmed') }
    },
    async outcome(requestId: string) {
      if (!/^[a-f0-9]{32}$/.test(requestId)) fail()
      return readConnectorOutcome(await request('/outcomes/' + requestId), sha, requestId)
    },
  }
}
