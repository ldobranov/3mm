// Admin control DTOs, not a public application SDK or native-trust issuer.
import { queriesMatch, type AuthorityQueryResource } from './authority-queries'
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
  review_available?: boolean
  review_blockers?: Array<'review_key_unavailable' | 'unsupported_authority'>
  runtime_blockers?: Array<'relational_runtime_unavailable' | 'peer_read_runtime_unavailable' | 'session_runtime_not_connected' | 'query_runtime_not_connected'>
}
export interface AuthorityPlan {
  plan_id: string
  revision: string
  fingerprint: string
  state: 'review_required' | 'approved_pending_apply' | 'applied' | 'denied'
  scopes: string[]
  artifact_sha256: string
  expires_in_seconds: number
  resources: { commands: unknown[]; connectors: unknown[]; events?: unknown[]; publications?: unknown[]; private_files?: AuthorityPrivateFileResource[]; relational?: AuthorityRelationalResource[]; checkpoints?: AuthorityCheckpointResource[]; identities?: AuthorityIdentityResource[]; status_projections?: AuthorityStatusResource[]; peer_reads?: AuthorityPeerReadResource[]; sessions?: AuthoritySessionResource[]; tasks?: AuthorityTaskResource[]; queries?: AuthorityQueryResource[] }
  isolation_proven: false
  historical?: boolean
  replayed?: boolean
}
export interface AuthorityPrivateFileResource {
  declaration: {
    file_contract_version: 1 | 2; namespace: 'private_files'; mode: 'read' | 'read_write'
    max_file_bytes: number; max_total_bytes: number; max_files: number
    max_uploads?: number; max_staging_bytes?: number; upload_ttl_seconds?: number
    public_links?: boolean; media_transforms?: boolean
  }
  owner: { core_installation_id: string; application_installation_id: string; incarnation: string; module_id: string }
  package_artifact_sha256: string
  operation: 'read' | 'write' | 'publish' | 'transform'
}
export interface AuthorityRelationalResource {
  declaration: {
    contract_version: 1; mode: 'read' | 'read_write'; limit_class: 'cooperative_v1'
    max_database_bytes: number; auxiliary_pause_bytes: number; max_statement_bytes: number
    max_value_bytes: number; max_result_bytes: number; max_result_rows: number
    max_transaction_ms: number; max_busy_ms: number
  }
  owner: AuthorityPrivateFileResource['owner']
  package_artifact_sha256: string
  service_artifact_sha256: string
  schema_revision: string
  migration_entrypoint: string
  resource_profile: 'owned_sqlite_request_v1'
  operation: 'read' | 'write'
}
export interface AuthorityCheckpointResource {
  declaration: { contract_version: 1; checkpoint_id: string; mode: 'read' | 'read_write'; max_value_bytes: number }
  owner: AuthorityPrivateFileResource['owner']
  package_artifact_sha256: string
  operation: 'read' | 'write'
}
export interface AuthorityIdentityResource {
  owner: AuthorityPrivateFileResource['owner']
  package_artifact_sha256: string
  operation: 'installation.identity.read'
  identity: {
    identity_version: 1; installation_id: string; algorithm: 'ed25519'; key_id: string
    public_key: string; key_generation: 1; created_at: string
  }
}
export interface AuthorityStatusResource {
  owner: AuthorityPrivateFileResource['owner']
  package_artifact_sha256: string
  operation: 'installation.status.read'
  link_id: string
  application_instance_id: string
  sender_identity: AuthorityIdentityResource['identity']
  receiver_identity: AuthorityIdentityResource['identity']
  origin: string
  target_module_id: string
  consent_revision: number
  consent: { consent_version: 1; summary_fields: string[]; node_ids: string[]; node_fields: string[] }
}
export interface AuthorityPeerReadResource {
  declaration: { contract_version: 1; binding_id: string; direction: 'outbound'; peer_id_config_key: string; operations: ['read'] }
  owner: AuthorityPrivateFileResource['owner']
  package_artifact_sha256: string
  service_artifact_sha256: string
  application_instance_id: string
  peer_id: string
  peer_version: 1 | 2
  sender_identity: AuthorityIdentityResource['identity']
  receiver_identity: AuthorityIdentityResource['identity']
  origin: string
  target_module_id: string
  consent_revision: number
  consent: AuthorityStatusResource['consent']
  enrollment_metadata: null | { metadata_version: 2; application_intent: string; consent_revision: number; consent: AuthorityStatusResource['consent']; metadata_hash: string }
}
export type Decision = 'approve' | 'deny' | 'apply'
export interface AuthorityTaskResource {
  declaration: { task_id: string; handler_operation_id: string; profile: 'bounded_result_once_v1' | 'bounded_task_v1';
    max_runtime_seconds: number; max_delay_seconds: number; max_pending: number }
  operation: { operation_id: string; kind: 'task'; audiences: ['internal']; required_permission: null;
    idempotency: 'required'; input_schema: Record<string, unknown>; output_schema: Record<string, unknown>;
    timeout_seconds: number; audit: 'metadata' | 'redacted'; emitted_events: [] }
  owner: AuthorityPrivateFileResource['owner']
  package_artifact_sha256: string
}
export interface AuthoritySessionResource {
  declaration: {
    contract_version: 1; binding_id: string; target_device_config_key: string
    provider_id: string; capability_id: string; access_mode: 'read' | 'write'
    control_actions: string[]; required_permission: string; options: Record<string, unknown>
  }
  owner: AuthorityPrivateFileResource['owner']
  package_artifact_sha256: string
  target_device_id: string
  control_revision: string
  provider_version: string
  contract: { contract_version: 1; access_modes: Array<'read' | 'write'>; control_actions: string[] }
}
const id = (value: unknown): value is string => typeof value === 'string' && value.length === 32 && /^[0-9a-f]{32}$/.test(value)
const digest = (value: unknown): value is string => typeof value === 'string' && value.length === 64 && /^[0-9a-f]{64}$/.test(value)
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const scopes = (value: unknown): value is string[] => Array.isArray(value)
  && value.length <= (value.some(item => item === 'storage:private_files_publish' || item === 'storage:private_files_transform') ? 2 : 0)
    + (value.some(item => typeof item === 'string' && item.startsWith('task:')) ? 72
    : value.some(item => typeof item === 'string' && item.startsWith('session:')) ? 293
    : value.some(item => typeof item === 'string' && item.startsWith('peer:')) ? 261
    : value.some(item => typeof item === 'string' && item.startsWith('status:')) ? 229 : 197)
  && value.every(item => typeof item === 'string' && item.trim() === item && /^(?:(?:command|connector|event|publication|task):[a-z][a-z0-9_]{0,95}|storage:(?:private_files_(?:read|write|publish|transform)|relational_(?:read|write))|checkpoint:[a-z][a-z0-9_]{0,95}:(?:read|write)|platform:installation\.identity\.read|status:peer_[0-9a-f]{32}:read|(?:peer|query):[a-z][a-z0-9_]{0,95}:read|session:[a-z][a-z0-9_]{0,95}:open)$/.test(item))
  && (!value.some(item => item.startsWith('query:')) || value.length <= 16 && value.every(item => /^query:/.test(item)))
  && (!value.some(item => item.startsWith('task:')) || value.every(item => /^(?:task|command):/.test(item)))
  && new Set(value).size === value.length
const exact = (value: Record<string, unknown>, fields: string[]) => Object.keys(value).length === fields.length && fields.every(key => key in value)
const identity = (value: unknown) => typeof value === 'string' && value.trim() === value && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/.test(value)
const bounded = (value: unknown, maximum: number, minimum = 1) => Number.isSafeInteger(value) && Number(value) >= minimum && Number(value) <= maximum
function ownerMatches(owner: Record<string, unknown>, status: AuthorityStatus, moduleId?: string): boolean {
  return exact(owner, ['core_installation_id', 'application_installation_id', 'incarnation', 'module_id'])
    && identity(owner.core_installation_id) && identity(owner.incarnation)
    && owner.application_installation_id === String(status.installation_id)
    && typeof owner.module_id === 'string' && owner.module_id.trim() === owner.module_id && owner.module_id.length <= 160
    && /^[a-z0-9]+(?:[.-][a-z0-9]+)+$/.test(owner.module_id) && (moduleId === undefined || owner.module_id === moduleId)
}
const ownerBinding = (owner: Record<string, unknown>) => JSON.stringify([
  owner.core_installation_id, owner.application_installation_id, owner.incarnation, owner.module_id,
])

function privateFilesMatch(resources: Record<string, unknown>, selected: string[], status: AuthorityStatus, moduleId?: string): boolean {
  const files = (resources.private_files || []) as unknown[]
  const keys: string[] = []
  let binding: string | undefined
  for (const item of files) {
    if (!object(item) || !exact(item, ['declaration', 'owner', 'package_artifact_sha256', 'operation'])
      || !object(item.declaration) || !object(item.owner)) return false
    const declaration = item.declaration, owner = item.owner
    const streaming = declaration.file_contract_version === 2
    const fields = ['file_contract_version', 'namespace', 'mode', 'max_file_bytes', 'max_total_bytes', 'max_files',
      ...(streaming ? ['max_uploads', 'max_staging_bytes', 'upload_ttl_seconds', 'public_links', 'media_transforms'] : [])]
    const operations = ['read', ...(declaration.mode === 'read_write' ? ['write'] : []),
      ...(streaming && declaration.public_links ? ['publish'] : []), ...(streaming && declaration.media_transforms ? ['transform'] : [])]
    if (!exact(declaration, fields)
      || (declaration.file_contract_version !== 1 && declaration.file_contract_version !== 2) || declaration.namespace !== 'private_files'
      || !['read', 'read_write'].includes(String(declaration.mode))
      || !bounded(declaration.max_file_bytes, streaming ? 1073741824 : 1048576) || !bounded(declaration.max_total_bytes, streaming ? 4294967296 : 67108864)
      || !bounded(declaration.max_files, streaming ? 4096 : 1024) || Number(declaration.max_file_bytes) > Number(declaration.max_total_bytes)
      || streaming && (!bounded(declaration.max_uploads, 16) || !bounded(declaration.max_staging_bytes, 2147483648)
        || !bounded(declaration.upload_ttl_seconds, 86400, 60) || Number(declaration.max_file_bytes) > Number(declaration.max_staging_bytes)
        || typeof declaration.public_links !== 'boolean' || typeof declaration.media_transforms !== 'boolean'
        || declaration.mode === 'read' && (declaration.public_links || declaration.media_transforms))
      || !ownerMatches(owner, status, moduleId)
      || item.package_artifact_sha256 !== status.artifact_sha256
      || !operations.includes(String(item.operation))) return false
    const currentBinding = JSON.stringify([owner.core_installation_id, owner.application_installation_id, owner.incarnation, owner.module_id,
      ...fields.map(field => declaration[field])])
    if (binding !== undefined && binding !== currentBinding) return false
    binding = currentBinding
    keys.push(`storage:private_files_${item.operation}`)
  }
  const expected = selected.filter(key => key.startsWith('storage:private_files_'))
  return new Set(keys).size === keys.length && keys.length === expected.length && keys.every(key => expected.includes(key))
    && (!files.length || keys.includes('storage:private_files_read')
      && (() => { const d = (files[0] as AuthorityPrivateFileResource).declaration
        return keys.length === 1 + (d.mode === 'read_write' ? 1 : 0) + (d.public_links ? 1 : 0) + (d.media_transforms ? 1 : 0) })())
}

function relationalMatch(resources: Record<string, unknown>, selected: string[], status: AuthorityStatus, moduleId?: string): boolean {
  const relational = (resources.relational || []) as unknown[]
  const keys: string[] = []
  let binding: string | undefined
  // Both storage families belong to the same current application principal.
  const file = (resources.private_files as AuthorityPrivateFileResource[] | undefined)?.[0]
  for (const item of relational) {
    if (!object(item) || !exact(item, ['declaration', 'owner', 'package_artifact_sha256', 'service_artifact_sha256',
      'schema_revision', 'migration_entrypoint', 'resource_profile', 'operation'])
      || !object(item.declaration) || !object(item.owner)) return false
    const declaration = item.declaration, owner = item.owner
    const fields = ['contract_version', 'mode', 'limit_class', 'max_database_bytes', 'auxiliary_pause_bytes',
      'max_statement_bytes', 'max_value_bytes', 'max_result_bytes', 'max_result_rows', 'max_transaction_ms', 'max_busy_ms']
    if (!exact(declaration, fields) || declaration.contract_version !== 1 || declaration.limit_class !== 'cooperative_v1'
      || declaration.mode !== 'read' && declaration.mode !== 'read_write'
      || !bounded(declaration.max_database_bytes, 268435456, 65536) || !bounded(declaration.auxiliary_pause_bytes, 67108864, 65536)
      || !bounded(declaration.max_statement_bytes, 65536) || !bounded(declaration.max_value_bytes, 1048576)
      || !bounded(declaration.max_result_bytes, 1048576) || !bounded(declaration.max_result_rows, 1000)
      || !bounded(declaration.max_transaction_ms, 30000, 100) || !bounded(declaration.max_busy_ms, 5000, 0)
      || Number(declaration.max_value_bytes) > Number(declaration.max_result_bytes)
      || Number(declaration.max_value_bytes) > Number(declaration.max_database_bytes)
      || Number(declaration.max_busy_ms) > Number(declaration.max_transaction_ms)
      || !ownerMatches(owner, status, moduleId) || file && ownerBinding(owner) !== ownerBinding(file.owner)
      || item.package_artifact_sha256 !== status.artifact_sha256 || !digest(item.service_artifact_sha256)
      || typeof item.schema_revision !== 'string' || item.schema_revision.trim() !== item.schema_revision
      || !/^[a-z0-9][a-z0-9_.-]{0,63}$/.test(item.schema_revision)
      || typeof item.migration_entrypoint !== 'string' || item.migration_entrypoint.trim() !== item.migration_entrypoint
      || item.migration_entrypoint.length > 240 || !/^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$/.test(item.migration_entrypoint)
      || item.resource_profile !== 'owned_sqlite_request_v1' || item.operation !== 'read' && item.operation !== 'write'
      || item.operation === 'write' && declaration.mode !== 'read_write') return false
    const currentBinding = JSON.stringify([ownerBinding(owner), ...fields.map(field => declaration[field]),
      item.package_artifact_sha256, item.service_artifact_sha256, item.schema_revision, item.migration_entrypoint, item.resource_profile])
    if (binding !== undefined && binding !== currentBinding) return false
    binding = currentBinding
    keys.push(`storage:relational_${item.operation}`)
  }
  const expected = selected.filter(key => key.startsWith('storage:relational_'))
  return new Set(keys).size === keys.length && keys.length === expected.length && keys.every(key => expected.includes(key))
    && (!relational.length || keys.includes('storage:relational_read')
      && ((relational[0] as AuthorityRelationalResource).declaration.mode === 'read' ? keys.length === 1 : keys.length === 2))
}

function checkpointsMatch(resources: Record<string, unknown>, selected: string[], status: AuthorityStatus, moduleId?: string): boolean {
  const checkpoints = (resources.checkpoints || []) as unknown[]
  const keys: string[] = []
  const declarations = new Map<string, { binding: string; mode: 'read' | 'read_write'; operations: Set<string> }>()
  const storage = (resources.private_files as AuthorityPrivateFileResource[] | undefined)?.[0]
    || (resources.relational as AuthorityRelationalResource[] | undefined)?.[0]
  let owner: string | undefined = storage ? ownerBinding(storage.owner) : undefined
  for (const item of checkpoints) {
    if (!object(item) || !exact(item, ['declaration', 'owner', 'package_artifact_sha256', 'operation'])
      || !object(item.declaration) || !object(item.owner)) return false
    const declaration = item.declaration
    if (!exact(declaration, ['contract_version', 'checkpoint_id', 'mode', 'max_value_bytes'])
      || declaration.contract_version !== 1 || typeof declaration.checkpoint_id !== 'string'
      || declaration.checkpoint_id.trim() !== declaration.checkpoint_id || !/^[a-z][a-z0-9_]{0,95}$/.test(declaration.checkpoint_id)
      || declaration.mode !== 'read' && declaration.mode !== 'read_write' || !bounded(declaration.max_value_bytes, 262144)
      || !ownerMatches(item.owner, status, moduleId) || item.package_artifact_sha256 !== status.artifact_sha256
      || item.operation !== 'read' && item.operation !== 'write' || item.operation === 'write' && declaration.mode !== 'read_write') return false
    const currentOwner = ownerBinding(item.owner)
    if (owner !== undefined && owner !== currentOwner) return false
    owner = currentOwner
    const binding = JSON.stringify([declaration.contract_version, declaration.mode, declaration.max_value_bytes])
    const previous = declarations.get(declaration.checkpoint_id)
    if (previous && (previous.binding !== binding || previous.operations.has(item.operation))) return false
    const current = previous || { binding, mode: declaration.mode, operations: new Set<string>() }
    current.operations.add(item.operation)
    declarations.set(declaration.checkpoint_id, current)
    keys.push(`checkpoint:${declaration.checkpoint_id}:${item.operation}`)
  }
  const expected = selected.filter(key => key.startsWith('checkpoint:'))
  return declarations.size <= 32 && keys.length === expected.length && keys.every(key => expected.includes(key))
    && [...declarations.values()].every(item => item.operations.has('read') && item.operations.size === (item.mode === 'read' ? 1 : 2))
}

function utcIdentityDate(value: unknown): boolean {
  if (typeof value !== 'string' || value.trim() !== value || value.length > 32) return false
  const parts = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(?:Z|\+00:00)$/.exec(value)
  if (!parts || Number(parts[1]) === 0) return false
  const date = new Date(value)
  return Number.isFinite(date.getTime()) && [date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate(),
    date.getUTCHours(), date.getUTCMinutes(), date.getUTCSeconds()].every((part, index) => part === Number(parts[index + 1]))
}

function publicIdentityMatches(value: unknown, installationId?: unknown): value is AuthorityIdentityResource['identity'] {
  // Presentation only; Core verifies the key digest. No browser possession or
  // trust proof is inferred from a key's shape or from HTTPS origin syntax.
  return object(value) && exact(value, ['identity_version', 'installation_id', 'algorithm', 'key_id', 'public_key', 'key_generation', 'created_at'])
    && value.identity_version === 1 && value.key_generation === 1 && value.algorithm === 'ed25519'
    && typeof value.installation_id === 'string' && value.installation_id.length === 37 && /^inst_[a-f0-9]{32}$/.test(value.installation_id)
    && (installationId === undefined || value.installation_id === installationId) && digest(value.key_id)
    && typeof value.public_key === 'string' && value.public_key.length === 44
    && /^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$/.test(value.public_key) && utcIdentityDate(value.created_at)
}
const publicIdentityBinding = (value: AuthorityIdentityResource['identity']) => JSON.stringify([
  value.identity_version, value.installation_id, value.algorithm, value.key_id, value.public_key, value.key_generation, value.created_at,
])

function identitiesMatch(resources: Record<string, unknown>, selected: string[], status: AuthorityStatus, moduleId?: string): boolean {
  const identities = (resources.identities || []) as unknown[]
  const expected = selected.filter(key => key.startsWith('platform:'))
  if (identities.length !== expected.length || identities.length > 1) return false
  const bound = (resources.private_files as AuthorityPrivateFileResource[] | undefined)?.[0]
    || (resources.relational as AuthorityRelationalResource[] | undefined)?.[0]
    || (resources.checkpoints as AuthorityCheckpointResource[] | undefined)?.[0]
  for (const item of identities) {
    if (!object(item) || !exact(item, ['owner', 'package_artifact_sha256', 'operation', 'identity'])
      || !object(item.owner) || !object(item.identity) || !ownerMatches(item.owner, status, moduleId)
      || bound && ownerBinding(item.owner) !== ownerBinding(bound.owner)
      || item.package_artifact_sha256 !== status.artifact_sha256 || item.operation !== 'installation.identity.read'
      || !expected.includes('platform:installation.identity.read')) return false
    if (!publicIdentityMatches(item.identity, item.owner.core_installation_id)) return false
  }
  return true
}

function statusProjectionsMatch(resources: Record<string, unknown>, selected: string[], status: AuthorityStatus, moduleId?: string): boolean {
  const projections = (resources.status_projections || []) as unknown[]
  const keys: string[] = []
  const bound = (resources.private_files as AuthorityPrivateFileResource[] | undefined)?.[0]
    || (resources.relational as AuthorityRelationalResource[] | undefined)?.[0]
    || (resources.checkpoints as AuthorityCheckpointResource[] | undefined)?.[0]
    || (resources.identities as AuthorityIdentityResource[] | undefined)?.[0]
  let owner = bound ? ownerBinding(bound.owner) : undefined
  let sender = (resources.identities as AuthorityIdentityResource[] | undefined)?.[0]?.identity
  let instance: string | undefined
  const summary = ['core_version', 'protocol_version', 'sdk_version']
  const nodeFields = ['display_name', 'role', 'protocol_version', 'agent_version', 'online', 'last_seen_at', 'architecture', 'memory_total_bytes', 'root_free_bytes']
  const selection = (value: unknown, maximum: number, accepts: (item: string) => boolean): value is string[] =>
    Array.isArray(value) && value.length <= maximum && value.every(item => typeof item === 'string' && accepts(item)) && new Set(value).size === value.length
  for (const item of projections) {
    if (!object(item) || !exact(item, ['owner', 'package_artifact_sha256', 'operation', 'link_id', 'application_instance_id',
      'sender_identity', 'receiver_identity', 'origin', 'target_module_id', 'consent_revision', 'consent'])
      || !object(item.owner) || !ownerMatches(item.owner, status, moduleId)
      || item.package_artifact_sha256 !== status.artifact_sha256 || item.operation !== 'installation.status.read'
      || typeof item.link_id !== 'string' || !/^peer_[a-f0-9]{32}$/.test(item.link_id)
      || typeof item.application_instance_id !== 'string' || !/^[a-f0-9]{24}$/.test(item.application_instance_id)
      || !publicIdentityMatches(item.sender_identity, item.owner.core_installation_id)
      || !publicIdentityMatches(item.receiver_identity) || item.receiver_identity.installation_id === item.owner.core_installation_id
      || typeof item.target_module_id !== 'string' || item.target_module_id.length > 160 || !/^[a-z0-9]+(?:[.-][a-z0-9]+)+$/.test(item.target_module_id)
      || !bounded(item.consent_revision, Number.MAX_SAFE_INTEGER) || typeof item.origin !== 'string' || item.origin.length > 255
      || !object(item.consent) || !exact(item.consent, ['consent_version', 'summary_fields', 'node_ids', 'node_fields'])
      || item.consent.consent_version !== 1 || !selection(item.consent.summary_fields, 3, value => summary.includes(value))
      || !selection(item.consent.node_ids, 64, value => /^dev_[a-f0-9]{32}$/.test(value))
      || !selection(item.consent.node_fields, 9, value => nodeFields.includes(value))
      || !!item.consent.node_ids.length !== !!item.consent.node_fields.length) return false
    try {
      const url = new URL(item.origin)
      if (url.protocol !== 'https:' || url.origin !== item.origin || url.hostname.length > 253 || url.port !== '' && Number(url.port) < 1
        || !url.hostname.startsWith('[') && !url.hostname.split('.').every(part => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(part))) return false
    } catch { return false }
    const currentOwner = ownerBinding(item.owner)
    if (owner !== undefined && owner !== currentOwner || instance !== undefined && instance !== item.application_instance_id
      || sender && publicIdentityBinding(sender) !== publicIdentityBinding(item.sender_identity)) return false
    owner = currentOwner; instance = item.application_instance_id; sender = item.sender_identity
    keys.push(`status:${item.link_id}:read`)
  }
  const expected = selected.filter(key => key.startsWith('status:'))
  return keys.length === expected.length && new Set(keys).size === keys.length && keys.every(key => expected.includes(key))
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

const consentBinding = (value: AuthorityStatusResource['consent']) => JSON.stringify([
  value.consent_version, [...value.summary_fields].sort(), [...value.node_ids].sort(), [...value.node_fields].sort(),
])
function peerConsent(value: unknown): value is AuthorityStatusResource['consent'] {
  const selection = (items: unknown, maximum: number, accepts: (item: string) => boolean): items is string[] =>
    Array.isArray(items) && items.length <= maximum && items.every((item, index) => typeof item === 'string'
      && accepts(item) && (index === 0 || items[index - 1] < item))
  return object(value) && exact(value, ['consent_version', 'summary_fields', 'node_ids', 'node_fields'])
    && value.consent_version === 1
    && selection(value.summary_fields, 3, item => ['core_version', 'protocol_version', 'sdk_version'].includes(item))
    && selection(value.node_ids, 64, item => item.length === 36 && /^dev_[a-f0-9]{32}$/.test(item))
    && selection(value.node_fields, 9, item => ['display_name', 'role', 'protocol_version', 'agent_version', 'online',
      'last_seen_at', 'architecture', 'memory_total_bytes', 'root_free_bytes'].includes(item))
    && !!value.node_ids.length === !!value.node_fields.length
}
function peerReadsMatch(resources: Record<string, unknown>, status: AuthorityStatus, moduleId?: string): boolean {
  const peers = (resources.peer_reads || []) as unknown[]
  const expected = status.scopes.filter(key => key.startsWith('peer:'))
  if (peers.length !== expected.length || peers.length > 32 || peers.length && (resources.relational as unknown[] | undefined)?.length) return false
  const bound = (resources.private_files as AuthorityPrivateFileResource[] | undefined)?.[0]
    || (resources.checkpoints as AuthorityCheckpointResource[] | undefined)?.[0]
    || (resources.identities as AuthorityIdentityResource[] | undefined)?.[0]
    || (resources.status_projections as AuthorityStatusResource[] | undefined)?.[0]
  let owner = bound ? ownerBinding(bound.owner) : undefined
  let sender = (resources.identities as AuthorityIdentityResource[] | undefined)?.[0]?.identity
    || (resources.status_projections as AuthorityStatusResource[] | undefined)?.[0]?.sender_identity
  let instance = (resources.status_projections as AuthorityStatusResource[] | undefined)?.[0]?.application_instance_id
  let service: unknown = (resources.publications as Array<Record<string, unknown>> | undefined)?.[0]?.service_artifact_sha256
  const keys = new Set<string>(), references = new Set<string>(), links = new Set<string>()
  for (const item of peers) {
    if (!object(item) || !exact(item, ['declaration', 'owner', 'package_artifact_sha256', 'service_artifact_sha256',
      'application_instance_id', 'peer_id', 'peer_version', 'sender_identity', 'receiver_identity', 'origin',
      'target_module_id', 'consent_revision', 'consent', 'enrollment_metadata'])
      || !object(item.declaration) || !object(item.owner) || !ownerMatches(item.owner, status, moduleId)
      || !id(item.owner.incarnation) || item.package_artifact_sha256 !== status.artifact_sha256
      || !digest(item.service_artifact_sha256) || typeof item.application_instance_id !== 'string'
      || item.application_instance_id.length !== 24 || !/^[a-f0-9]{24}$/.test(item.application_instance_id)
      || typeof item.peer_id !== 'string' || item.peer_id.length !== 37 || !/^peer_[a-f0-9]{32}$/.test(item.peer_id)
      || item.peer_version !== 1 && item.peer_version !== 2
      || !publicIdentityMatches(item.sender_identity, item.owner.core_installation_id) || !publicIdentityMatches(item.receiver_identity)
      || item.receiver_identity.installation_id === item.owner.core_installation_id
      || !bounded(item.consent_revision, Number.MAX_SAFE_INTEGER) || !peerConsent(item.consent)
      || typeof item.target_module_id !== 'string' || item.target_module_id.trim() !== item.target_module_id
      || item.target_module_id.length > 160 || !/^[a-z0-9]+(?:[.-][a-z0-9]+)+$/.test(item.target_module_id)
      || typeof item.origin !== 'string' || item.origin.length > 255) return false
    const declaration = item.declaration
    if (!exact(declaration, ['contract_version', 'binding_id', 'direction', 'peer_id_config_key', 'operations'])
      || declaration.contract_version !== 1 || declaration.direction !== 'outbound'
      || typeof declaration.binding_id !== 'string' || declaration.binding_id.trim() !== declaration.binding_id || !/^[a-z][a-z0-9_]{0,95}$/.test(declaration.binding_id)
      || typeof declaration.peer_id_config_key !== 'string' || declaration.peer_id_config_key.trim() !== declaration.peer_id_config_key || !/^[A-Z][A-Z0-9_]{1,63}$/.test(declaration.peer_id_config_key)
      || !Array.isArray(declaration.operations) || declaration.operations.length !== 1 || declaration.operations[0] !== 'read') return false
    try {
      const url = new URL(item.origin)
      if (url.protocol !== 'https:' || url.origin !== item.origin || url.hostname.length > 253 || url.port !== '' && Number(url.port) < 1
        || !url.hostname.startsWith('[') && !url.hostname.split('.').every(part => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(part))) return false
    } catch { return false }
    const metadata = item.enrollment_metadata
    // Core verifies signed metadata and its hash. The UI only checks the exact
    // public shape and matching bounds; it never claims cryptographic trust.
    if (item.peer_version === 1 ? metadata !== null : !object(metadata)
      || !exact(metadata, ['metadata_version', 'application_intent', 'consent_revision', 'consent', 'metadata_hash'])
      || metadata.metadata_version !== 2 || typeof metadata.application_intent !== 'string'
      || metadata.application_intent.trim() !== metadata.application_intent || !/^[A-Za-z0-9_-]{1,256}$/.test(metadata.application_intent) || !digest(metadata.metadata_hash)
      || metadata.consent_revision !== item.consent_revision || !peerConsent(metadata.consent)
      || consentBinding(metadata.consent) !== consentBinding(item.consent)) return false
    const currentOwner = ownerBinding(item.owner), key = `peer:${declaration.binding_id}:read`
    if (owner !== undefined && owner !== currentOwner || sender && publicIdentityBinding(sender) !== publicIdentityBinding(item.sender_identity)
      || instance !== undefined && instance !== item.application_instance_id || service !== undefined && service !== item.service_artifact_sha256
      || !expected.includes(key) || keys.has(key) || references.has(declaration.peer_id_config_key) || links.has(item.peer_id)) return false
    owner = currentOwner; sender = item.sender_identity; instance = item.application_instance_id; service = item.service_artifact_sha256
    keys.add(key); references.add(declaration.peer_id_config_key); links.add(item.peer_id)
    for (const projection of (resources.status_projections || []) as AuthorityStatusResource[]) {
      if (ownerBinding(projection.owner) !== owner || publicIdentityBinding(projection.sender_identity) !== publicIdentityBinding(sender)
        || projection.application_instance_id !== instance || projection.link_id === item.peer_id
        && (publicIdentityBinding(projection.receiver_identity) !== publicIdentityBinding(item.receiver_identity)
          || projection.origin !== item.origin || projection.target_module_id !== item.target_module_id
          || projection.consent_revision !== item.consent_revision || consentBinding(projection.consent) !== consentBinding(item.consent))) return false
    }
  }
  return true
}

function sessionResourcesMatch(resources: Record<string, unknown>, status: AuthorityStatus, moduleId?: string): boolean {
  const sessions = (resources.sessions || []) as unknown[]
  const expected = status.scopes.filter(key => key.startsWith('session:'))
  if (sessions.length !== expected.length || sessions.length > 32) return false
  const owners = ['private_files', 'relational', 'checkpoints', 'identities', 'status_projections', 'peer_reads']
    .flatMap(key => (resources[key] || []) as Array<{ owner: Record<string, unknown> }>).map(item => ownerBinding(item.owner))
  const keys = new Set<string>()
  const controls = (value: unknown): value is string[] => Array.isArray(value) && value.length <= 16
    && value.every(item => typeof item === 'string' && item.length <= 64 && /^[a-z][a-z0-9_.-]{0,63}$/.test(item))
    && new Set(value).size === value.length
  for (const item of sessions) {
    if (!object(item) || !exact(item, ['declaration', 'owner', 'package_artifact_sha256', 'target_device_id', 'control_revision', 'provider_version', 'contract'])
      || !object(item.owner) || !ownerMatches(item.owner, status, moduleId) || !id(item.owner.incarnation)
      || item.package_artifact_sha256 !== status.artifact_sha256 || !digest(item.control_revision)
      || typeof item.target_device_id !== 'string' || item.target_device_id.length !== 36 || !/^dev_[a-f0-9]{32}$/.test(item.target_device_id)
      || typeof item.provider_version !== 'string' || !item.provider_version.length || item.provider_version.length > 64
      || !object(item.declaration) || !object(item.contract)) return false
    const declaration = item.declaration, contract = item.contract
    if (!exact(declaration, ['contract_version', 'binding_id', 'target_device_config_key', 'provider_id', 'capability_id', 'access_mode', 'control_actions', 'required_permission', 'options'])
      || declaration.contract_version !== 1 || typeof declaration.binding_id !== 'string' || !/^[a-z][a-z0-9_]{0,95}$/.test(declaration.binding_id)
      || typeof declaration.target_device_config_key !== 'string' || !/^[A-Z][A-Z0-9_]{1,63}$/.test(declaration.target_device_config_key)
      || typeof declaration.provider_id !== 'string' || declaration.provider_id.length > 160 || !/^[a-z0-9]+(?:[.-][a-z0-9]+)+$/.test(declaration.provider_id)
      || !identity(declaration.capability_id) || !['read', 'write'].includes(String(declaration.access_mode))
      || typeof declaration.required_permission !== 'string' || !/^[a-z][a-z0-9_]{0,95}$/.test(declaration.required_permission)
      || !controls(declaration.control_actions) || !object(declaration.options)
      || !exact(contract, ['contract_version', 'access_modes', 'control_actions']) || contract.contract_version !== 1
      || !Array.isArray(contract.access_modes) || !contract.access_modes.length || contract.access_modes.length > 2
      || !contract.access_modes.every(mode => mode === 'read' || mode === 'write') || new Set(contract.access_modes).size !== contract.access_modes.length
      || !contract.access_modes.includes(declaration.access_mode) || !controls(contract.control_actions)
      || declaration.control_actions.some(action => !(contract.control_actions as string[]).includes(action))) return false
    let items = 0
    const json = (value: unknown, depth = 0): boolean => {
      if (++items > 8192 || depth > 16) return false
      if (value === null || typeof value === 'boolean' || typeof value === 'string') return true
      if (typeof value === 'number') return Number.isFinite(value) && (!Number.isInteger(value) || Number.isSafeInteger(value))
      if (Array.isArray(value)) return value.every(child => json(child, depth + 1))
      return object(value) && Object.getPrototypeOf(value) === Object.prototype
        && Object.entries(value).every(([key, child]) => json(key, depth + 1) && json(child, depth + 1))
    }
    if (!json(declaration.options) || new TextEncoder().encode(JSON.stringify(declaration.options)).length > 8192) return false
    const key = `session:${declaration.binding_id}:open`, owner = ownerBinding(item.owner)
    if (!expected.includes(key) || keys.has(key) || owners.some(previous => previous !== owner)) return false
    keys.add(key); owners.push(owner)
  }
  return true
}

function taskScalarSchema(value: unknown): boolean {
  if (!object(value) || Object.keys(value).some(key => !['type', 'properties', 'required', 'additionalProperties'].includes(key))
    || value.type !== 'object' || value.additionalProperties !== false || !object(value.properties)
    || Object.keys(value.properties).length > 8) return false
  const required = value.required === undefined ? [] : value.required
  if (!Array.isArray(required) || new Set(required).size !== required.length
    || required.some(key => typeof key !== 'string' || !Object.prototype.hasOwnProperty.call(value.properties, key))) return false
  for (const [name, field] of Object.entries(value.properties)) {
    if (!name || Array.from(name).length > 128 || !object(field)) return false
    const kind = field.type
    if (!['string', 'boolean', 'integer', 'number'].includes(String(kind))) return false
    const allowed = ['type', 'enum', ...(kind === 'string' ? ['minLength', 'maxLength']
      : kind === 'boolean' ? [] : ['minimum', 'maximum'])]
    if (Object.keys(field).some(key => !allowed.includes(key))) return false
    const minimumLength = field.minLength === undefined ? 0 : field.minLength
    if (kind === 'string' && (!bounded(field.maxLength, 512) || !bounded(minimumLength, Number(field.maxLength), 0))) return false
    if ((kind === 'integer' || kind === 'number') && (typeof field.minimum !== 'number' || !Number.isFinite(field.minimum)
      || typeof field.maximum !== 'number' || !Number.isFinite(field.maximum) || field.minimum > field.maximum)) return false
    if (field.enum !== undefined) {
      if (!Array.isArray(field.enum) || !field.enum.length || field.enum.some(item => kind === 'boolean' ? typeof item !== 'boolean'
        : kind === 'string' ? typeof item !== 'string' || Array.from(item).length < Number(minimumLength) || Array.from(item).length > Number(field.maxLength)
        : typeof item !== 'number' || !Number.isFinite(item) || kind === 'integer' && !Number.isInteger(item)
          || item < Number(field.minimum) || item > Number(field.maximum))) return false
    }
  }
  return true
}

function taskResourcesMatch(resources: Record<string, unknown>, selected: string[], status: AuthorityStatus, moduleId?: string): boolean {
  const tasks = (resources.tasks || []) as unknown[]
  const expected = selected.filter(scope => scope.startsWith('task:'))
  if (tasks.length !== expected.length) return false
  if (tasks.length && Object.entries(resources).some(([key, items]) => !['tasks', 'commands'].includes(key) && (items as unknown[]).length)) return false
  const keys = new Set<string>(), handlers = new Set<string>(), owners = new Set<string>()
  const identifier = (value: unknown): value is string => typeof value === 'string' && /^[a-z][a-z0-9_]{0,95}$/.test(value)
  for (const item of tasks) {
    if (!object(item) || !exact(item, ['declaration', 'operation', 'owner', 'package_artifact_sha256'])
      || !object(item.owner) || !ownerMatches(item.owner, status, moduleId)
      || item.package_artifact_sha256 !== status.artifact_sha256 || !object(item.declaration) || !object(item.operation)) return false
    const declaration = item.declaration, operation = item.operation
    if (!exact(declaration, ['task_id', 'handler_operation_id', 'profile', 'max_runtime_seconds', 'max_delay_seconds', 'max_pending'])
      || !identifier(declaration.task_id) || !identifier(declaration.handler_operation_id)
      || !['bounded_result_once_v1', 'bounded_task_v1'].includes(String(declaration.profile))
      || (resources.commands as unknown[]).length > 0 && declaration.profile !== 'bounded_task_v1'
      || !bounded(declaration.max_runtime_seconds, 10) || !bounded(declaration.max_delay_seconds, 3600, 0)
      || !bounded(declaration.max_pending, 8)
      || !exact(operation, ['operation_id', 'kind', 'audiences', 'required_permission', 'idempotency', 'input_schema', 'output_schema', 'timeout_seconds', 'audit', 'emitted_events'])
      || operation.operation_id !== declaration.handler_operation_id || operation.kind !== 'task' || operation.idempotency !== 'required'
      || !Array.isArray(operation.audiences) || operation.audiences.length !== 1 || operation.audiences[0] !== 'internal'
      || operation.required_permission !== null || operation.timeout_seconds !== declaration.max_runtime_seconds
      || !['metadata', 'redacted'].includes(String(operation.audit)) || !Array.isArray(operation.emitted_events) || operation.emitted_events.length
      || !taskScalarSchema(operation.input_schema) || !taskScalarSchema(operation.output_schema)) return false
    const key = `task:${declaration.task_id}`, owner = ownerBinding(item.owner)
    if (!expected.includes(key) || keys.has(key) || handlers.has(declaration.handler_operation_id) || owners.size && !owners.has(owner)) return false
    keys.add(key); handlers.add(declaration.handler_operation_id); owners.add(owner)
  }
  return true
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
  // Older Core responses remain supported. A status-only response must not
  // smuggle effective authority, review choices or usable grant revisions.
  if (value.review_available !== undefined || value.review_blockers !== undefined) {
    if (typeof value.review_available !== 'boolean' || !Array.isArray(value.review_blockers)
      || value.review_blockers.length > 2 || new Set(value.review_blockers).size !== value.review_blockers.length
      || !value.review_blockers.every(reason => ['review_key_unavailable', 'unsupported_authority'].includes(String(reason)))
      || value.review_available && value.review_blockers.length !== 0
      || !value.review_available && (!value.review_blockers.length || value.grant_effective
        || value.grant_record_revision !== null || value.scopes.length || value.native_reviews.length
        || value.grant_state !== null && value.grant_state !== 'unavailable')) {
      throw new Error('Unsupported authority availability')
    }
  }
  const declared = value.scopes
  if (value.runtime_blockers !== undefined && (!Array.isArray(value.runtime_blockers) || value.runtime_blockers.length > 3
    || new Set(value.runtime_blockers).size !== value.runtime_blockers.length
    || !value.runtime_blockers.every(reason => reason === 'relational_runtime_unavailable'
      ? declared.some(scope => scope.startsWith('storage:relational_'))
      : reason === 'peer_read_runtime_unavailable' ? declared.some(scope => scope.startsWith('peer:'))
      : reason === 'query_runtime_not_connected' ? declared.some(scope => scope.startsWith('query:'))
      : reason === 'session_runtime_not_connected' && declared.some(scope => scope.startsWith('session:')))
    || value.runtime_blockers.length > 0 && value.grant_effective)
    || declared.some(scope => scope.startsWith('peer:')) && declared.some(scope => scope.startsWith('storage:relational_'))) {
    throw new Error('Unsupported authority runtime status')
  }
  return value as unknown as AuthorityStatus
}

export function readAuthorityPlan(value: unknown, status: AuthorityStatus, moduleId?: string, requested?: string[]): AuthorityPlan {
  const selected = object(value) && scopes(value.scopes) ? value.scopes : null
  if (status.review_available === false || !object(value) || !id(value.plan_id) || !id(value.revision) || !digest(value.fingerprint)
    || value.state !== 'review_required' || value.artifact_sha256 !== status.artifact_sha256
    || value.isolation_proven !== false || !selected
    || selected.some(scope => !status.scopes.includes(scope))
    || status.scopes.some(scope => !scope.startsWith('peer:') && !scope.startsWith('session:') && !scope.startsWith('query:') && !selected.includes(scope))
    || requested !== undefined && (selected.length !== requested.length || requested.some(scope => !selected.includes(scope)))
    || !Number.isInteger(value.expires_in_seconds) || Number(value.expires_in_seconds) <= 0 || Number(value.expires_in_seconds) > 900
    || !object(value.resources) || !Array.isArray(value.resources.commands) || value.resources.commands.length > 64
    || !Array.isArray(value.resources.connectors) || value.resources.connectors.length > 32
    || !(value.resources.events === undefined || Array.isArray(value.resources.events) && value.resources.events.length <= 32)
    || !(value.resources.publications === undefined || Array.isArray(value.resources.publications) && value.resources.publications.length <= 32)
    || !(value.resources.private_files === undefined || Array.isArray(value.resources.private_files) && value.resources.private_files.length <= 4)
    || !(value.resources.relational === undefined || Array.isArray(value.resources.relational) && value.resources.relational.length <= 2)
    || !(value.resources.checkpoints === undefined || Array.isArray(value.resources.checkpoints) && value.resources.checkpoints.length <= 64)
    || !(value.resources.identities === undefined || Array.isArray(value.resources.identities) && value.resources.identities.length <= 1)
    || !(value.resources.status_projections === undefined || Array.isArray(value.resources.status_projections) && value.resources.status_projections.length <= 32)
    || !(value.resources.peer_reads === undefined || Array.isArray(value.resources.peer_reads) && value.resources.peer_reads.length <= 32)
    || !(value.resources.sessions === undefined || Array.isArray(value.resources.sessions) && value.resources.sessions.length <= 32)
    || !(value.resources.tasks === undefined || Array.isArray(value.resources.tasks) && value.resources.tasks.length <= 8)
    || !(value.resources.queries === undefined || Array.isArray(value.resources.queries) && value.resources.queries.length <= 16)
    || Object.keys(value.resources).some(key => !['commands', 'connectors', 'events', 'publications', 'private_files', 'relational', 'checkpoints', 'identities', 'status_projections', 'peer_reads', 'sessions', 'tasks', 'queries'].includes(key))
    || value.resources.commands.length + value.resources.connectors.length + ((value.resources.events as unknown[] | undefined)?.length || 0)
      + ((value.resources.publications as unknown[] | undefined)?.length || 0) + ((value.resources.private_files as unknown[] | undefined)?.length || 0)
      + ((value.resources.relational as unknown[] | undefined)?.length || 0) + ((value.resources.checkpoints as unknown[] | undefined)?.length || 0)
      + ((value.resources.identities as unknown[] | undefined)?.length || 0)
      + ((value.resources.status_projections as unknown[] | undefined)?.length || 0)
      + ((value.resources.tasks as unknown[] | undefined)?.length || 0) !== selected.filter(scope => !scope.startsWith('peer:') && !scope.startsWith('session:') && !scope.startsWith('query:')).length
    || !resourceScopesMatch(value.resources, selected)
    || !privateFilesMatch(value.resources, selected, status, moduleId)
    || !relationalMatch(value.resources, selected, status, moduleId)
    || !checkpointsMatch(value.resources, selected, status, moduleId)
    || !identitiesMatch(value.resources, selected, status, moduleId)
    || !statusProjectionsMatch(value.resources, selected, status, moduleId)
    || !peerReadsMatch(value.resources, status, moduleId)
    || !sessionResourcesMatch(value.resources, status, moduleId)
    || !taskResourcesMatch(value.resources, selected, status, moduleId)
    || !queriesMatch(value.resources, status, moduleId)
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
