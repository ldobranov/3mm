<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import http from '@/utils/dynamic-http'
import { useAuthorityLabels, type AuthorityLabel } from './authority-labels'
import { authorityRequestId, readAuthorityStatus, type AuthorityStatus } from './authority-management'
import { readConsentPreview, readConsentResult, type ApplicationConsentPreview } from './application-consent'

const props = defineProps<{ moduleId: string; name: string }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const label = useAuthorityLabels()
const base = `/api/v1/application-extensions/${encodeURIComponent(props.moduleId)}/authority`
const preview = ref<ApplicationConsentPreview | null>(null)
const status = ref<AuthorityStatus | null>(null)
const selected = ref<string[]>([]), selectedUser = ref<string[]>([])
const busy = ref(false), confirmRevoke = ref(false)
const error = ref<AuthorityLabel | null>(null), notice = ref<AuthorityLabel | null>(null)
const now = ref(Date.now())
let deadline = 0, generation = 0
const timer = setInterval(() => { now.value = Date.now() }, 1000)
onBeforeUnmount(() => { ++generation; clearInterval(timer) })
const expired = computed(() => !!preview.value && now.value >= deadline)
const same = (left: string[], right: string[]) => left.length === right.length && left.every(item => right.includes(item))
const dirty = computed(() => !!preview.value && (!same(selected.value, preview.value.selected_scopes)
  || !same(selectedUser.value, preview.value.selected_user_permissions)))
const relationalPair = computed(() => preview.value?.scopes.includes('storage:relational_read') === true
  && preview.value.scopes.includes('storage:relational_write')
  && preview.value.resources.relational?.some(item => item.declaration.mode === 'read_write') === true)
const canAllow = computed(() => !!preview.value && !busy.value && !expired.value && (!preview.value.access_saved || dirty.value))
const canRevoke = computed(() => status.value?.grant_state === 'active' && !!status.value.grant_record_revision && !busy.value)
const savedLabel = computed(() => !preview.value?.access_saved ? 'consentNeeded'
  : !preview.value.installation_enabled ? 'inactive' : 'consentSaved')
const runtimeUnavailable = computed(() => preview.value?.access_saved && !!status.value?.runtime_blockers?.length)
const kinds = ['commands', 'connectors', 'events', 'publications', 'private_files', 'relational', 'checkpoints', 'identities', 'status_projections', 'peer_reads', 'sessions', 'tasks'] as const
const kindLabels = { commands: 'commands', connectors: 'connectors', events: 'events', publications: 'publications',
  private_files: 'privateFiles', relational: 'relational', checkpoints: 'checkpoints', identities: 'identities',
  status_projections: 'statusProjections', peer_reads: 'peerReads', sessions: 'sessions', tasks: 'tasks' } as const
function failure(cause: unknown, mutation = false): AuthorityLabel {
  const response = (cause as { response?: { status?: number; data?: { detail?: { code?: string } } } })?.response
  if (response?.status === 401 || response?.status === 403) return 'actor'
  if (mutation && !response) return 'consentUncertain'
  return response?.status === 409 ? 'consentStale' : 'consentUnavailable'
}
async function load(current: number) {
  const started = Date.now()
  const response = await http.post(base + '/consent/preview', { request_id: authorityRequestId() }, { timeout: 12000 })
  const value = readConsentPreview(response.data, props.moduleId)
  if (current !== generation) return
  preview.value = value; selected.value = [...value.selected_scopes]; selectedUser.value = [...value.selected_user_permissions]
  deadline = started + value.expires_in_seconds * 1000; now.value = Date.now()
  status.value = null
  // Approval choice and runtime availability are independent. Legacy status is
  // used only for current runtime presentation and explicit revocation.
  try {
    const result = await http.get(base, { timeout: 12000 })
    if (current === generation) {
      const actual = readAuthorityStatus(result.data)
      if (actual.installation_id === value.installation_id && actual.artifact_sha256 === value.artifact_sha256) status.value = actual
    }
  } catch { /* Saved consent is still known; no runtime success is invented. */ }
}
async function refresh() {
  if (busy.value) return
  busy.value = true; error.value = null; notice.value = null; confirmRevoke.value = false
  const current = generation
  try { await load(current) }
  catch (cause) { if (current === generation) { preview.value = null; status.value = null; error.value = failure(cause) } }
  finally { if (current === generation) busy.value = false }
}
async function allow() {
  const value = preview.value
  if (!value || !canAllow.value) return
  busy.value = true; error.value = null; notice.value = null
  const current = generation
  let saved = false
  try {
    const response = await http.post(base + '/consent/allow', { request_id: authorityRequestId(), preview_id: value.preview_id,
      expected_revision: value.revision, fingerprint: value.fingerprint, scopes: [...selected.value],
      user_permissions: [...selectedUser.value], accept_native_code: true }, { timeout: 30000 })
    if (current !== generation) return
    readConsentResult(response.data, value)
    saved = true
    notice.value = 'consentSaved'; emit('changed')
    // Fresh server selection survives future disable/enable and dialog reloads.
    preview.value = null; status.value = null
    await load(current)
  } catch (cause) {
    if (current === generation) { preview.value = null; status.value = null; error.value = saved ? 'consentUnavailable' : failure(cause, true) }
  } finally { if (current === generation) busy.value = false }
}
async function revoke() {
  if (!canRevoke.value || !confirmRevoke.value || !status.value) return
  busy.value = true; error.value = null; notice.value = null
  const current = generation
  try {
    const response = await http.post(base + '/revoke', { request_id: authorityRequestId(),
      expected_revision: status.value.grant_record_revision }, { timeout: 12000 })
    if (current !== generation) return
    if (response.data?.state !== 'revoked' || response.data.historical || response.data.replayed) throw new Error('Unconfirmed revocation')
    confirmRevoke.value = false; notice.value = 'revoked'; emit('changed'); await load(current)
  } catch (cause) {
    if (current === generation) { preview.value = null; status.value = null; error.value = failure(cause, true) }
  } finally { if (current === generation) busy.value = false }
}
function choose(scope: string, event: Event, user = false) {
  if (busy.value || expired.value || !preview.value) return
  const target = user ? selectedUser : selected
  const allowed = user ? preview.value.user_permissions.map(item => item.permission_id) : preview.value.scopes
  if (!allowed.includes(scope)) return
  // Read/write SQL access is one declared profile. The visible pair changes
  // together, so no partial profile is submitted or silently broadened later.
  const group = !user && relationalPair.value && ['storage:relational_read', 'storage:relational_write'].includes(scope)
    ? ['storage:relational_read', 'storage:relational_write'] : [scope]
  target.value = (event.target as HTMLInputElement).checked ? [...new Set([...target.value, ...group])]
    : target.value.filter(item => !group.includes(item))
  notice.value = null
}
function close() { if (!busy.value) emit('close') }
function scopeName(scope: string) {
    const fileLabels: Record<string, AuthorityLabel> = { storage_private_files_read: 'fileRead', storage_private_files_write: 'fileWrite',
      storage_private_files_publish: 'filePublish', storage_private_files_transform: 'fileTransform' }
    const fileLabel = fileLabels[scope.replace(':', '_')]
    if (fileLabel) return label(fileLabel)
  const family = scope.split(':')[0]
  const names: Record<string, AuthorityLabel> = { command: 'commands', connector: 'connectors', event: 'events', publication: 'publications',
    storage: scope.includes('relational') ? 'relational' : 'privateFiles', checkpoint: 'checkpoints', platform: 'identities', status: 'statusProjections', peer: 'peerReads', session: 'sessions', task: 'tasks' }
  return `${label(names[family || ''] || 'resources')} · ${scope}`
}
function sourceReason(reason: string) {
  const reasons: Record<string, AuthorityLabel> = {
    configuration_unresolved: 'sourceConfiguration', device_unavailable: 'sourceDevice',
    device_credentials_unavailable: 'sourceDevice', capability_unresolved: 'sourceProvider',
    capability_unavailable: 'sourceHealth', runtime_support_unresolved: 'sourceRuntime',
    command_contract_unresolved: 'sourceContract', command_schema_containment_not_evaluated: 'sourceContract',
    connector_binding_unavailable: 'sourceConnector', connector_origin_mismatch: 'sourceConnector',
    connector_credential_unavailable: 'sourceConnector',
  }
  return label(reasons[reason] || 'sourceUnavailable')
}
onMounted(refresh)
</script>

<template>
  <UiDialog :open="true" class="authority-dialog" :title="label('manage')" :close-label="label('close')" @update:open="!$event && close()">
    <div class="authority-body ui-stack" :aria-busy="busy">
      <div><h3>{{ name }}</h3><p class="ui-help">{{ label('consentHelp') }}</p></div>
      <p class="authority-native">{{ label('consentNative') }}</p>
      <p v-if="error" class="authority-error" role="alert">{{ label(error) }}</p>
      <p v-if="notice" class="authority-notice" role="status">{{ label(notice) }}</p>
      <p v-if="busy" class="ui-help" role="status">{{ label('consentLoading') }}</p>
      <template v-if="preview">
        <p class="authority-status" role="status">{{ label(savedLabel) }}</p>
        <p v-if="runtimeUnavailable" class="ui-help authority-runtime">{{ label('consentRuntime') }}</p>
        <section v-if="preview.unavailable_resources.length" class="ui-section ui-stack authority-unavailable" role="status">
          <h4>{{ label('optionalUnavailable') }}</h4>
          <p class="ui-help">{{ label('optionalUnavailableHelp') }}</p>
          <div v-for="resource in preview.unavailable_resources" :key="resource.scope">
            <strong>{{ scopeName(resource.scope) }}</strong>
            <p>{{ sourceReason(resource.reason) }}</p>
            <code>{{ resource.reason }}</code>
          </div>
        </section>
        <p class="ui-help">{{ selected.length }} / {{ preview.scopes.length }} {{ label('consentPermissions') }} · {{ selectedUser.length }} {{ label('consentYourPermissions') }}</p>
        <p v-if="expired" class="authority-error" role="alert">{{ label('consentExpired') }}</p>
        <details class="authority-details">
          <summary>{{ label('consentDetails') }}</summary>
          <div class="authority-choices ui-stack">
            <h4>{{ label('consentServicePermissions') }}</h4>
            <p v-if="relationalPair" class="ui-help authority-relational-profile">{{ label('consentRelationalProfile') }}</p>
            <label v-for="scope in preview.scopes" :key="scope" class="ui-check authority-scope-choice">
              <input type="checkbox" :value="scope" :checked="selected.includes(scope)" :disabled="busy || expired" @change="choose(scope, $event)" />
              <span>{{ scopeName(scope) }}</span>
            </label>
            <p v-if="!preview.scopes.length" class="ui-help">{{ label('empty') }}</p>
            <h4 v-if="preview.user_permissions.length">{{ label('consentYourAccess') }}</h4>
            <label v-for="permission in preview.user_permissions" :key="permission.permission_id" class="ui-check authority-user-choice">
              <input type="checkbox" :value="permission.permission_id" :checked="selectedUser.includes(permission.permission_id)" :disabled="busy || expired" @change="choose(permission.permission_id, $event, true)" />
              <span>{{ permission.name }} · <code>{{ permission.permission_id }}</code></span>
            </label>
          </div>
          <template v-for="kind in kinds" :key="kind">
            <section v-if="preview.resources[kind]?.length" class="authority-resources" :class="`authority-${kind}`">
              <h4>{{ label(kindLabels[kind]) }}</h4>
              <pre v-for="(resource, index) in preview.resources[kind]" :key="index">{{ JSON.stringify(resource, null, 2) }}</pre>
            </section>
          </template>
          <p class="ui-help authority-artifact">{{ label('digest') }} <code>{{ preview.artifact_sha256 }}</code></p>
        </details>
      </template>
      <section v-if="confirmRevoke" class="authority-revoke ui-stack" role="region" :aria-label="label('revokeTitle')">
        <h3>{{ label('revokeTitle') }}</h3><p>{{ label('revokeHelp') }}</p>
      </section>
    </div>
    <template #actions>
      <UiButton :disabled="busy" @click="close">{{ label('close') }}</UiButton>
      <template v-if="confirmRevoke">
        <UiButton :disabled="busy" @click="confirmRevoke = false">{{ label('cancel') }}</UiButton>
        <UiButton variant="danger" :disabled="!canRevoke" @click="revoke">{{ label('confirmRevoke') }}</UiButton>
      </template>
      <template v-else>
        <UiButton :disabled="busy" @click="refresh">{{ label('refresh') }}</UiButton>
        <UiButton v-if="canRevoke" variant="danger" @click="confirmRevoke = true">{{ label('revoke') }}</UiButton>
        <UiButton variant="primary" :disabled="!canAllow" :loading="busy" @click="allow">{{ label('consentAllow') }}</UiButton>
      </template>
    </template>
  </UiDialog>
</template>

<style scoped>
.ui-v2 .authority-dialog { width: min(720px, calc(100vw - 32px)); }
.authority-body { min-width: 0; }
h3, h4, p { margin: 0; }
h3 { margin-bottom: calc(var(--ui-space) * 2); overflow-wrap: anywhere; }
h4 { font-size: .95em; }
.authority-native, .authority-details, .authority-runtime { font-size: .9em; color: var(--ui-text-secondary); }
.authority-error { color: var(--ui-danger); }
.authority-notice, .authority-status { font-weight: 500; }
.authority-details summary { cursor: pointer; padding: calc(var(--ui-space) * 2) 0; }
.authority-choices, .authority-resources { margin-top: calc(var(--ui-space) * 4); }
.authority-scope-choice, .authority-user-choice { align-items: flex-start; overflow-wrap: anywhere; }
.authority-unavailable { overflow-wrap: anywhere; }
.authority-resources pre { background: var(--ui-surface-alt); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); padding: calc(var(--ui-space) * 3); white-space: pre-wrap; overflow-wrap: anywhere; max-height: 18rem; overflow: auto; font-size: .8em; }
.authority-artifact { margin-top: calc(var(--ui-space) * 4); overflow-wrap: anywhere; }
.authority-revoke { border-top: 1px solid var(--ui-danger); padding-top: calc(var(--ui-space) * 4); }
</style>
