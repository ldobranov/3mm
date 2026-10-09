// Admin control DTOs, not a public application SDK or native-trust issuer.
export interface AuthorityStatus {
  installation_id: number
  mode: 'compatibility' | 'review_required' | 'enforced'
  installation_status: string
  installation_enabled: boolean
  artifact_sha256: string
  scopes: string[]
  native_reviews: Array<{ native_review_id: string; revision: string }>
  grant_record_revision: string | null
  grant_state: 'active' | 'revoked' | 'unavailable' | null
  grant_effective: boolean
  isolation_proven: false
}
export interface AuthorityPlan {
  plan_id: string
  revision: string
  fingerprint: string
  state: 'review_required' | 'approved_pending_apply' | 'applied' | 'denied'
  scopes: string[]
  artifact_sha256: string
  expires_in_seconds: number
  resources: { commands: unknown[]; connectors: unknown[]; events?: unknown[]; publications?: unknown[] }
  isolation_proven: false
  historical?: boolean
  replayed?: boolean
}
export type Decision = 'approve' | 'deny' | 'apply'
const id = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value)
const digest = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value)
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const scopes = (value: unknown): value is string[] => Array.isArray(value) && value.length <= 128
  && value.every(item => typeof item === 'string' && /^(command|connector|event|publication):[a-z][a-z0-9_]{0,95}$/.test(item))
  && new Set(value).size === value.length

function resourceScopesMatch(resources: Record<string, unknown>, selected: string[]): boolean {
  const keys: string[] = []
  for (const kind of ['commands', 'connectors', 'events', 'publications']) {
    for (const resource of (resources[kind] || []) as unknown[]) {
      if (!object(resource) || !object(resource.declaration)) return false
      const key = kind === 'commands' ? `command:${resource.declaration.binding_id}` : kind === 'events'
        ? `event:${resource.declaration.subscription_id}` : kind === 'publications'
          ? `publication:${resource.declaration.publication_id}` : `connector:${resource.declaration.connector_id}`
      if (!selected.includes(key)) return false
      if (kind === 'commands' && (typeof resource.target_device_id !== 'string' || !/^dev_[a-f0-9]{32}$/.test(resource.target_device_id))) return false
      if (kind === 'connectors' && (!object(resource.stored) || typeof resource.stored.destination_origin !== 'string')) return false
      if (kind === 'events' && (typeof resource.source_device_id !== 'string' || !/^dev_[a-f0-9]{32}$/.test(resource.source_device_id)
        || !object(resource.handler) || resource.handler.operation_id !== resource.declaration.handler_operation_id
        || resource.handler.kind !== 'command' || resource.handler.idempotency !== 'required'
        || !Array.isArray(resource.handler.audiences) || resource.handler.audiences.length !== 1 || resource.handler.audiences[0] !== 'internal'
        || typeof resource.declaration.event_type !== 'string' || typeof resource.declaration.capability_id !== 'string'
        || resource.declaration.acknowledgement !== 'after_commit' || !Number.isInteger(resource.declaration.max_backlog)
        || Number(resource.declaration.max_backlog) < 1 || Number(resource.declaration.max_backlog) > 100000)) return false
      if (kind === 'publications' && (!object(resource.operation)
        || resource.operation.operation_id !== resource.declaration.operation_id
        || !['command', 'job'].includes(String(resource.operation.kind)) || resource.operation.idempotency !== 'required'
        || !digest(resource.service_artifact_sha256)
        || typeof resource.declaration.event_type !== 'string' || resource.declaration.event_type.startsWith('core.')
        || !Array.isArray(resource.operation.emitted_events) || !resource.operation.emitted_events.includes(resource.declaration.event_type)
        || !object(resource.declaration.payload_schema) || resource.declaration.payload_schema.type !== 'object'
        || resource.declaration.payload_schema.additionalProperties !== false
        || !Number.isInteger(resource.declaration.max_payload_bytes) || Number(resource.declaration.max_payload_bytes) < 1
        || Number(resource.declaration.max_payload_bytes) > 61440)) return false
      keys.push(key)
    }
  }
  return new Set(keys).size === keys.length
}

export function readAuthorityStatus(value: unknown): AuthorityStatus {
  if (!object(value) || !['compatibility', 'review_required', 'enforced'].includes(String(value.mode))
    || !Number.isSafeInteger(value.installation_id) || Number(value.installation_id) <= 0
    || typeof value.installation_status !== 'string' || typeof value.installation_enabled !== 'boolean'
    || !digest(value.artifact_sha256) || !scopes(value.scopes) || value.isolation_proven !== false
    || typeof value.grant_effective !== 'boolean'
    || !(value.grant_record_revision === null || id(value.grant_record_revision))
    || !(value.grant_state === null || ['active', 'revoked', 'unavailable'].includes(String(value.grant_state)))
    || !Array.isArray(value.native_reviews) || value.native_reviews.length > 32
    || !value.native_reviews.every(item => object(item) && id(item.native_review_id) && id(item.revision))) {
    throw new Error('Unsupported authority status')
  }
  return value as unknown as AuthorityStatus
}

export function readAuthorityPlan(value: unknown, status: AuthorityStatus): AuthorityPlan {
  if (!object(value) || !id(value.plan_id) || !id(value.revision) || !digest(value.fingerprint)
    || value.state !== 'review_required' || value.artifact_sha256 !== status.artifact_sha256
    || value.isolation_proven !== false || !scopes(value.scopes)
    || value.scopes.length !== status.scopes.length || value.scopes.some(scope => !status.scopes.includes(scope))
    || !Number.isInteger(value.expires_in_seconds) || Number(value.expires_in_seconds) <= 0 || Number(value.expires_in_seconds) > 900
    || !object(value.resources) || !Array.isArray(value.resources.commands) || value.resources.commands.length > 64
    || !Array.isArray(value.resources.connectors) || value.resources.connectors.length > 32
    || !(value.resources.events === undefined || Array.isArray(value.resources.events) && value.resources.events.length <= 32)
    || !(value.resources.publications === undefined || Array.isArray(value.resources.publications) && value.resources.publications.length <= 32)
    || value.resources.commands.length + value.resources.connectors.length + ((value.resources.events as unknown[] | undefined)?.length || 0)
      + ((value.resources.publications as unknown[] | undefined)?.length || 0) !== value.scopes.length
    || !resourceScopesMatch(value.resources, value.scopes)
    || value.historical === true || value.replayed === true) {
    throw new Error('Unsupported authority review')
  }
  return value as unknown as AuthorityPlan
}

export function readAuthorityDecision(value: unknown, plan: AuthorityPlan, decision: Decision): AuthorityPlan {
  const expected = { approve: 'approved_pending_apply', deny: 'denied', apply: 'applied' }[decision]
  if (!object(value) || value.plan_id !== plan.plan_id || value.fingerprint !== plan.fingerprint
    || !id(value.revision) || value.revision === plan.revision || value.state !== expected || value.historical === true || value.replayed === true) {
    throw new Error('Unsupported or historical authority decision')
  }
  return { ...plan, revision: value.revision, state: expected as AuthorityPlan['state'] }
}

export function authorityRequestId(): string {
  // No weak fallback and no persistent browser approval/token cache.
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')
}
