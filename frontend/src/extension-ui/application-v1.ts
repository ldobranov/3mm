// Public, credential-free contract. The host is provided only to an application
// route. Same-origin reviewed code is NOT a browser sandbox (see WP5).
import { inject, type InjectionKey } from 'vue'

export const APPLICATION_HOST_VERSION = 1 as const
export type ApplicationAudience = 'public' | 'kiosk' | 'operator' | 'administrator'
export type ApplicationJson = null | boolean | number | string | ApplicationJson[] | { [key: string]: ApplicationJson }
export type ApplicationPayload = { [key: string]: ApplicationJson }
export type ApplicationAdministrationRead = 'devices.list' | 'devices.detail' | 'modules.list' | 'capabilities.list' | 'capabilities.state' | 'commands.get' | 'resources.inspect'
export interface ApplicationResourceObservation {
  readonly scope: string; readonly required: boolean; readonly declared: boolean | null; readonly configured: boolean | null
  readonly access: 'not_evaluated' | 'required' | 'granted'
  readonly readiness: 'not_evaluated' | 'unknown' | 'unavailable' | 'ready'
  readonly reasons: readonly string[]
  readonly provider: { readonly provider_type: string; readonly provider_id: string
    readonly provider_version: string | null; readonly contract_version: string | null } | null
  readonly selected_resource_id: string | null
}
export interface ApplicationResourceDiscovery {
  readonly discovery_version: 1; readonly instance_id: string; readonly artifact_sha256: string
  readonly observed_at: string; readonly resources: readonly ApplicationResourceObservation[]
  readonly admission_required: true
}
export type ApplicationAdministrationAction = 'modules.install' | 'modules.disable' | 'capabilities.invoke'
export interface ApplicationModulePackage {
  readonly module_id: string; readonly version: string; readonly sha256: string; readonly name: string
}
export interface ApplicationCapability {
  readonly capability_id: string; readonly provider_type: string | null; readonly provider_id: string | null
  readonly provider_version: string | null; readonly registered: boolean; readonly available: boolean | null
  readonly unavailable_reason: string | null; readonly declaration_digest: string | null
  readonly contract_version: string | null; readonly contract: ApplicationPayload | null
}
export interface ApplicationCommandReceipt {
  readonly request_id: string; readonly command_id: string; readonly device_id: string; readonly status: string
}
export interface ApplicationCommand extends ApplicationCommandReceipt {
  readonly result: ApplicationPayload | null; readonly error: string | null
  readonly command_type: string; readonly created_at: string; readonly expires_at: string
}
export interface ApplicationCapabilityInvocation {
  readonly capability_id: string; readonly provider_type: string; readonly provider_id: string
  readonly declaration_digest: string; readonly contract_version: string
  readonly action: string; readonly arguments: ApplicationPayload; readonly ttl_seconds?: number
}
export interface ApplicationCapabilityState {
  readonly device_id: string; readonly capability_id: string; readonly values: ApplicationPayload
  readonly observed_at: string; readonly received_at: string
}
export interface ApplicationDevice {
  readonly device_id: string
  readonly display_name: string | null
  readonly role: string
  readonly protocol_version: string
  readonly approved_at: string
  readonly revoked_at: string | null
  readonly online: boolean
  readonly last_seen_at: string | null
  /** Normalized inventory schema v2, or null before the first report. */
  readonly latest_inventory: ApplicationPayload | null
}
export interface ApplicationDeviceDetail extends ApplicationDevice {
  readonly modules: readonly {
    readonly module_id: string
    readonly installed_version: string | null
    readonly desired_version: string
    readonly status: string
    readonly enabled: boolean
    readonly error: string | null
  }[]
}
export interface ApplicationAdministration {
  readonly resources: { inspect(scopes: readonly string[]): Promise<ApplicationResourceDiscovery> }
  readonly modules: {
    list(): Promise<readonly ApplicationModulePackage[]>
    install(deviceId: string, packageSha256: string, requestId: string): Promise<ApplicationCommandReceipt>
    disable(deviceId: string, moduleId: string, requestId: string): Promise<ApplicationCommandReceipt>
  }
  readonly capabilities: {
    list(deviceId: string): Promise<readonly ApplicationCapability[]>
    state(deviceId: string, capabilityId: string): Promise<ApplicationCapabilityState>
    invoke(deviceId: string, invocation: ApplicationCapabilityInvocation, requestId: string): Promise<ApplicationCommandReceipt>
  }
  readonly commands: { get(requestId: string): Promise<ApplicationCommand> }

  /** Current administrator reads, scoped to this route's declared reads. */
  readonly devices: {
    list(options?: { readonly offset?: number; readonly limit?: number }): Promise<{
      readonly items: readonly ApplicationDevice[]; readonly total: number
    }>
    detail(deviceId: string): Promise<ApplicationDeviceDetail>
  }
}
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
    readonly presentation_version?: 1
    readonly administration_reads?: readonly ApplicationAdministrationRead[]
    readonly administration_actions?: readonly ApplicationAdministrationAction[]
  }
  readonly operations: readonly {
    readonly operation_id: string
    readonly kind: 'query' | 'command'
    readonly idempotency: 'required' | 'forbidden'
  }[]
}
export interface ApplicationPresentationInfo {
  readonly locale: string
}
export interface ApplicationPresentation {
  readonly version: 1
  /** Effective Core locale, available synchronously before the application mounts. */
  getInfo(): ApplicationPresentationInfo
  /** Future locale changes. Read getInfo() for the initial value; unsubscribe on disposal. */
  subscribe(listener: (info: ApplicationPresentationInfo) => void): () => void
}
export interface ApplicationHost {
  readonly access: { getInfo(): Promise<ApplicationActorAccess> }
  readonly delegations: {
    create(operationId: string, payload: ApplicationPayload, requestId: string, ttlSeconds?: number): Promise<ApplicationDelegation>
    lookup(delegationId: string): Promise<ApplicationDelegation>
    cancel(delegationId: string): Promise<ApplicationDelegation>
  }
  readonly presentation: ApplicationPresentation
  /** Fresh access/feature information; not a durable grant or resource listing. */
  getInfo(): Promise<ApplicationHostInfo>
  /** Exactly one dispatch, no retry, audience promotion or credential exposure. */
  invoke(operationId: string, payload: ApplicationPayload,
    options?: { readonly idempotencyKey?: string }): Promise<ApplicationPayload>
  /** Optional on older hosts. No URLs, credentials, sockets or retry policy. */
  readonly sessions?: ApplicationSessions
  readonly administration: ApplicationAdministration
  readonly files: ApplicationFiles
}
export interface ApplicationExecutor {
  readonly kind: 'application'; readonly module_id: string; readonly instance_id: string; readonly artifact_sha256: string
}
export interface ApplicationActorAccess {
  readonly access_version: 1; readonly entrypoint_id: string; readonly audience: ApplicationAudience
  readonly built_ui_sha256: string | null
  readonly actor: { readonly kind: 'user' | 'kiosk' | 'anonymous'; readonly user_id: number | null; readonly subject_id: string | null
    readonly terminal_id: string | null; readonly platform_administrator: boolean }
  readonly executor: ApplicationExecutor
  readonly permission_ids: readonly string[]; readonly allowed_operation_ids: readonly string[]
  readonly delegated_operation_ids: readonly string[]
  readonly service_authority: 'separate'; readonly admission_required: true
}
export interface ApplicationDelegation {
  readonly delegation_version: 1; readonly delegation_id: string; readonly operation_id: string; readonly module_id: string
  readonly status: 'pending' | 'running' | 'succeeded' | 'cancelled' | 'expired' | 'denied' | 'unknown'
  readonly initiator: { readonly kind: 'user'; readonly user_id: number; readonly subject_id: string }
  readonly executor: ApplicationExecutor; readonly expires_at: string
  readonly result: ApplicationPayload | null
  readonly error_code: 'expired' | 'authority_changed' | 'execution_unconfirmed' | null
  readonly automatic_retry: false
}
export interface ApplicationFileMetadata {
  readonly file_id: string; readonly size_bytes: number; readonly sha256: string
  readonly filename: string; readonly content_type: string; readonly created_at: number
  readonly origin: null | { readonly file_id: string; readonly sha256: string; readonly job_id: string }
}
export interface ApplicationFiles {
  checksum(file: Blob): Promise<string>
  list(after?: string): Promise<ApplicationPayload>
  stat(fileId: string): Promise<ApplicationFileMetadata>
  begin(fileId: string, file: Blob, options: {sha256:string;filename:string;contentType:string;expectedSha256?:string;requestId?:string}): Promise<ApplicationPayload>
  append(uploadId:string, offset:number, chunk:Blob): Promise<ApplicationPayload>
  uploadStatus(uploadId:string): Promise<ApplicationPayload>
  finalize(uploadId:string, requestId?:string): Promise<ApplicationPayload>
  cancel(uploadId:string, requestId?:string): Promise<ApplicationPayload>
  remove(fileId:string, sha256:string, requestId?:string): Promise<ApplicationPayload>
  /** Bounded chunks; consuming to EOF verifies the complete checksum. No retry. */
  download(fileId:string): Promise<ReadableStream<Uint8Array>>
  createLink(fileId:string, sha256:string, options:{ttlSeconds:number;maxDownloads:number;requestId?:string}): Promise<{readonly linkId:string; readonly expiresAt:number; readonly url:string}>
  revokeLink(linkId:string, requestId?:string): Promise<ApplicationPayload>
  transform(fileId:string, sha256:string, options:{outputId:string;width:number;height:number;format:'png'|'jpeg'|'webp';requestId?:string}): Promise<ApplicationPayload>
  job(jobId:string): Promise<ApplicationPayload>
  operationStatus(requestId:string): Promise<ApplicationPayload>
  /** Exact public CAP11 metadata operations; never arbitrary paths or transport. */
  control(operation:string, fields?:object, requestId?:string): Promise<ApplicationPayload>
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
export type ApplicationHostErrorCode = 'access_denied' | 'unavailable' | 'invalid_request' | 'not_found' | 'unconfirmed' | 'disposed'
  | 'conflict' | 'quota' | 'expired' | 'checksum' | 'provider_unavailable' | 'transform_failed' | 'recovery_required'
export class ApplicationHostError extends Error {
  constructor(readonly code: ApplicationHostErrorCode, readonly requestId?: string) {
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
