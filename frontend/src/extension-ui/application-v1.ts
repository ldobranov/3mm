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
