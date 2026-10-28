<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import { authorityRequestId } from './authority-management'
import { createConnectorSettingsClient, ConnectorSettingsError, type ConnectorSettings, type ConnectorSave, type ConnectorOutcome } from './connector-settings'
import { useConnectorSettingsLabels } from './connector-settings-labels'

const props = defineProps<{ packageSha: string; name: string }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const label = useConnectorSettingsLabels(), client = createConnectorSettingsClient(props.packageSha)
const data = ref<ConnectorSettings | null>(null), connectorId = ref(''), origin = ref(''), mode = ref('create'), secretRef = ref('')
const credentialLabel = ref(''), username = ref(''), password = ref(''), header = ref('X-API-Key')
const action = ref<ConnectorSave['action']>('save'), confirmed = ref(false), busy = ref(false), message = ref(''), applied = ref(false)
const pending = ref<string | null>(null)
const rejected = ref<string | null>(null), storageFault = ref(false)
const pendingKey = `3mm.connector-settings.pending:${props.packageSha}`
let disposed = false
const connector = computed(() => data.value?.connectors.find(c => c.connector_id === connectorId.value))
const credentials = computed(() => data.value?.credentials.filter(c => !c.revoked && c.authentication === connector.value?.authentication) ?? [])
const needsCredential = computed(() => connector.value?.authentication !== 'none' && (mode.value === 'create' || action.value === 'rotate'))
const canSave = computed(() => !!connector.value && !busy.value && !pending.value && !storageFault.value && !!origin.value.trim()
  && (connector.value.authentication === 'none' || data.value?.encryption_available
    && (mode.value === 'existing' ? !!secretRef.value : !!credentialLabel.value.trim() && !!password.value.trim()
      && (connector.value.authentication !== 'basic' || !!username.value.trim())
      && (connector.value.authentication !== 'api_key' || /^x-[a-z0-9-]+$/i.test(header.value)))))
const canConfirm = computed(() => !busy.value && !pending.value && !storageFault.value && confirmed.value && connector.value?.credential
  && (action.value === 'revoke' || data.value?.encryption_available && !!password.value.trim()
    && (connector.value.authentication !== 'basic' || !!username.value.trim())
    && (connector.value.authentication !== 'api_key' || /^x-[a-z0-9-]+$/i.test(header.value))))
const errorLabels = { access_denied: 'actor', invalid_request: 'invalid', conflict: 'stale',
  unavailable: 'failed', unconfirmed: 'uncertain', stop_required: 'stopFirst' } as const
const errorLabel = computed(() => errorLabels[message.value as keyof typeof errorLabels] ?? 'failed')

function clearCredential() { username.value = ''; password.value = ''; credentialLabel.value = ''; header.value = 'X-API-Key' }
function choose() {
  clearCredential(); action.value = 'save'; confirmed.value = false; applied.value = false
  origin.value = connector.value?.destination_origin ?? ''
  secretRef.value = connector.value?.credential?.revoked ? '' : connector.value?.credential?.secret_ref ?? ''
  mode.value = secretRef.value ? 'existing' : 'create'
}
async function load() {
  const result = await client.inspect()
  if (disposed) return
  data.value = result
  if (!result.connectors.some(c => c.connector_id === connectorId.value)) connectorId.value = result.connectors[0]?.connector_id ?? ''
  choose()
}
function persistPending() { sessionStorage.setItem(pendingKey, JSON.stringify({ request_id: pending.value, rejected: rejected.value })) }
function clearPending() { sessionStorage.removeItem(pendingKey); pending.value = null; rejected.value = null }
async function applyOutcome(result: ConnectorOutcome) {
  if (disposed) return
  if (result.status === 'unknown') {
    // Only a definite pre-dispatch refusal or recognised Core rejection of this
    // attempt resolves unknown. A bare conflict or lost/malformed reply does not.
    if (rejected.value) {
      const code = rejected.value
      clearPending(); await load()
      if (!disposed) message.value = code
    }
    return
  }
  clearPending(); clearCredential(); action.value = 'save'; confirmed.value = false
  emit('changed')
  await load()
  if (!disposed) { applied.value = true; message.value = '' }
}
async function check() {
  if (!pending.value || busy.value) return
  busy.value = true; message.value = ''
  try { await applyOutcome(await client.outcome(pending.value)) }
  catch (error) { if (!disposed) message.value = error instanceof ConnectorSettingsError ? error.code : 'unavailable' }
  finally { if (!disposed) busy.value = false }
}
async function refresh() {
  if (pending.value) { await check(); return }
  if (busy.value) return
  busy.value = true; message.value = ''; applied.value = false
  try { await load() }
  catch (error) { if (!disposed) message.value = error instanceof ConnectorSettingsError ? error.code : 'unavailable' }
  finally { if (!disposed) busy.value = false }
}
function changeAction(next: 'rotate' | 'revoke') {
  clearCredential(); action.value = next; confirmed.value = false; applied.value = false
}
function credential(): Record<string, string> {
  return connector.value?.authentication === 'basic' ? { username: username.value, password: password.value }
    : connector.value?.authentication === 'api_key' ? { header: header.value, value: password.value }
      : { token: password.value }
}
async function save() {
  const current = connector.value
  if (!current || (action.value === 'save' ? !canSave.value : !canConfirm.value) || !data.value) return
  const request: ConnectorSave = { request_id: authorityRequestId(), expected_snapshot: data.value.snapshot, action: action.value }
  if (action.value === 'save') {
    request.destination_origin = origin.value.trim()
    if (current.authentication !== 'none') {
      if (mode.value === 'create') Object.assign(request, { create_credential: true, credential_label: credentialLabel.value, credential: credential() })
      else request.secret_ref = secretRef.value
    }
  } else {
    request.secret_ref = current.credential!.secret_ref
    request.confirm_credential_change = true
    if (action.value === 'rotate') request.credential = credential()
  }
  busy.value = true; message.value = ''; applied.value = false
  try {
    // Persist only the request identity BEFORE sending. Never persist the draft,
    // credentials or a digest of them. A reopened dialog looks up this outcome.
    pending.value = request.request_id
    rejected.value = null
    persistPending()
  } catch {
    pending.value = null; storageFault.value = true
    busy.value = false; message.value = 'unavailable'; return
  }
  clearCredential()
  try { await applyOutcome(await client.save(current.connector_id, request)) }
  catch (error) {
    const code = error instanceof ConnectorSettingsError ? error.code : 'unconfirmed'
    if (!disposed) {
      message.value = code
      if (error instanceof ConnectorSettingsError && error.rejected) {
        rejected.value = code
        try { persistPending() } catch { /* Keep the identity and rejection in memory. */ }
      }
      // Even a conflict may refer to an earlier committed write. Always inspect
      // the original receipt; a network/unknown result never unlocks another Save.
      try {
        const result = await client.outcome(request.request_id)
        await applyOutcome(result)
      } catch { /* Keep the pending identity for explicit lookup after re-login. */ }
    }
  } finally { request.credential = undefined; if (!disposed) busy.value = false }
}
function close() { if (!busy.value) { clearCredential(); emit('close') } }
onMounted(async () => {
  try {
    const saved = sessionStorage.getItem(pendingKey)
    if (saved) {
      const record = JSON.parse(saved)
      if (!record || !/^[a-f0-9]{32}$/.test(record.request_id)
        || !(record.rejected === null || ['access_denied', 'invalid_request', 'conflict', 'unavailable', 'stop_required'].includes(record.rejected))) throw new Error()
      pending.value = record.request_id; rejected.value = record.rejected
    }
  } catch { storageFault.value = true; message.value = 'unavailable' }
  if (pending.value) await check()
  else await refresh()
  if (storageFault.value) message.value = 'unavailable'
})
onBeforeUnmount(() => { disposed = true; clearCredential() })
</script>

<template>
  <UiDialog :open="true" :title="label('title')" :close-label="label('close')" class="connector-settings-dialog" @update:open="close">
    <div class="ui-stack connector-settings-body">
      <p class="connector-app-name">{{ name }}</p>
      <p class="ui-help">{{ label('help') }}</p>
      <p v-if="busy" role="status">{{ label('loading') }}</p>
      <p v-if="message" class="connector-error" role="alert">{{ label(errorLabel) }}</p>
      <p v-if="applied" class="connector-saved" role="status">{{ label('applied') }}</p>
      <section v-if="pending" class="ui-section ui-stack connector-pending" role="status">
        <p>{{ label('uncertain') }}</p><p>{{ label('request') }}: <code>{{ pending }}</code></p>
        <UiButton :disabled="busy" @click="check">{{ label('check') }}</UiButton>
      </section>
      <template v-else-if="data && connector">
        <label class="ui-field">{{ label('connector') }}
          <select v-model="connectorId" class="ui-control" :disabled="busy" @change="choose">
            <option v-for="item in data.connectors" :key="item.connector_id" :value="item.connector_id">{{ item.connector_id }}</option>
          </select>
        </label>
        <p role="status">{{ label(connector.state) }} · {{ connector.authentication }}</p>
        <p class="ui-help">{{ label('path') }}: <code>{{ connector.path_prefix }}</code> · {{ connector.allowed_schemes.join(', ') }}</p>
        <p v-if="!data.encryption_available && connector.authentication !== 'none'" class="connector-error" role="alert">{{ label('key') }}</p>
        <form class="ui-stack" autocomplete="off" @submit.prevent="save">
          <template v-if="action === 'save'">
            <label class="ui-field">{{ label('origin') }}
              <input v-model="origin" class="ui-control connector-origin" type="url" :disabled="busy" required placeholder="https://example.com" />
            </label>
            <template v-if="connector.authentication !== 'none'">
              <label class="ui-field">{{ label('credential') }}
                <select v-model="mode" class="ui-control connector-credential-mode" :disabled="busy" @change="clearCredential">
                  <option value="create">{{ label('create') }}</option><option value="existing">{{ label('existing') }}</option>
                </select>
              </label>
              <label v-if="mode === 'existing'" class="ui-field">{{ label('choose') }}
                <select v-model="secretRef" class="ui-control connector-existing" :disabled="busy" required>
                  <option value="">{{ label('choose') }}</option>
                  <option v-for="item in credentials" :key="item.secret_ref" :value="item.secret_ref">{{ item.label }} · v{{ item.version }}</option>
                </select>
              </label>
              <label v-else class="ui-field">{{ label('label') }}
                <input v-model="credentialLabel" class="ui-control connector-label" :disabled="busy" maxlength="120" required />
              </label>
            </template>
          </template>
          <template v-else>
            <h3>{{ label(action) }}</h3>
            <p>{{ label('affected') }}: {{ connector.affected_connector_ids.join(', ') }}</p>
            <label class="ui-check"><input v-model="confirmed" class="connector-confirm" type="checkbox" :disabled="busy" /> {{ label('confirm') }}</label>
          </template>
          <template v-if="needsCredential && action !== 'revoke'">
            <label v-if="connector.authentication === 'basic'" class="ui-field">{{ label('username') }}
              <input v-model="username" class="ui-control connector-username" :disabled="busy" autocomplete="off" maxlength="4096" required />
            </label>
            <label v-if="connector.authentication === 'api_key'" class="ui-field">{{ label('header') }}
              <input v-model="header" class="ui-control connector-api-header" :disabled="busy" maxlength="128" required />
            </label>
            <label class="ui-field">{{ label(connector.authentication === 'basic' ? 'password' : 'token') }}
              <input v-model="password" class="ui-control connector-password" type="password" :disabled="busy" autocomplete="new-password" maxlength="4096" required />
            </label>
          </template>
          <p class="ui-help">{{ label('access') }}</p>
          <div class="connector-actions">
            <UiButton v-if="action === 'save'" type="submit" variant="primary" :disabled="!canSave" class="connector-save">{{ label('save') }}</UiButton>
            <template v-else>
              <UiButton type="button" :disabled="busy" @click="choose">{{ label('cancel') }}</UiButton>
              <UiButton type="submit" :variant="action === 'revoke' ? 'danger' : 'primary'" :disabled="!canConfirm" class="connector-apply-credential">{{ label(action === 'revoke' ? 'confirmRevoke' : 'confirmRotate') }}</UiButton>
            </template>
          </div>
        </form>
        <div v-if="connector.credential && action === 'save'" class="connector-actions">
          <UiButton :disabled="busy || !data.encryption_available" class="connector-rotate" @click="changeAction('rotate')">{{ label('rotate') }}</UiButton>
          <UiButton variant="danger" :disabled="busy || connector.credential.revoked" class="connector-revoke" @click="changeAction('revoke')">{{ label('revoke') }}</UiButton>
        </div>
      </template>
      <p v-else-if="data">{{ label('empty') }}</p>
    </div>
    <template #actions>
      <UiButton :disabled="busy" @click="close">{{ label('close') }}</UiButton>
      <UiButton v-if="!pending" :disabled="busy" @click="refresh">{{ label('refresh') }}</UiButton>
    </template>
  </UiDialog>
</template>

<style scoped>
.connector-settings-dialog { width: min(640px, calc(100vw - 32px)); }
.connector-settings-body { min-width: 0; }
.connector-app-name { font-weight: var(--ui-font-weight-heading); overflow-wrap: anywhere; }
.connector-error { color: var(--ui-danger, #b42318); }
.connector-actions { display: flex; flex-wrap: wrap; gap: var(--ui-space-2, 8px); }
.connector-pending code { overflow-wrap: anywhere; }
</style>
