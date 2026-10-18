// Synthetic public DTOs shared by peer-read parser/dialog tests, never live data.
export const peerModuleId = 'org.example.peer-reference'
export const peerArtifact = 'a'.repeat(64)
export const peerOwner = () => ({ core_installation_id: 'inst_' + 'b'.repeat(32), application_installation_id: '7', incarnation: 'c'.repeat(32), module_id: peerModuleId })
export const peerSender = () => ({ identity_version: 1, installation_id: peerOwner().core_installation_id, algorithm: 'ed25519',
  key_id: '21fe31dfa154a261626bf854046fd2271b7bed4b6abe45aa58877ef47f9721b9',
  public_key: '11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=', key_generation: 1, created_at: '2026-10-16T12:00:00Z' })
export const peerReceiver = () => ({ ...peerSender(), installation_id: 'inst_' + '8'.repeat(32),
  key_id: '515a733d7320b35b2117893952f93a9400dc4d5ca8bb6972453cae4cab993a07', public_key: 'cnJy'.repeat(10) + 'cnI=' })
export const peerConsent = () => ({ consent_version: 1, summary_fields: ['core_version', 'sdk_version'], node_ids: ['dev_' + 'e'.repeat(32)], node_fields: ['display_name', 'online'] })
export const peerResource = (version = 1, binding = 'remote_link', letter = 'a') => ({
  declaration: { contract_version: 1, binding_id: binding, direction: 'outbound', peer_id_config_key: binding.toUpperCase(), operations: ['read'] },
  owner: peerOwner(), package_artifact_sha256: peerArtifact, service_artifact_sha256: 'f'.repeat(64),
  application_instance_id: 'd'.repeat(24), peer_id: 'peer_' + letter.repeat(32), peer_version: version,
  sender_identity: peerSender(), receiver_identity: peerReceiver(), origin: 'https://receiver.example', target_module_id: 'org.example.receiver',
  consent_revision: 2, consent: peerConsent(), enrollment_metadata: version === 1 ? null : {
    metadata_version: 2, application_intent: 'intent_opaque', consent_revision: 2, consent: peerConsent(),
    metadata_hash: '7'.repeat(64), // Shape only: the browser is deliberately not a cryptographic verifier.
  },
})
export const peerResources = () => [peerResource(), peerResource(2, 'second_link', 'f')]
export const peerScopes = () => peerResources().map(item => `peer:${item.declaration.binding_id}:read`)
export const peerStatus = () => ({ installation_id: 7, mode: 'enforced', installation_status: 'active', installation_enabled: true,
  artifact_sha256: peerArtifact, scopes: peerScopes(), native_reviews: [{ native_review_id: '1'.repeat(32), revision: '2'.repeat(32) }],
  grant_state: 'active', grant_record_revision: '3'.repeat(32), grant_effective: false, isolation_proven: false,
  review_available: true, review_blockers: [], runtime_blockers: ['peer_read_runtime_unavailable'] })
export const peerPlan = (selected = peerScopes()) => ({ plan_id: '4'.repeat(32), revision: '5'.repeat(32), fingerprint: '6'.repeat(64),
  state: 'review_required', artifact_sha256: peerArtifact, scopes: selected, expires_in_seconds: 900, isolation_proven: false,
  resources: { commands: [], connectors: [], peer_reads: peerResources() } })
