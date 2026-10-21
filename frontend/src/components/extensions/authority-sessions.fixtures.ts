// Synthetic public review DTOs, not live authority or a runnable provider.
export const sessionModuleId = 'org.example.session-client'
export const sessionOwner = () => ({ core_installation_id: 'inst_' + 'b'.repeat(32), application_installation_id: '7', incarnation: 'c'.repeat(32), module_id: sessionModuleId })
export const sessionResource = () => ({
  declaration: { contract_version: 1, binding_id: 'console', target_device_config_key: 'SESSION_DEVICE',
    provider_id: 'org.example.session-provider', capability_id: 'example.interactive', access_mode: 'write',
    control_actions: ['resize'], required_permission: 'console_use', options: { cols: 80, rows: 24 } },
  owner: sessionOwner(), package_artifact_sha256: 'a'.repeat(64), target_device_id: 'dev_' + 'd'.repeat(32),
  provider_version: '1.0.0', control_revision: 'e'.repeat(64),
  contract: { contract_version: 1, access_modes: ['read', 'write'], control_actions: ['resize', 'signal'] },
})
export const sessionScope = 'session:console:open'
export const sessionStatus = () => ({ installation_id: 7, mode: 'enforced', installation_status: 'active', installation_enabled: true,
  artifact_sha256: 'a'.repeat(64), scopes: [sessionScope], native_reviews: [{ native_review_id: '1'.repeat(32), revision: '2'.repeat(32) }],
  grant_state: 'active', grant_record_revision: '3'.repeat(32), grant_effective: false, isolation_proven: false,
  review_available: true, review_blockers: [], runtime_blockers: ['session_runtime_not_connected'] })
export const sessionPlan = (selected: string[] = []) => ({ plan_id: '4'.repeat(32), revision: '5'.repeat(32), fingerprint: '6'.repeat(64),
  state: 'review_required', artifact_sha256: 'a'.repeat(64), scopes: selected, expires_in_seconds: 900, isolation_proven: false,
  resources: { commands: [], connectors: [], sessions: [sessionResource()] } })
