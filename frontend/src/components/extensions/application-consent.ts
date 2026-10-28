/** Strict admin consent DTOs; previews never approve or start application code. */
import { readAuthorityPlan, readAuthorityStatus, type AuthorityPlan } from './authority-management'

export interface ApplicationConsentPreview {
  consent_version: 1; preview_id: string; revision: string; fingerprint: string; expires_in_seconds: number
  module_id: string; installation_id: number; artifact_sha256: string; built_ui_sha256: string | null
  scopes: string[]; selected_scopes: string[]; optional_resources: string[]; resources: AuthorityPlan['resources']
  unavailable_resources: Array<{ scope: string; reason: string }>
  user_permissions: Array<{ permission_id: string; name: string }>; selected_user_permissions: string[]
  access_saved: boolean; installation_enabled: boolean; installation_status: string
}
export interface ApplicationConsentResult {
  consent_version: 1; module_id: string; installation_id: number; preview_id: string; saved: true
  effective: boolean; grant_revision: number; grant_record_revision: string; authority_epoch: string
  installation_enabled: boolean; installation_status: string
}
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const id = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value)
const digest = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
const permission = (value: unknown): value is string => typeof value === 'string' && /^[a-z][a-z0-9_]{0,95}$/.test(value)
const subset = (value: unknown, allowed: string[]): value is string[] => Array.isArray(value) && value.length <= allowed.length
  && value.every(item => typeof item === 'string' && allowed.includes(item)) && new Set(value).size === value.length
const lifecycle = (value: unknown): value is string => typeof value === 'string' && /^[a-z][a-z0-9_]{0,31}$/.test(value)
const optionalResources = (value: unknown): value is string[] => Array.isArray(value) && value.length <= 16
  && value.every(scope => typeof scope === 'string' && /^[a-z][a-z0-9_.:-]{0,191}$/.test(scope))
  && new Set(value).size === value.length

export function readConsentPreview(value: unknown, moduleId: string): ApplicationConsentPreview {
  const fields = ['consent_version', 'preview_id', 'revision', 'fingerprint', 'expires_in_seconds', 'module_id', 'installation_id',
    'artifact_sha256', 'built_ui_sha256', 'scopes', 'selected_scopes', 'optional_resources', 'unavailable_resources', 'resources', 'user_permissions', 'selected_user_permissions',
    'access_saved', 'installation_enabled', 'installation_status']
  if (!object(value) || Object.keys(value).length !== fields.length || fields.some(field => !(field in value))
    || value.consent_version !== 1 || value.module_id !== moduleId || !id(value.preview_id) || !id(value.revision)
    || !digest(value.fingerprint) || !digest(value.artifact_sha256) || value.built_ui_sha256 !== null && !digest(value.built_ui_sha256)
    || !Number.isSafeInteger(value.installation_id) || Number(value.installation_id) < 1
    || !Number.isInteger(value.expires_in_seconds) || Number(value.expires_in_seconds) < 1 || Number(value.expires_in_seconds) > 900
    || typeof value.access_saved !== 'boolean' || typeof value.installation_enabled !== 'boolean' || !lifecycle(value.installation_status)
    || !optionalResources(value.optional_resources)
    || !Array.isArray(value.unavailable_resources) || value.unavailable_resources.length > 16
    || !value.unavailable_resources.every(item => object(item) && Object.keys(item).length === 2
      && typeof item.scope === 'string' && (value.optional_resources as string[]).includes(item.scope)
      && Array.isArray(value.scopes) && !value.scopes.includes(item.scope)
      && typeof item.reason === 'string' && /^[a-z][a-z0-9_]{0,95}$/.test(item.reason))
    || !Array.isArray(value.user_permissions) || value.user_permissions.length > 96
    || !value.user_permissions.every(item => object(item) && Object.keys(item).length === 2 && permission(item.permission_id)
      && typeof item.name === 'string' && item.name.length > 0 && item.name.length <= 1000)) throw new Error('Unsupported application consent preview')
  const permissions = value.user_permissions.map(item => (item as { permission_id: string }).permission_id)
  if (new Set(value.unavailable_resources.map(item => item.scope)).size !== value.unavailable_resources.length) throw new Error('Duplicate unavailable resource')
  if (new Set(permissions).size !== permissions.length) throw new Error('Duplicate application permissions')
  // Adapt only validation inputs, never a server authority record. This reuses
  // every existing exact resource/owner/digest/limit validator on ALL declared
  // resources; selected rights are separately checked as explicit subsets.
  const status = readAuthorityStatus({ installation_id: value.installation_id, mode: 'review_required',
    installation_status: value.installation_status, installation_enabled: value.installation_enabled,
    artifact_sha256: value.artifact_sha256, scopes: value.scopes, native_reviews: [], grant_state: null,
    grant_record_revision: null, grant_effective: false, isolation_proven: false })
  readAuthorityPlan({ plan_id: value.preview_id, revision: value.revision, fingerprint: value.fingerprint, state: 'review_required',
    artifact_sha256: value.artifact_sha256, scopes: value.scopes, expires_in_seconds: value.expires_in_seconds,
    resources: value.resources, isolation_proven: false }, status, moduleId, status.scopes)
  if (!subset(value.selected_scopes, status.scopes) || !subset(value.selected_user_permissions, permissions)) {
    throw new Error('Unsupported application consent selection')
  }
  if (status.scopes.includes('storage:relational_read') && status.scopes.includes('storage:relational_write')
    && value.selected_scopes.includes('storage:relational_read') !== value.selected_scopes.includes('storage:relational_write')) {
    throw new Error('Partial relational access profile')
  }
  return value as unknown as ApplicationConsentPreview
}

export function readConsentResult(value: unknown, preview: ApplicationConsentPreview): ApplicationConsentResult {
  const fields = ['consent_version', 'module_id', 'installation_id', 'preview_id', 'saved', 'effective', 'grant_revision',
    'grant_record_revision', 'authority_epoch', 'installation_enabled', 'installation_status']
  if (!object(value) || fields.some(field => !(field in value))
    || Object.keys(value).some(field => !fields.includes(field) && field !== 'replayed' && field !== 'historical')
    || value.consent_version !== 1 || value.module_id !== preview.module_id || value.installation_id !== preview.installation_id
    || value.preview_id !== preview.preview_id || value.saved !== true || typeof value.effective !== 'boolean'
    || !Number.isSafeInteger(value.grant_revision) || Number(value.grant_revision) < 1
    || !id(value.grant_record_revision) || !id(value.authority_epoch)
    || typeof value.installation_enabled !== 'boolean' || !lifecycle(value.installation_status)
    || value.effective && (!value.installation_enabled || value.installation_status !== 'active')
    || value.replayed !== undefined && value.replayed !== false || value.historical !== undefined && value.historical !== false) {
    throw new Error('Unconfirmed application consent result')
  }
  return value as unknown as ApplicationConsentResult
}
