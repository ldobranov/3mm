import type { ConnectorSettings } from './connector-settings'
export const settingsSha = 'a'.repeat(64)
export function connectorSettings(): ConnectorSettings {
  return { module_id: 'org.example.connection', artifact_sha256: settingsSha, installation_id: null,
    snapshot: 'b'.repeat(64), encryption_available: true, credentials: [], connectors: [{
      connector_id: 'business_api', artifact_sha256: settingsSha, snapshot: 'b'.repeat(64), authentication: 'basic',
      allowed_schemes: ['http', 'https'], path_prefix: '/api/', destination_origin: null,
      credential: null, affected_connector_ids: [], reasons: ['connector_binding_unavailable'], state: 'unconfigured', authority: 'not_granted',
    }] }
}
