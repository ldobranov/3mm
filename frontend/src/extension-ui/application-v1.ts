// Public, credential-free contract. The host is provided only to an application
// route. Same-origin reviewed code is NOT a browser sandbox (see WP5).
import { inject, type InjectionKey } from 'vue'

export const APPLICATION_HOST_VERSION = 1 as const
export type ApplicationAudience = 'public' | 'kiosk' | 'operator' | 'administrator'
export type ApplicationJson = null | boolean | number | string | ApplicationJson[] | { [key: string]: ApplicationJson }
export type ApplicationPayload = { [key: string]: ApplicationJson }
export interface ApplicationHostInfo {
  readonly host_version: 1
  readonly module_id: string
  readonly active_version: string
  readonly artifact_sha256: string
  readonly built_ui_sha256?: string
  readonly entrypoint_id: string
  readonly audience: ApplicationAudience
  readonly features: {
    readonly operations: true
    readonly resource_authority: 'separate'
    readonly browser_isolation: false
  }
  readonly operations: readonly {
    readonly operation_id: string
    readonly kind: 'query' | 'command'
    readonly idempotency: 'required' | 'forbidden'
  }[]
}
export interface ApplicationHost {
  /** Fresh access/feature information; not a durable grant or resource listing. */
  getInfo(): Promise<ApplicationHostInfo>
  /** Exactly one dispatch, no retry, audience promotion or credential exposure. */
  invoke(operationId: string, payload: ApplicationPayload,
    options?: { readonly idempotencyKey?: string }): Promise<ApplicationPayload>
  /** Optional on older hosts. No URLs, credentials, sockets or retry policy. */
  readonly sessions?: ApplicationSessions
}
export interface ApplicationSessionTarget {
  readonly bindingId: string
  readonly deviceId: string
  readonly providerId: string
  readonly capabilityIds: readonly string[]
  readonly available: boolean
  readonly accessMode: 'read' | 'write'
  readonly controlActions: readonly string[]
  readonly options: ApplicationPayload
}
export interface ApplicationSessionOpen {
  readonly session_request_version: 1
  readonly request_id: string
  readonly provider_id: string
  readonly capability_id: string
  readonly device_id: string
  readonly access_mode: 'read' | 'write'
  readonly options: ApplicationPayload
}
export interface ApplicationSessionAcceptance {
  readonly request_id: string; readonly session_id: string; readonly state: 'active'
  readonly provider_id: string; readonly capability_id: string; readonly device_id: string
}
export interface ApplicationSessionControl {
  readonly session_id: string; readonly control_id: string; readonly action: string
  readonly arguments: ApplicationPayload
}
export interface ApplicationSessions {
  targets(): Promise<readonly ApplicationSessionTarget[]>
  resolveTarget(bindingOrDeviceId: string): Promise<ApplicationSessionTarget>
  /** One attempt only; uncertain completion is never re-opened automatically. */
  open(request: ApplicationSessionOpen): Promise<ApplicationSessionAcceptance>
  sendData(sessionId: string, data: Uint8Array): Promise<void>
  control(message: ApplicationSessionControl): Promise<void>
  close(sessionId: string): Promise<void>
  observe(sessionId: string, handlers: { onData(data: Uint8Array): void; onClosed(reason?: string): void }): () => void
}
export type ApplicationHostErrorCode = 'access_denied' | 'unavailable' | 'invalid_request' | 'unconfirmed' | 'disposed'
export class ApplicationHostError extends Error {
  constructor(readonly code: ApplicationHostErrorCode) {
    super(`Application host: ${code}`)
    this.name = 'ApplicationHostError'
  }
}
// Symbol identity survives the separately emitted public module.
export const applicationHostKey = Symbol.for('3mm.application-host.v1') as InjectionKey<ApplicationHost>
export function useApplicationHost(): ApplicationHost {
  const host = inject(applicationHostKey, undefined)
  if (!host) throw new ApplicationHostError('unavailable')
  return host
}
