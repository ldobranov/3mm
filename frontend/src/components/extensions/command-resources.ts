// Administrator observations and explicit changes; never application authority.
export interface CommandBinding {
  binding_id: string; target_device_config_key: string; capability_id: string
  contract_version: string | null; action: string
}
export interface CommandCandidate {
  device_id: string; provider_type: string | null; provider_id: string | null
  provider_version: string | null; contract_version: string | null
  compatible: boolean; selectable: boolean; blockers: string[]
  readiness: 'ready' | 'unavailable' | 'unknown'; readiness_reason: string | null
}
export interface CommandDiscovery {
  binding_id: string; capability_id: string; action: string; contract_version: string | null
  selected_device_id: string | null; candidates: CommandCandidate[]; next_after_device_id: string | null
}
export interface CommandRebindPreview {
  preview_id: string; revision: string; fingerprint: string; expires_in_seconds: number
  before_provider: CommandCandidate; after_provider: CommandCandidate; scopes: string[]
}
export interface CommandRebindStatus {
  preview_id: string; revision: string; binding_id: string; device_id: string
  state: 'preview' | 'applying' | 'completed' | 'recovering' | 'recovery_required' | 'recovered_disabled'
  installation_status: string; installation_enabled: boolean; recovery_required: boolean
}
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const text = (v: unknown, max = 160): v is string => typeof v === 'string' && v.length > 0 && v.length <= max && v.trim() === v
const nullableText = (v: unknown) => v === null || text(v)
const device = (v: unknown): v is string => typeof v === 'string' && /^dev_[a-f0-9]{32}$/.test(v)
const id = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{32}$/.test(v)
const digest = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v)
const bindingId = (v: unknown): v is string => typeof v === 'string' && /^[a-z][a-z0-9_]{0,95}$/.test(v)
function invalid(): never { throw new Error('Invalid command resource observation') }

export function readCommandConfiguration(value: unknown, moduleId: string) {
  if (!object(value) || value.module_id !== moduleId || !Array.isArray(value.command_bindings)
    || value.command_bindings.length > 64 || !Array.isArray(value.devices)) return invalid()
  const bindings = value.command_bindings.map(item => {
    if (!object(item) || !bindingId(item.binding_id) || !text(item.target_device_config_key)
      || !text(item.capability_id) || !nullableText(item.contract_version) || !text(item.action)) return invalid()
    return item as unknown as CommandBinding
  })
  if (new Set(bindings.map(item => item.binding_id)).size !== bindings.length) return invalid()
  const names: Record<string, string> = {}
  for (const item of value.devices) {
    if (!object(item) || !device(item.device_id) || !(item.display_name == null || typeof item.display_name === 'string')) return invalid()
    names[item.device_id] = item.display_name as string || item.device_id
  }
  return { bindings, names }
}

function readCandidate(value: unknown): CommandCandidate {
  if (!object(value) || !device(value.device_id) || !nullableText(value.provider_type)
    || !nullableText(value.provider_id) || !nullableText(value.provider_version) || !nullableText(value.contract_version)
    || typeof value.compatible !== 'boolean' || typeof value.selectable !== 'boolean'
    || !Array.isArray(value.blockers) || value.blockers.length > 8 || !value.blockers.every(item => text(item))
    || !['ready', 'unavailable', 'unknown'].includes(String(value.readiness)) || !nullableText(value.readiness_reason)
    || value.selectable !== (value.compatible && !value.blockers.length)
    || (value.readiness === 'ready') !== (value.readiness_reason === null)) return invalid()
  return value as unknown as CommandCandidate
}

export function readCommandDiscovery(value: unknown, binding: CommandBinding): CommandDiscovery {
  if (!object(value) || value.discovery_version !== 1 || value.access !== 'not_evaluated'
    || value.binding_id !== binding.binding_id || value.capability_id !== binding.capability_id
    || value.action !== binding.action || value.contract_version !== binding.contract_version
    || !(value.selected_device_id === null || device(value.selected_device_id))
    || !(value.next_after_device_id === null || device(value.next_after_device_id))
    || !text(value.observed_at) || !/(Z|[+-]\d\d:\d\d)$/.test(value.observed_at) || !Number.isFinite(Date.parse(value.observed_at))
    || !Array.isArray(value.candidates) || value.candidates.length > 32) return invalid()
  const candidates = value.candidates.map(readCandidate)
  if (new Set(candidates.map(item => item.device_id)).size !== candidates.length) return invalid()
  return { ...value, candidates } as unknown as CommandDiscovery
}

export function readCommandRebindPreview(value: unknown, moduleId: string, sha: string,
  binding: CommandBinding, selected: string, previous: string | null): CommandRebindPreview {
  if (!object(value) || value.rebinding_version !== 1 || value.module_id !== moduleId
    || !id(value.preview_id) || !id(value.revision) || !digest(value.fingerprint) || value.artifact_sha256 !== sha
    || value.binding_id !== binding.binding_id || value.restart_required !== true
    || !Number.isSafeInteger(value.expires_in_seconds) || Number(value.expires_in_seconds) < 1 || Number(value.expires_in_seconds) > 900
    || !Array.isArray(value.scopes) || value.scopes.length > 293 || !value.scopes.every(item => text(item))
    || !value.scopes.includes('command:' + binding.binding_id) || new Set(value.scopes).size !== value.scopes.length) return invalid()
  const before = readCandidate(value.before_provider), after = readCandidate(value.after_provider)
  if (!previous || before.device_id !== previous || after.device_id !== selected || previous === selected || !after.selectable) return invalid()
  for (const [resource, candidate] of [[value.before, before], [value.after, after]] as const) {
    if (!object(resource) || !object(resource.declaration) || resource.declaration.binding_id !== binding.binding_id
      || resource.declaration.capability_id !== binding.capability_id || resource.declaration.action !== binding.action
      || resource.declaration.contract_version !== binding.contract_version || resource.target_device_id !== candidate.device_id
      || !text(resource.control_revision)) return invalid()
  }
  return value as unknown as CommandRebindPreview
}

export function readCommandRebindStatus(value: unknown, moduleId: string, planId?: string): CommandRebindStatus {
  if (!object(value) || value.rebinding_version !== 1 || value.module_id !== moduleId || !id(value.preview_id)
    || planId !== undefined && value.preview_id !== planId || !id(value.revision) || !bindingId(value.binding_id) || !device(value.device_id)
    || !['preview', 'applying', 'completed', 'recovering', 'recovery_required', 'recovered_disabled'].includes(String(value.state))
    || !text(value.installation_status) || typeof value.installation_enabled !== 'boolean'
    || value.access !== 'not_evaluated' || typeof value.recovery_required !== 'boolean'
    || value.recovery_required !== ['applying', 'recovering', 'recovery_required'].includes(String(value.state))) return invalid()
  return value as unknown as CommandRebindStatus
}

export function readPendingRebind(value: unknown, moduleId: string): CommandRebindStatus | null {
  if (!object(value) || !('pending' in value)) return invalid()
  if (value.pending === null) return null
  const result = readCommandRebindStatus(value.pending, moduleId)
  if (!result.recovery_required || result.installation_enabled) return invalid()
  return result
}
