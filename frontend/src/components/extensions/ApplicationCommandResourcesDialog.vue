<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiButton from '@/components/ui/UiButton.vue'
import http from '@/utils/dynamic-http'
import { authorityRequestId, readAuthorityStatus } from './authority-management'
import { useCommandResourceLabels } from './command-resource-labels'
import { readCommandConfiguration, readCommandDiscovery, readCommandRebindPreview, readCommandRebindStatus, readPendingRebind,
  type CommandBinding, type CommandCandidate, type CommandRebindPreview, type CommandRebindStatus } from './command-resources'

const props = defineProps<{ moduleId: string; name: string; packageSha: string }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const label = useCommandResourceLabels()
const base = `/api/v1/application-extensions/${encodeURIComponent(props.moduleId)}/authority/command-rebindings`
const packageBase = `/api/v1/application-extensions/packages/${encodeURIComponent(props.packageSha)}`
const bindings = ref<CommandBinding[]>([]), bindingId = ref(''), names = ref<Record<string, string>>({})
const candidates = ref<CommandCandidate[]>([]), currentDevice = ref<string | null>(null), selectedDevice = ref('')
const next = ref<string | null>(null), preview = ref<CommandRebindPreview | null>(null)
const outcome = ref<CommandRebindStatus | null>(null)
const eligible = ref(false), busy = ref(false), loaded = ref(false), uncertain = ref(false)
const approved = ref(false), recoveryApproved = ref(false)
const error = ref<ReturnType<typeof errorLabel> | null>(null)
const now = ref(Date.now())
let generation = 0, deadline = 0
const timer = setInterval(() => { now.value = Date.now() }, 1000)
onBeforeUnmount(() => { ++generation; clearInterval(timer) })
const binding = computed(() => bindings.value.find(item => item.binding_id === bindingId.value))
const expired = computed(() => !!preview.value && now.value >= deadline)
const pending = computed(() => outcome.value?.recovery_required === true)
const canChoose = computed(() => !busy.value && !pending.value && !uncertain.value && eligible.value)
const canReview = computed(() => canChoose.value && !!binding.value && selectedDevice.value !== currentDevice.value
  && candidates.value.some(item => item.device_id === selectedDevice.value && item.selectable))
const canApply = computed(() => canReview.value && !!preview.value && approved.value && !expired.value)
function clearReview() { preview.value = null; approved.value = false }
function errorLabel(cause: unknown) {
  const response = (cause as { response?: { status?: number; data?: { detail?: { code?: string } } } })?.response
  if (response?.status === 401 || response?.status === 403) return 'actor' as const
  if (['grant_not_current', 'installation_inactive'].includes(response?.data?.detail?.code || '')) return 'needsAccess' as const
  if (['binding_change_not_isolated', 'unsupported_authority'].includes(response?.data?.detail?.code || '')) return 'unsupported' as const
  return response?.status === 409 ? 'stale' as const : 'failed' as const
}
function deviceName(id: string | null) { return id ? names.value[id] || id : '—' }
function provider(item: CommandCandidate) { return [item.provider_id, item.provider_version].filter(Boolean).join(' · ') || '—' }

async function status(planId: string, current: number) {
  const response = await http.get(base + '/' + planId, { timeout: 12000 })
  const value = readCommandRebindStatus(response.data, props.moduleId, planId)
  if (current !== generation) return
  outcome.value = value; uncertain.value = false; recoveryApproved.value = false
}
async function fetchCandidates(current: number, more = false) {
  const requirement = binding.value
  if (!requirement) return
  const cursor = more ? next.value : null
  const response = await http.get(packageBase + `/command-bindings/${requirement.binding_id}/discovery`, {
    timeout: 12000, ...(cursor ? { params: { after_device_id: cursor } } : {}),
  })
  const value = readCommandDiscovery(response.data, requirement)
  if (current !== generation) return
  if (value.next_after_device_id && (value.next_after_device_id === cursor
    || cursor && value.next_after_device_id <= cursor)) throw new Error('Repeated device page')
  const merged = more ? [...candidates.value, ...value.candidates] : value.candidates
  if (new Set(merged.map(item => item.device_id)).size !== merged.length) throw new Error('Duplicate device page')
  if (more && value.selected_device_id !== currentDevice.value) clearReview()
  candidates.value = merged; next.value = value.next_after_device_id; currentDevice.value = value.selected_device_id
}
async function refresh() {
  if (busy.value) return
  busy.value = true; error.value = null; clearReview(); eligible.value = false
  const current = ++generation
  try {
    if (outcome.value) await status(outcome.value.preview_id, current)
    const pendingResponse = await http.get(base, { timeout: 12000 })
    const interrupted = readPendingRebind(pendingResponse.data, props.moduleId)
    if (current !== generation) return
    if (interrupted) {
      outcome.value = interrupted; uncertain.value = false; loaded.value = true; return
    }
    // Status by ID is historical. Another recovery/restore may have superseded
    // it; only the current pending observation offers a recovery action.
    if (outcome.value?.recovery_required) { outcome.value = null; recoveryApproved.value = false }
    // A failed status read never turns an uncertain mutation into another apply.
    if (uncertain.value) return
    const response = await http.get(packageBase + '/configuration', { timeout: 12000 })
    const configuration = readCommandConfiguration(response.data, props.moduleId)
    if (current !== generation) return
    bindings.value = configuration.bindings; names.value = configuration.names
    if (!bindings.value.some(item => item.binding_id === bindingId.value)) bindingId.value = bindings.value[0]?.binding_id || ''
    selectedDevice.value = ''; candidates.value = []; next.value = null
    if (binding.value) {
      const authority = await http.get(base.replace('/command-rebindings', ''), { timeout: 12000 })
      const actual = readAuthorityStatus(authority.data)
      if (current !== generation) return
      eligible.value = actual.artifact_sha256 === props.packageSha && actual.mode === 'enforced'
        && actual.installation_status === 'active' && actual.installation_enabled && actual.grant_effective
        && !actual.scopes.some(scope => scope.startsWith('storage:relational_'))
      await fetchCandidates(current)
    }
    if (current === generation) loaded.value = true
  } catch (cause) { if (current === generation) { error.value = errorLabel(cause); eligible.value = false } }
  finally { if (current === generation) busy.value = false }
}
async function changeBinding() {
  if (busy.value) return
  clearReview(); selectedDevice.value = ''; candidates.value = []; next.value = null; error.value = null
  busy.value = true
  const current = ++generation
  try { await fetchCandidates(current) }
  catch (cause) { if (current === generation) error.value = errorLabel(cause) }
  finally { if (current === generation) busy.value = false }
}
async function more() {
  if (busy.value || !next.value) return
  busy.value = true
  const current = generation
  try { await fetchCandidates(current, true) }
  catch (cause) { if (current === generation) { error.value = errorLabel(cause); next.value = null } }
  finally { if (current === generation) busy.value = false }
}
async function review() {
  if (!canReview.value || !binding.value) return
  clearReview(); error.value = null; busy.value = true
  const current = generation, started = Date.now()
  try {
    const response = await http.post(base, { request_id: authorityRequestId(), binding_id: binding.value.binding_id,
      device_id: selectedDevice.value }, { timeout: 12000 })
    const value = readCommandRebindPreview(response.data, props.moduleId, props.packageSha,
      binding.value, selectedDevice.value, currentDevice.value)
    if (current !== generation) return
    preview.value = value; deadline = started + value.expires_in_seconds * 1000; now.value = Date.now()
  } catch (cause) { if (current === generation) error.value = errorLabel(cause) }
  finally { if (current === generation) busy.value = false }
}
async function apply() {
  const plan = preview.value
  if (!plan || !canApply.value) return
  busy.value = true; error.value = null; uncertain.value = true; eligible.value = false
  const current = generation
  clearReview()
  // Retain the known plan even if the HTTP reply or status read is lost.
  outcome.value = { preview_id: plan.preview_id, revision: plan.revision, binding_id: bindingId.value,
    device_id: selectedDevice.value, state: 'applying', installation_status: 'unknown',
    installation_enabled: false, recovery_required: true }
  let mutationError: unknown
  try {
    await http.post(base + `/${plan.preview_id}/apply`, { request_id: authorityRequestId(),
      expected_revision: plan.revision, fingerprint: plan.fingerprint, approve_change: true }, { timeout: 90000 })
  } catch (cause) { mutationError = cause }
  if (current !== generation) return
  try {
    await status(plan.preview_id, current)
    if (current === generation) error.value = outcome.value?.state === 'preview' ? errorLabel(mutationError) : null
  }
  catch (cause) { if (current === generation) { uncertain.value = true; error.value = errorLabel(cause) === 'actor' ? 'actor' : null } }
  finally { if (current === generation) { busy.value = false; emit('changed') } }
}
async function recover() {
  const operation = outcome.value
  if (!operation || !pending.value || !recoveryApproved.value || busy.value || uncertain.value) return
  busy.value = true; error.value = null; recoveryApproved.value = false; uncertain.value = true
  const current = generation
  try {
    await http.post(base + `/${operation.preview_id}/recover`, { expected_revision: operation.revision,
      confirmed_external_outcome_reviewed: true }, { timeout: 60000 })
  } catch { /* Read the durable state below; never repeat recovery automatically. */ }
  if (current !== generation) return
  try { await status(operation.preview_id, current) }
  catch (cause) { if (current === generation) { uncertain.value = true; error.value = errorLabel(cause) === 'actor' ? 'actor' : null } }
  finally { if (current === generation) { busy.value = false; emit('changed') } }
}
function close() { if (!busy.value) emit('close') }
onMounted(refresh)
</script>

<template>
  <UiDialog class="command-resources-dialog" :open="true" :title="label('title')" :close-label="label('close')" @update:open="!$event && close()">
    <div class="command-resources ui-stack" :aria-busy="busy">
      <h3>{{ name }}</h3>
      <p v-if="!preview" class="ui-help">{{ label('help') }}</p>
      <p v-if="busy" role="status">{{ label('loading') }}</p>
      <p v-if="error" class="resource-error" role="alert">{{ label(error) }}</p>
      <p v-if="uncertain" class="resource-error" role="alert">{{ label('uncertain') }}</p>
      <template v-if="pending && !uncertain">
        <p role="status">{{ label('pending') }}</p>
        <p><strong>{{ outcome?.binding_id }}</strong> · {{ deviceName(outcome?.device_id || null) }}</p>
        <p class="ui-help">{{ label('external') }}</p>
        <label class="ui-check"><input v-model="recoveryApproved" type="checkbox" :disabled="busy" />{{ label('recoverAcknowledgment') }}</label>
        <UiButton variant="danger" :disabled="busy || !recoveryApproved" @click="recover">{{ label('recover') }}</UiButton>
      </template>
      <template v-if="!pending && !uncertain">
        <p v-if="outcome?.state === 'completed'" role="status">{{ label('completed') }}</p>
        <p v-if="outcome?.state === 'recovered_disabled'" role="status">{{ label('recovered') }}</p>
        <p v-if="loaded && !bindings.length && !outcome" class="ui-help">{{ label('empty') }}</p>
        <template v-if="bindings.length">
          <label v-if="!preview" class="ui-field">{{ label('binding') }}
            <select v-model="bindingId" class="ui-control" :disabled="busy" @change="changeBinding">
              <option v-for="item in bindings" :key="item.binding_id" :value="item.binding_id">{{ item.binding_id }}</option>
            </select>
          </label>
          <p v-if="binding" class="ui-help">{{ label('contract') }}: {{ binding.capability_id }} · {{ binding.contract_version }} · {{ binding.action }}</p>
          <p v-if="!eligible && !busy" class="ui-help">{{ label('needsAccess') }}</p>
          <p v-if="!preview">{{ label('current') }}: <strong>{{ deviceName(currentDevice) }}</strong></p>
          <fieldset v-if="!preview" class="resource-options" :disabled="!canChoose">
            <legend>{{ label('choose') }}</legend>
            <label v-for="item in candidates" :key="item.device_id" class="resource-option" :class="{ 'is-blocked': !item.selectable }">
              <input v-model="selectedDevice" type="radio" name="command-device" :value="item.device_id"
                :disabled="!item.selectable || item.device_id === currentDevice" @change="clearReview" />
              <span><strong>{{ deviceName(item.device_id) }}</strong><small>{{ provider(item) }}</small>
                <small>{{ item.device_id === currentDevice ? label('current') + ' · ' : '' }}{{ label(item.readiness) }}</small>
                <small v-if="!item.selectable">{{ label(item.compatible ? 'blocked' : 'incompatible') }}</small>
              </span>
            </label>
            <p v-if="!candidates.length && !busy" class="ui-help">{{ label('noCandidates') }}</p>
          </fieldset>
          <UiButton v-if="next && !preview" :disabled="busy" @click="more">{{ label('more') }}</UiButton>
          <UiButton v-if="!preview" :disabled="!canReview" @click="review">{{ label('review') }}</UiButton>
        </template>
        <section v-if="preview" class="resource-review ui-stack" aria-live="polite">
          <UiButton variant="quiet" :disabled="busy" @click="clearReview">{{ label('chooseAgain') }}</UiButton>
          <div class="resource-comparison">
            <div v-for="(item, index) in [preview.before_provider, preview.after_provider]" :key="index">
              <h4>{{ label(index === 0 ? 'before' : 'after') }}</h4>
              <strong>{{ deviceName(item.device_id) }}</strong><code>{{ item.device_id }}</code>
              <small>{{ label('provider') }}: {{ provider(item) }}</small>
              <small>{{ label(item.readiness) }}</small>
            </div>
          </div>
          <p>{{ label('restart') }}</p><p class="ui-help">{{ label('external') }}</p>
          <p v-if="expired" class="resource-error" role="alert">{{ label('expired') }}</p>
          <label class="ui-check"><input v-model="approved" type="checkbox" :disabled="busy || expired" />{{ label('acknowledge') }}</label>
          <UiButton variant="primary" :disabled="!canApply" @click="apply">{{ label('apply') }}</UiButton>
        </section>
      </template>
    </div>
    <template #actions>
      <UiButton :disabled="busy" @click="close">{{ label('close') }}</UiButton>
      <UiButton :disabled="busy" @click="refresh">{{ label('refresh') }}</UiButton>
    </template>
  </UiDialog>
</template>

<style scoped>
.ui-v2 .command-resources-dialog { width: min(720px, calc(100vw - 32px)); }
h3, h4, p { margin: 0; }
.command-resources { min-width: 0; max-width: 44rem; }
.resource-error { color: var(--ui-danger); }
.resource-options { min-width: 0; border: 0; padding: 0; margin: 0; }
.resource-options legend { font-weight: 600; margin-bottom: .5rem; }
.resource-option { display: flex; align-items: flex-start; gap: .75rem; padding: .75rem; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); margin-bottom: .5rem; }
.resource-option input { margin-top: .25rem; }
.resource-option small, .resource-comparison small, .resource-comparison code { display: block; overflow-wrap: anywhere; }
.resource-option small { color: var(--ui-text-secondary); }
.resource-option.is-blocked { opacity: .65; }
.resource-review { border-top: 1px solid var(--ui-border); padding-top: 1rem; }
.resource-comparison { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; }
.resource-comparison > div { padding: .75rem; background: var(--ui-surface-alt); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); overflow-wrap: anywhere; }
.resource-comparison h4 { margin-bottom: .5rem; }
.resource-comparison code { font-size: .75rem; margin: .25rem 0; }
@media (max-width: 540px) { .resource-comparison { grid-template-columns: 1fr; } }
</style>
