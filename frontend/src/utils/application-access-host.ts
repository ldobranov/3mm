import { ApplicationHostError, type ApplicationActorAccess, type ApplicationDelegation,
  type ApplicationPayload, type ApplicationExecutor } from '../extension-ui/application-v1'

const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const id = /^[a-z][a-z0-9_]{0,95}$/
const hex = /^[a-f0-9]{32}$/
const exact = (v: unknown, keys: string[]): v is Record<string, unknown> => object(v)
  && Object.keys(v).length === keys.length && keys.every(k => k in v)
const ids = (v: unknown, max: number): v is string[] => Array.isArray(v) && v.length <= max
  && v.every(x => typeof x === 'string' && id.test(x)) && new Set(v).size === v.length
const subject = (v: unknown): v is string => typeof v === 'string' && /^usr_[a-f0-9]{32}$/.test(v)
const userId = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) > 0
type Binding = { moduleId: string; artifact: string; entrypoint: string; audience: string; build?: string }
const executor = (v: unknown, b: Binding): v is ApplicationExecutor => exact(v, ['kind','module_id','instance_id','artifact_sha256'])
  && v.kind === 'application' && v.module_id === b.moduleId && v.artifact_sha256 === b.artifact
  && typeof v.instance_id === 'string' && /^[a-f0-9]{24}$/.test(v.instance_id)
function invalid(): never { throw new ApplicationHostError('unavailable') }
const asciiSize = (v: unknown) => JSON.stringify(v).replace(/[\u007f-\uffff]/g, c => '\\u'+c.charCodeAt(0).toString(16).padStart(4,'0')).length
const validString = (s: string) => Array.from(s).length <= 4096
  && !Array.from(s).some(c => c.length === 1 && c.charCodeAt(0) >= 0xd800 && c.charCodeAt(0) <= 0xdfff)
function freeze<T>(value: T): T {
  if (value !== null && typeof value === 'object') {
    for (const v of Object.values(value)) freeze(v)
    Object.freeze(value)
  }
  return value
}

export function readActorAccess(v: unknown, b: Binding): ApplicationActorAccess {
  if (!exact(v, ['access_version','entrypoint_id','audience','built_ui_sha256','actor','executor',
      'permission_ids','allowed_operation_ids','delegated_operation_ids','service_authority','admission_required'])
      || v.access_version !== 1 || v.entrypoint_id !== b.entrypoint || v.audience !== b.audience
      || v.built_ui_sha256 !== (b.build ?? null) || !executor(v.executor, b)
      || !exact(v.actor, ['kind','user_id','subject_id','terminal_id','platform_administrator'])
      || typeof v.actor.platform_administrator !== 'boolean'
      || !ids(v.permission_ids, 96) || !ids(v.allowed_operation_ids, 256) || !ids(v.delegated_operation_ids, 16)
      || v.delegated_operation_ids.some(x => !(v.allowed_operation_ids as string[]).includes(x))
      || b.audience !== 'operator' && v.delegated_operation_ids.length > 0
      || v.service_authority !== 'separate' || v.admission_required !== true) invalid()
  const a = v.actor
  if (a.kind === 'user') {
    if (!userId(a.user_id) || !subject(a.subject_id) || a.terminal_id !== null || !['operator','administrator'].includes(b.audience)) invalid()
  } else if (a.kind === 'kiosk') {
    if (b.audience !== 'kiosk' || a.user_id !== null || a.subject_id !== null || a.platform_administrator || typeof a.terminal_id !== 'string' || !hex.test(a.terminal_id) || v.permission_ids.length) invalid()
  } else if (a.kind === 'anonymous') {
    if (b.audience !== 'public' || a.user_id !== null || a.subject_id !== null || a.terminal_id !== null || a.platform_administrator || v.permission_ids.length) invalid()
  } else invalid()
  // Reconstruct a public snapshot, never pass arbitrary response properties.
  return freeze({ ...v, actor: { ...a }, executor: { ...v.executor }, permission_ids: [...v.permission_ids],
    allowed_operation_ids: [...v.allowed_operation_ids], delegated_operation_ids: [...v.delegated_operation_ids] }) as unknown as ApplicationActorAccess
}

export function readDelegation(v: unknown, b: Binding, delegationId: string, copy: (p: ApplicationPayload) => ApplicationPayload): ApplicationDelegation {
  if (!exact(v, ['delegation_version','delegation_id','operation_id','module_id','status','initiator','executor',
      'expires_at','result','error_code','automatic_retry']) || v.delegation_version !== 1
      || v.delegation_id !== delegationId || v.module_id !== b.moduleId || !executor(v.executor, b)
      || typeof v.operation_id !== 'string' || !id.test(v.operation_id)
      || typeof v.status !== 'string' || !['pending','running','succeeded','cancelled','expired','denied','unknown'].includes(v.status)
      || !exact(v.initiator, ['kind','user_id','subject_id']) || v.initiator.kind !== 'user' || !userId(v.initiator.user_id) || !subject(v.initiator.subject_id)
      || typeof v.expires_at !== 'string' || !/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(v.expires_at)
      || !Number.isFinite(Date.parse(v.expires_at)) || v.automatic_retry !== false) invalid()
  const error = ({ expired:'expired', denied:'authority_changed', unknown:'execution_unconfirmed' } as Record<string,string>)[String(v.status)] ?? null
  if (v.error_code !== error || (v.status === 'succeeded') !== object(v.result) || v.status !== 'succeeded' && v.result !== null) invalid()
  let result: ApplicationPayload | null
  try { result = v.result === null ? null : copy(v.result as ApplicationPayload) }
  catch { invalid() }
  if (result && asciiSize(result) > 32768) invalid()
  return freeze({ ...v, initiator: { ...v.initiator }, executor: { ...v.executor }, result }) as unknown as ApplicationDelegation
}

export function createApplicationAccess(deps: Binding & {
  request(path: string, data?: unknown): Promise<unknown>; live(): void
  copyPayload(payload: ApplicationPayload): ApplicationPayload
}) {
  function boundedPayload(value: ApplicationPayload, limit: number) {
    const copied = deps.copyPayload(value)
    const pending: Array<[unknown, number]> = [[copied, 0]]
    let nodes = 0
    while (pending.length) {
      const [item, depth] = pending.pop()!
      if (++nodes > 2048 || depth > 12) throw new ApplicationHostError('invalid_request')
      if (typeof item === 'string' && !validString(item)
          || typeof item === 'number' && (!Number.isFinite(item) || Math.abs(item) > Number.MAX_SAFE_INTEGER)) throw new ApplicationHostError('invalid_request')
      if (item !== null && typeof item === 'object') {
        if (Object.keys(item).some(k => !validString(k))) throw new ApplicationHostError('invalid_request')
        pending.push(...Object.values(item).map(v => [v, depth + 1] as [unknown, number]))
      }
    }
    if (asciiSize(copied) > limit) throw new ApplicationHostError('invalid_request')
    return copied
  }
  const root = `/ui-host/${encodeURIComponent(deps.entrypoint)}`
  const ui = Object.freeze({ host_version:1, entrypoint_id:deps.entrypoint, artifact_sha256:deps.artifact,
    ...(deps.build === undefined ? {} : { built_ui_sha256:deps.build }) })
  const query = new URLSearchParams({ artifact_sha256:deps.artifact,
    ...(deps.build === undefined ? {} : { built_ui_sha256:deps.build }) })
  const identifier = (value: string) => { if (typeof value !== 'string' || !hex.test(value)) throw new ApplicationHostError('invalid_request') }
  async function getInfo() { deps.live(); return readActorAccess(await deps.request(`${root}/access?${query}`), deps) }
  async function receipt(path: string, delegationId: string, data?: unknown) {
    deps.live(); identifier(delegationId)
    if (deps.audience !== 'operator') throw new ApplicationHostError('access_denied')
    try { return readDelegation(await deps.request(path, data), deps, delegationId, p => boundedPayload(p, 32768)) }
    catch (error) {
      if (data !== undefined && error instanceof ApplicationHostError && error.code === 'unavailable') throw new ApplicationHostError('unconfirmed')
      throw error
    }
  }
  return Object.freeze({
    access: Object.freeze({ getInfo }),
    delegations: Object.freeze({
      async create(operationId: string, payload: ApplicationPayload, requestId: string, ttlSeconds = 60) {
        deps.live(); identifier(requestId)
        if (!id.test(operationId) || !Number.isInteger(ttlSeconds) || ttlSeconds < 5 || ttlSeconds > 300) throw new ApplicationHostError('invalid_request')
        const input = boundedPayload(payload, 16384)
        const access = await getInfo()
        if (deps.audience !== 'operator' || !access.delegated_operation_ids.includes(operationId)) throw new ApplicationHostError('access_denied')
        const value = await receipt(`${root}/delegations`, requestId,
          { request_id:requestId, operation_id:operationId, payload:input, ttl_seconds:ttlSeconds, ui_context:ui })
        if (value.operation_id !== operationId || value.initiator.user_id !== access.actor.user_id || value.initiator.subject_id !== access.actor.subject_id) throw new ApplicationHostError('unconfirmed')
        return value
      },
      async lookup(delegationId: string) {
        identifier(delegationId)
        const access = await getInfo()
        const value = await receipt(`/delegations/${encodeURIComponent(delegationId)}`, delegationId)
        if (value.initiator.user_id !== access.actor.user_id || value.initiator.subject_id !== access.actor.subject_id) invalid()
        return value
      },
      async cancel(delegationId: string) {
        identifier(delegationId)
        const access = await getInfo()
        const value = await receipt(`/delegations/${encodeURIComponent(delegationId)}/cancel`, delegationId, {})
        if (value.initiator.user_id !== access.actor.user_id || value.initiator.subject_id !== access.actor.subject_id) throw new ApplicationHostError('unconfirmed')
        return value
      },
    }),
  })
}
