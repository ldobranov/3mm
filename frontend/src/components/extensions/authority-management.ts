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
  resources: { commands: unknown[]; connectors: unknown[]; events?: unknown[]; publications?: unknown[]; private_files?: AuthorityPrivateFileResource[] }
  isolation_proven: false
  historical?: boolean
  replayed?: boolean
}
export interface AuthorityPrivateFileResource {
  declaration: {
    file_contract_version: 1; namespace: 'private_files'; mode: 'read' | 'read_write'
    max_file_bytes: number; max_total_bytes: number; max_files: number
  }
  owner: { core_installation_id: string; application_installation_id: string; incarnation: string; module_id: string }
  package_artifact_sha256: string
  operation: 'read' | 'write'
}
export type Decision = 'approve' | 'deny' | 'apply'
const id = (value: unknown): value is string => typeof value === 'string' && value.length === 32 && /^[0-9a-f]{32}$/.test(value)
const digest = (value: unknown): value is string => typeof value === 'string' && value.length === 64 && /^[0-9a-f]{64}$/.test(value)
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const scopes = (value: unknown): value is string[] => Array.isArray(value) && value.length <= 128
  && value.every(item => typeof item === 'string' && item.trim() === item && /^(?:(?:command|connector|event|publication):[a-z][a-z0-9_]{0,95}|storage:private_files_(?:read|write))$/.test(item))
  && new Set(value).size === value.length

function privateFilesMatch(resources: Record<string, unknown>, selected: string[], status: AuthorityStatus, moduleId?: string): boolean {
  const files = (resources.private_files || []) as unknown[]
  const keys: string[] = []
  let binding: string | undefined
  const exact = (value: Record<string, unknown>, fields: string[]) => Object.keys(value).length === fields.length && fields.every(key => key in value)
  const identity = (value: unknown) => typeof value === 'string' && value.trim() === value && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/.test(value)
  const bounded = (value: unknown, maximum: number) => Number.isSafeInteger(value) && Number(value) >= 1 && Number(value) <= maximum
  for (const item of files) {
    if (!object(item) || !exact(item, ['declaration', 'owner', 'package_artifact_sha256', 'operation'])
      || !object(item.declaration) || !object(item.owner)) return false
    const declaration = item.declaration, owner = item.owner
    if (!exact(declaration, ['file_contract_version', 'namespace', 'mode', 'max_file_bytes', 'max_total_bytes', 'max_files'])
      || declaration.file_contract_version !== 1 || declaration.namespace !== 'private_files'
      || !['read', 'read_write'].includes(String(declaration.mode))
      || !bounded(declaration.max_file_bytes, 1048576) || !bounded(declaration.max_total_bytes, 67108864)
      || !bounded(declaration.max_files, 1024) || Number(declaration.max_file_bytes) > Number(declaration.max_total_bytes)
      || !exact(owner, ['core_installation_id', 'application_installation_id', 'incarnation', 'module_id'])
      || !identity(owner.core_installation_id) || !identity(owner.incarnation)
      || owner.application_installation_id !== String(status.installation_id)
      || typeof owner.module_id !== 'string' || owner.module_id.trim() !== owner.module_id || owner.module_id.length > 160 || !/^[a-z0-9]+(?:[.-][a-z0-9]+)+$/.test(owner.module_id)
      || moduleId !== undefined && owner.module_id !== moduleId
      || item.package_artifact_sha256 !== status.artifact_sha256
      || !['read', 'write'].includes(String(item.operation)) || item.operation === 'write' && declaration.mode !== 'read_write') return false
    const currentBinding = JSON.stringify([owner.core_installation_id, owner.application_installation_id, owner.incarnation, owner.module_id,
      declaration.file_contract_version, declaration.namespace, declaration.mode, declaration.max_file_bytes, declaration.max_total_bytes, declaration.max_files])
    if (binding !== undefined && binding !== currentBinding) return false
    binding = currentBinding
    keys.push(`storage:private_files_${item.operation}`)
  }
  const expected = selected.filter(key => key.startsWith('storage:'))
  return new Set(keys).size === keys.length && keys.length === expected.length && keys.every(key => expected.includes(key))
    && (!files.length || keys.includes('storage:private_files_read')
      && ((files[0] as AuthorityPrivateFileResource).declaration.mode === 'read' ? keys.length === 1 : keys.length === 2))
}

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

export function readAuthorityPlan(value: unknown, status: AuthorityStatus, moduleId?: string): AuthorityPlan {
  if (!object(value) || !id(value.plan_id) || !id(value.revision) || !digest(value.fingerprint)
    || value.state !== 'review_required' || value.artifact_sha256 !== status.artifact_sha256
    || value.isolation_proven !== false || !scopes(value.scopes)
    || value.scopes.length !== status.scopes.length || value.scopes.some(scope => !status.scopes.includes(scope))
    || !Number.isInteger(value.expires_in_seconds) || Number(value.expires_in_seconds) <= 0 || Number(value.expires_in_seconds) > 900
    || !object(value.resources) || !Array.isArray(value.resources.commands) || value.resources.commands.length > 64
    || !Array.isArray(value.resources.connectors) || value.resources.connectors.length > 32
    || !(value.resources.events === undefined || Array.isArray(value.resources.events) && value.resources.events.length <= 32)
    || !(value.resources.publications === undefined || Array.isArray(value.resources.publications) && value.resources.publications.length <= 32)
    || !(value.resources.private_files === undefined || Array.isArray(value.resources.private_files) && value.resources.private_files.length <= 2)
    || Object.keys(value.resources).some(key => !['commands', 'connectors', 'events', 'publications', 'private_files'].includes(key))
    || value.resources.commands.length + value.resources.connectors.length + ((value.resources.events as unknown[] | undefined)?.length || 0)
      + ((value.resources.publications as unknown[] | undefined)?.length || 0) + ((value.resources.private_files as unknown[] | undefined)?.length || 0) !== value.scopes.length
    || !resourceScopesMatch(value.resources, value.scopes)
    || !privateFilesMatch(value.resources, value.scopes, status, moduleId)
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
