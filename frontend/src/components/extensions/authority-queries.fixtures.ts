import { consentPreview } from './application-consent.fixtures'
import type { AuthorityQueryResource } from './authority-queries'

export function queryPreview() {
  const contract = { contract_id: 'example.directory.lookup', contract_version: '1.0', kind: 'query' as const,
    input_schema: { type: 'object', properties: { reference: { type: 'string', minLength: 1, maxLength: 96 } }, required: ['reference'], additionalProperties: false },
    output_schema: { type: 'object', properties: { found: { type: 'boolean' }, label: { type: 'string', maxLength: 160 } }, required: ['found'], additionalProperties: false },
    timeout_seconds: 5, max_response_bytes: 4096 }
  const owner = { core_installation_id: 'inst_'+'a'.repeat(32), application_installation_id: '7', incarnation: 'b'.repeat(32), module_id: 'org.example.reference' }
  const resource: AuthorityQueryResource = {
    declaration: { binding_id: 'directory', contract, provider_instance_config_key: 'DIRECTORY_INSTANCE', provider_export_config_key: 'DIRECTORY_EXPORT' },
    export: { export_id: 'lookup', handler_operation_id: 'lookup_entity', contract: structuredClone(contract) },
    owner, owner_instance_id: 'c'.repeat(24), package_artifact_sha256: 'd'.repeat(64),
    provider: { ...owner, application_installation_id: '8', incarnation: 'e'.repeat(32), module_id: 'org.example.directory' },
    provider_instance_id: 'f'.repeat(24), provider_artifact: { version: '1.0.0', sha256: '1'.repeat(64), built_ui_sha256: null },
    provider_configuration: { key_id: 'review_'+'2'.repeat(32), keyed_sha256: '3'.repeat(64) },
    provider_authority_epoch: '4'.repeat(32), provider_grant_revision: 3, provider_grant_record_revision: '5'.repeat(32), contract_digest: '6'.repeat(64),
  }
  return { ...consentPreview({ installation_id: 7, artifact_sha256: resource.package_artifact_sha256,
    scopes: ['query:directory:read'], installation_enabled: false, installation_status: 'disabled' }, { commands: [], connectors: [], queries: [resource] }),
    selected_scopes: [], user_permissions: [], selected_user_permissions: [] }
}
