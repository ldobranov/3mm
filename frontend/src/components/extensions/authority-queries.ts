/** Exact CAP13 consent DTO validation, not a signature/permission verifier. */
import type { AuthorityStatus, AuthorityPrivateFileResource } from './authority-management'

export interface QueryContract {
  contract_id: string; contract_version: string; kind: 'query'
  input_schema: Record<string, unknown>; output_schema: Record<string, unknown>
  timeout_seconds: number; max_response_bytes: number
}
export interface AuthorityQueryResource {
  declaration: { binding_id: string; contract: QueryContract; provider_instance_config_key: string; provider_export_config_key: string }
  export: { export_id: string; handler_operation_id: string; contract: QueryContract }
  owner: AuthorityPrivateFileResource['owner']; owner_instance_id: string; package_artifact_sha256: string
  provider: AuthorityPrivateFileResource['owner']; provider_instance_id: string
  provider_artifact: { version: string; sha256: string; built_ui_sha256: string | null }
  provider_configuration: { key_id: string; keyed_sha256: string }; provider_authority_epoch: string
  provider_grant_revision: number; provider_grant_record_revision: string; contract_digest: string
}
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const exact = (v: Record<string, unknown>, keys: string[]) => Object.keys(v).length === keys.length && keys.every(k => k in v)
const text = (v: unknown, pattern: RegExp, max = 160): v is string => typeof v === 'string' && v.length <= max && pattern.test(v)
const id = (v: unknown) => text(v, /^[a-z][a-z0-9_]{0,95}$/)
const digest = (v: unknown) => text(v, /^[a-f0-9]{64}$/)
const identity = (v: unknown) => text(v, /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/)
const integer = (v: unknown, max: number, min = 1) => Number.isSafeInteger(v) && Number(v) >= min && Number(v) <= max
const bytes = (v: unknown) => new TextEncoder().encode(JSON.stringify(v)).length
const canonical = (v: unknown): string => JSON.stringify(v, (_key, item) => object(item)
  ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : item)

function schema(v: unknown, depth = 0): boolean {
  if (!object(v) || depth > 4) return false
  if (v.type === 'object') {
    if (Object.keys(v).some(k => !['type', 'properties', 'required', 'additionalProperties'].includes(k))
      || v.additionalProperties !== false || !object(v.properties) || Object.keys(v.properties).length > 32) return false
    const required = v.required ?? []
    if (!Array.isArray(required) || new Set(required).size !== required.length
      || required.some(k => typeof k !== 'string' || !(k in (v.properties as object)))) return false
    return Object.entries(v.properties).every(([key, value]) => Array.from(key).length > 0
      && Array.from(key).length <= 160 && schema(value, depth + 1))
  }
  const kind = v.type
  const allowed = ['type', 'enum', ...(kind === 'string' ? ['minLength', 'maxLength']
    : kind === 'number' || kind === 'integer' ? ['minimum', 'maximum'] : [])]
  if (Object.keys(v).some(k => !allowed.includes(k)) || !['string', 'integer', 'number', 'boolean', 'null'].includes(String(kind))) return false
  if (kind === 'string' && (!integer(v.maxLength, 512) || !integer(v.minLength ?? 0, Number(v.maxLength), 0))) return false
  if ((kind === 'number' || kind === 'integer') && (typeof v.minimum !== 'number' || typeof v.maximum !== 'number'
    || !Number.isFinite(v.minimum) || !Number.isFinite(v.maximum) || v.minimum > v.maximum)) return false
  return v.enum === undefined || Array.isArray(v.enum) && v.enum.length > 0 && v.enum.length <= 32 && v.enum.every(value =>
    kind === 'string' ? typeof value === 'string' && Array.from(value).length >= Number(v.minLength ?? 0) && Array.from(value).length <= Number(v.maxLength)
    : kind === 'boolean' ? typeof value === 'boolean' : kind === 'null' ? value === null
    : typeof value === 'number' && Number.isFinite(value) && (kind !== 'integer' || Number.isInteger(value))
      && value >= Number(v.minimum) && value <= Number(v.maximum))
}
function contract(v: unknown): v is QueryContract {
  return object(v) && exact(v, ['contract_id', 'contract_version', 'kind', 'input_schema', 'output_schema', 'timeout_seconds', 'max_response_bytes'])
    && text(v.contract_id, /^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$/) && text(v.contract_version, /^[1-9][0-9]{0,3}\.[0-9]{1,4}$/)
    && v.kind === 'query' && integer(v.timeout_seconds, 5) && integer(v.max_response_bytes, 16384)
    && object(v.input_schema) && v.input_schema.type === 'object' && bytes(v.input_schema) <= 8192 && schema(v.input_schema)
    && object(v.output_schema) && v.output_schema.type === 'object' && bytes(v.output_schema) <= 8192 && schema(v.output_schema)
}
function principal(v: unknown): v is AuthorityPrivateFileResource['owner'] {
  return object(v) && exact(v, ['core_installation_id', 'application_installation_id', 'incarnation', 'module_id'])
    && identity(v.core_installation_id) && identity(v.incarnation) && identity(v.application_installation_id)
    && text(v.module_id, /^[a-z0-9]+(?:[.-][a-z0-9]+)+$/)
}
export function queriesMatch(resources: Record<string, unknown>, status: AuthorityStatus, moduleId?: string): boolean {
  try {
    const queries = (resources.queries ?? []) as unknown[]
    const expected = status.scopes.filter(scope => scope.startsWith('query:'))
    if (!Array.isArray(queries) || queries.length !== expected.length || queries.length > 16
      || queries.length > 0 && Object.entries(resources).some(([name, items]) => name !== 'queries' && (items as unknown[]).length)) return false
    const keys: string[] = []; let owner: string | undefined
    for (const value of queries) {
      if (!object(value) || !exact(value, ['declaration', 'export', 'owner', 'owner_instance_id', 'package_artifact_sha256',
        'provider', 'provider_instance_id', 'provider_artifact', 'provider_configuration', 'provider_authority_epoch',
        'provider_grant_revision', 'provider_grant_record_revision', 'contract_digest'])
        || !object(value.declaration) || !object(value.export) || !principal(value.owner) || !principal(value.provider)
        || !object(value.provider_artifact) || !object(value.provider_configuration)) return false
      const d = value.declaration, e = value.export, a = value.provider_artifact, c = value.provider_configuration
      if (!exact(d, ['binding_id', 'contract', 'provider_instance_config_key', 'provider_export_config_key']) || !id(d.binding_id)
        || !text(d.provider_instance_config_key, /^[A-Z][A-Z0-9_]{1,63}$/) || !text(d.provider_export_config_key, /^[A-Z][A-Z0-9_]{1,63}$/)
        || d.provider_instance_config_key === d.provider_export_config_key || !contract(d.contract)
        || !exact(e, ['export_id', 'handler_operation_id', 'contract']) || !id(e.export_id) || !id(e.handler_operation_id)
        || !contract(e.contract) || canonical(d.contract) !== canonical(e.contract)
        || value.owner.application_installation_id !== String(status.installation_id)
        || moduleId !== undefined && value.owner.module_id !== moduleId || value.package_artifact_sha256 !== status.artifact_sha256
        || value.owner.core_installation_id !== value.provider.core_installation_id
        || value.owner.application_installation_id === value.provider.application_installation_id || value.owner.module_id === value.provider.module_id
        || !text(value.owner_instance_id, /^[a-f0-9]{24}$/) || !text(value.provider_instance_id, /^[a-f0-9]{24}$/)
        || value.owner_instance_id === value.provider_instance_id
        || !exact(a, ['version', 'sha256', 'built_ui_sha256']) || !text(a.version, /^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)*$/, 96)
        || !digest(a.sha256) || a.built_ui_sha256 !== null && !digest(a.built_ui_sha256)
        || !exact(c, ['key_id', 'keyed_sha256']) || !identity(c.key_id) || !digest(c.keyed_sha256)
        || !identity(value.provider_authority_epoch) || !integer(value.provider_grant_revision, Number.MAX_SAFE_INTEGER - 1)
        || !text(value.provider_grant_record_revision, /^[a-f0-9]{32}$/) || !digest(value.contract_digest)) return false
      const binding = canonical([value.owner, value.owner_instance_id])
      if (owner !== undefined && owner !== binding) return false
      owner = binding; keys.push(`query:${d.binding_id}:read`)
    }
    return new Set(keys).size === keys.length && keys.every(key => expected.includes(key))
  } catch { return false }
}
