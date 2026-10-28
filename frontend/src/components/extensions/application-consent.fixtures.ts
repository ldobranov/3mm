// Disposable public consent DTOs for parser/dialog tests, never live grants.
import type { ApplicationConsentPreview } from './application-consent'
export function consentPreview<T>(current: { installation_id: number; artifact_sha256: string; scopes: string[]; installation_enabled: boolean; installation_status: string },
  resources: T, moduleId = 'org.example.reference') {
  return { consent_version: 1, preview_id: '4'.repeat(32), revision: '5'.repeat(32), fingerprint: '6'.repeat(64),
    expires_in_seconds: 900, module_id: moduleId, installation_id: current.installation_id,
    artifact_sha256: current.artifact_sha256, built_ui_sha256: 'b'.repeat(64), scopes: [...current.scopes], selected_scopes: [...current.scopes],
    resources, optional_resources: [] as string[], unavailable_resources: [] as Array<{ scope: string; reason: string }>,
    user_permissions: [{ permission_id: 'app_use', name: 'Use this application' }], selected_user_permissions: ['app_use'],
    access_saved: false, installation_enabled: current.installation_enabled, installation_status: current.installation_status }
}
export function consentResult(preview: Pick<ApplicationConsentPreview, 'module_id' | 'installation_id' | 'preview_id' | 'installation_enabled' | 'installation_status'>) {
  return { consent_version: 1, module_id: preview.module_id, installation_id: preview.installation_id,
    preview_id: preview.preview_id, saved: true, effective: preview.installation_enabled,
    grant_revision: 2, grant_record_revision: '7'.repeat(32), authority_epoch: '8'.repeat(32),
    installation_enabled: preview.installation_enabled, installation_status: preview.installation_status }
}
