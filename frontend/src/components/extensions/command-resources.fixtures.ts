// Disposable administrator DTOs. No live device identifiers or grants.
export const moduleId = 'org.example.resources'
export const sha = 'a'.repeat(64)
export const first = 'dev_' + '1'.repeat(32), second = 'dev_' + '2'.repeat(32)
export const base = `/api/v1/application-extensions/${moduleId}/authority/command-rebindings`
export const binding = { binding_id: 'pulse', target_device_config_key: 'OUTPUT_DEVICE_ID',
  capability_id: 'gpio.digital.control', contract_version: '1.0', action: 'pulse' }
export function candidate(device_id = first) {
  return { device_id, provider_type: 'native', provider_id: device_id === first ? 'org.example.first' : 'org.example.second',
    provider_version: '1.0.0', contract_version: '1.0', compatible: true, selectable: true, blockers: [],
    readiness: 'ready', readiness_reason: null }
}
export function configuration() {
  return { module_id: moduleId, version: '1.0.0', fields: [], command_bindings: [binding],
    devices: [{ device_id: first, display_name: 'Entrance controller' }, { device_id: second, display_name: 'Spare controller' }] }
}
export function authority() {
  return { installation_id: 1, mode: 'enforced', installation_status: 'active', installation_enabled: true,
    artifact_sha256: sha, scopes: ['command:pulse'], native_reviews: [], grant_record_revision: 'b'.repeat(32),
    grant_state: 'active', grant_effective: true, isolation_proven: false }
}
export function discovery() {
  return { discovery_version: 1, ...binding, observed_at: '2026-10-25T10:00:00Z', access: 'not_evaluated',
    selected_device_id: first, candidates: [candidate(), candidate(second)], next_after_device_id: null }
}
export function preview() {
  return { rebinding_version: 1, module_id: moduleId, artifact_sha256: sha, binding_id: 'pulse',
    preview_id: 'c'.repeat(32), revision: 'd'.repeat(32), fingerprint: 'e'.repeat(64), expires_in_seconds: 900,
    before: { declaration: binding, target_device_id: first, control_revision: 'control_' + 'f'.repeat(64) },
    after: { declaration: binding, target_device_id: second, control_revision: 'control_' + 'a'.repeat(64) },
    before_provider: candidate(), after_provider: candidate(second), scopes: ['command:pulse'], restart_required: true }
}
export function status(state = 'completed') {
  const pending = ['applying', 'recovering', 'recovery_required'].includes(state)
  return { rebinding_version: 1, module_id: moduleId, preview_id: 'c'.repeat(32), revision: 'f'.repeat(32),
    binding_id: 'pulse', device_id: second, state, installation_status: pending ? 'recovery_required' : state === 'completed' ? 'active' : 'disabled',
    installation_enabled: state === 'completed', recovery_required: pending, access: 'not_evaluated' }
}
