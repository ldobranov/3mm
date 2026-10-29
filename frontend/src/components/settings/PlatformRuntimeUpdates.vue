<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'

const props = withDefaults(defineProps<{ maintenanceOverrideRequired?: boolean }>(), { maintenanceOverrideRequired: false })
const { t } = useI18n()
const text = (key: string, fallback: string) => t('runtimeUpdates.' + key, fallback)
type Operation = { request_id: string; action: string; state: string; reason: string | null; updated_at: number }
type Candidate = { candidate_id: string; build_id: string; sha256: string; bytes: number; compatible: boolean; features: Record<string, number | null> }
type Status = { current_build_id: string | null; previous_build_id: string | null; ready: boolean;
  recovery_required: boolean; features: Record<string, number | null>; reason: string | null; candidate: Candidate | null; operation: Operation | null }
const status = ref<Status | null>(null)
const loading = ref(false), sending = ref(false), unconfirmed = ref(false)
const error = ref(''), requestId = ref('')
const visibleRequestId = computed(() => requestId.value || status.value?.operation?.request_id || '')
const confirm = ref<'apply' | 'recover' | null>(null)
const acknowledged = ref(false), maintenanceOverride = ref(false)
const reviewedCandidate = ref<Candidate | null>(null), reviewedOperation = ref<string | null>(null)
const reviewInvalidated = ref(false)
const busyStates = ['queued', 'preparing', 'applying', 'recovering']
const busy = computed(() => sending.value || !!status.value?.operation && busyStates.includes(status.value.operation.state))
const recovery = computed(() => status.value?.recovery_required || status.value?.operation?.state === 'recovery_required')
const canPrepare = computed(() => !!status.value?.current_build_id && !busy.value && !unconfirmed.value && !recovery.value)
const canApply = computed(() => !!status.value?.candidate?.compatible && status.value.candidate.build_id !== status.value.current_build_id && canPrepare.value)
const reviewActionAvailable = computed(() => confirm.value === 'apply' ? canApply.value
  : confirm.value === 'recover' && !!recovery.value && !busy.value && !unconfirmed.value)
const reviewCurrent = computed(() => !reviewInvalidated.value && reviewedOperation.value === (status.value?.operation?.request_id ?? null)
  && (confirm.value !== 'apply' || !!reviewedCandidate.value
    && reviewedCandidate.value.candidate_id === status.value?.candidate?.candidate_id
    && reviewedCandidate.value.build_id === status.value?.candidate?.build_id
    && reviewedCandidate.value.sha256 === status.value?.candidate?.sha256))
const features = ['query_execution_contract', 'connector_execution_contract', 'application_response_contract', 'event_delivery_contract']
const featureNames: Record<string, string> = { query_execution_contract: 'Application queries',
  connector_execution_contract: 'External connectors', application_response_contract: 'Application replies', event_delivery_contract: 'Event delivery' }
let live = true, timer: ReturnType<typeof setTimeout> | null = null, polls = 0

function decode(value: unknown): Status {
  const s = value as Status
  const hash = (v: unknown) => typeof v === 'string' && /^[0-9a-f]{64}$/.test(v)
  if (!s || typeof s.ready !== 'boolean' || typeof s.recovery_required !== 'boolean' || !s.features || typeof s.features !== 'object'
    || s.current_build_id !== null && !hash(s.current_build_id)
    || s.previous_build_id !== null && !hash(s.previous_build_id)
    || s.candidate && (!hash(s.candidate.build_id) || !hash(s.candidate.sha256)
      || !/^[0-9a-f]{32}$/.test(s.candidate.candidate_id) || typeof s.candidate.compatible !== 'boolean')
    || s.operation && (!/^[0-9a-f]{32}$/.test(s.operation.request_id)
      || ![...busyStates, 'succeeded', 'failed', 'recovery_required'].includes(s.operation.state))) {
    throw new Error('Invalid Runtime status')
  }
  return s
}

function schedule() {
  if (timer) clearTimeout(timer)
  timer = null
  if (live && (busy.value || unconfirmed.value) && polls < 40) {
    timer = setTimeout(() => { polls += 1; void refresh() }, 3000)
  }
}

async function refresh() {
  if (loading.value) return
  loading.value = true
  try {
    const response = await http.get('/api/v1/system-updates/runtime')
    if (!live) return
    status.value = decode(response.data)
    error.value = ''
    if (requestId.value && status.value.operation?.request_id === requestId.value) unconfirmed.value = false
    // A refreshed denial consumes the acknowledgement even if eligibility later
    // returns. A new review is explicit; sending/unknown outcomes are not retries.
    if (confirm.value && !sending.value && !unconfirmed.value
      && (!reviewCurrent.value || !reviewActionAvailable.value)) {
      reviewInvalidated.value = true
      acknowledged.value = false
      maintenanceOverride.value = false
    }
  } catch {
    if (live) error.value = text('unavailable', 'Runtime status is unavailable. Other Core administration remains available.')
  } finally {
    loading.value = false
    schedule()
  }
}

function newId() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('')
}

function openConfirmation(action: 'apply' | 'recover') {
  reviewInvalidated.value = false
  acknowledged.value = false
  maintenanceOverride.value = false
  reviewedCandidate.value = status.value?.candidate ? { ...status.value.candidate } : null
  reviewedOperation.value = status.value?.operation?.request_id ?? null
  confirm.value = action
}

async function submit(action: 'prepare' | 'apply' | 'recover') {
  if (sending.value || !status.value || unconfirmed.value) return
  if (action === 'prepare' && !canPrepare.value || action === 'apply' && !canApply.value
    || action === 'recover' && (!recovery.value || busy.value)) return
  if (action !== 'prepare' && (!acknowledged.value
    || !reviewCurrent.value || action === 'apply' && props.maintenanceOverrideRequired && !maintenanceOverride.value)) return
  sending.value = true
  error.value = ''
  polls = 0
  let dispatched = false
  try {
    requestId.value = newId() // Works on LAN HTTP; never Math.random or an automatic retry.
    const payload: Record<string, unknown> = { request_id: requestId.value,
      expected_operation_id: action === 'prepare' ? status.value.operation?.request_id ?? null : reviewedOperation.value }
    if (action === 'apply') {
      const candidate = reviewedCandidate.value!
      Object.assign(payload, { candidate_id: candidate.candidate_id, build_id: candidate.build_id,
        confirmation: 'UPDATE RUNTIME ' + candidate.build_id,
        maintenance_override: props.maintenanceOverrideRequired && maintenanceOverride.value })
    }
    dispatched = true
    await http.post('/api/v1/system-updates/runtime/' + action, payload)
    if (live) { confirm.value = null; unconfirmed.value = true }
  } catch {
    if (live) {
      unconfirmed.value = dispatched
      error.value = text('unconfirmed', 'Outcome unconfirmed. Keep the request ID and read status; do not resend.')
    }
  } finally {
    sending.value = false
    if (live && dispatched) await refresh()
  }
}

function reason(code: string | null) {
  const labels: Record<string, string> = {
    candidate_prepared: 'Candidate prepared; the running Runtime has not changed.',
    runtime_updated: 'Runtime updated and checked; Core stayed running.',
    runtime_recovered: 'Runtime recovery checked. The update was not replayed.',
    preparation_failed: 'Preparation failed. No Runtime switch was requested.',
    previous_runtime_ready: 'The operation failed; the previous Runtime is confirmed ready.',
    runtime_outcome_unconfirmed: 'Runtime outcome is unconfirmed. Explicit recovery is required.',
    worker_interrupted: 'The worker stopped before confirming completion. Do not repeat the update.',
  }
  return code ? text('reason.' + code, labels[code] || code) : ''
}

function stateName(state: string) {
  const labels: Record<string, string> = { queued: 'Queued', preparing: 'Preparing', applying: 'Updating',
    recovering: 'Recovering', succeeded: 'Succeeded', failed: 'Failed', recovery_required: 'Recovery required' }
  return text('state.' + state, labels[state] || state)
}

onMounted(() => { void refresh() })
onUnmounted(() => { live = false; if (timer) clearTimeout(timer) })
</script>

<template>
  <section class="runtime-updates card ui-v2" aria-labelledby="runtime-updates-title">
    <header>
      <div><h2 id="runtime-updates-title">{{ text('title', 'Platform Runtime') }}</h2>
        <p>{{ text('help', 'Independent component. Preparation uses only this installed Core release; no downloads or dependency installation.') }}</p></div>
      <UiButton :disabled="loading || sending" @click="refresh">{{ text('refresh', 'Refresh status') }}</UiButton>
    </header>
    <p>{{ text('boundary', 'Only Platform Runtime is switched. SDK connections may briefly stop. Core, application-host pins and application rights are not updated.') }}</p>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="unconfirmed" role="alert">{{ text('unconfirmed', 'Outcome unconfirmed. Keep the request ID and read status; do not resend.') }}</p>
    <p v-if="visibleRequestId">{{ text('requestId', 'Preserve request ID:') }} <code>{{ visibleRequestId }}</code></p>
    <template v-if="status">
      <dl>
        <dt>{{ text('current', 'Current build') }}</dt><dd><code>{{ status.current_build_id || '—' }}</code></dd>
        <dt>{{ text('previous', 'Previous build') }}</dt><dd><code>{{ status.previous_build_id || '—' }}</code></dd>
        <dt>{{ text('health', 'Live readiness') }}</dt><dd>{{ status.ready ? text('ready', 'Ready') : text('notReady', 'Not confirmed') }}</dd>
        <template v-for="feature in features" :key="feature"><dt>{{ text('feature.' + feature, featureNames[feature]!) }}</dt>
          <dd>{{ status.features[feature] ?? text('notAdvertised', 'Not advertised') }}</dd></template>
      </dl>
      <p v-if="status.operation" role="status">{{ text('operation', 'Operation') }}: {{ stateName(status.operation.state) }} · {{ reason(status.operation.reason) }}</p>
      <div v-if="status.candidate" class="candidate">
        <h3>{{ text('candidate', 'Prepared candidate') }}</h3>
        <code>{{ status.candidate.build_id }}</code>
        <p>SHA-256: <code>{{ status.candidate.sha256 }}</code></p>
        <p>{{ text('declared', 'Candidate features below are declarations, not a live health proof.') }}</p>
        <dl><template v-for="feature in features" :key="feature"><dt>{{ text('feature.' + feature, featureNames[feature]!) }}</dt>
          <dd>{{ status.candidate.features[feature] ?? text('notDeclared', 'Not declared in the Core contract') }}</dd></template></dl>
        <p v-if="status.candidate.build_id === status.current_build_id">{{ text('same', 'This prepared build is already the current Runtime. No update is needed.') }}</p>
        <p v-else-if="!status.candidate.compatible">{{ text('stale', 'Core or Runtime changed after preparation. Prepare a fresh candidate.') }}</p>
        <p v-else>{{ text('compatible', 'Candidate matches the current Core and Runtime selection. Activation still needs separate approval.') }}</p>
      </div>
      <div class="actions">
        <UiButton :disabled="!canPrepare" @click="submit('prepare')">{{ text('prepare', 'Prepare from installed Core') }}</UiButton>
        <UiButton variant="primary" :disabled="!canApply" @click="openConfirmation('apply')">{{ text('update', 'Review Runtime update') }}</UiButton>
        <UiButton v-if="recovery" :disabled="busy || unconfirmed" @click="openConfirmation('recover')">{{ text('recover', 'Review interrupted-operation recovery') }}</UiButton>
      </div>
    </template>
    <p v-else-if="loading" role="status">{{ text('loading', 'Reading Runtime status…') }}</p>
    <UiDialog :open="confirm !== null" :title="text('confirmTitle', 'Confirm Runtime operation')" :close-label="text('close', 'Close')" @update:open="value => { if (!value && !sending) confirm = null }">
      <p>{{ confirm === 'apply' ? text('confirmUpdate', 'Switch only Runtime to this exact prepared build. Failure must leave a verified previous Runtime or an explicit recovery-required result.') : text('confirmRecovery', 'Reconcile the interrupted transaction and check Runtime. This may restart Runtime but never replays the requested update or an application operation.') }}</p>
      <code v-if="confirm === 'apply'">{{ reviewedCandidate?.build_id }}</code>
      <p v-if="!reviewCurrent" role="alert">{{ text('reviewChanged', 'The reviewed state changed. Close and review it again.') }}</p>
      <label class="check"><input v-model="acknowledged" type="checkbox" :disabled="sending">{{ text('acknowledge', 'I reviewed the exact component and temporary connection interruption.') }}</label>
      <label v-if="confirm === 'apply' && maintenanceOverrideRequired" class="check"><input v-model="maintenanceOverride" type="checkbox" :disabled="sending">{{ text('override', 'I explicitly approve updating outside the maintenance window.') }}</label>
      <template #actions>
        <UiButton :disabled="sending" @click="confirm = null">{{ text('close', 'Close') }}</UiButton>
        <UiButton variant="primary" :disabled="sending || !acknowledged || !reviewCurrent || !reviewActionAvailable || confirm === 'apply' && maintenanceOverrideRequired && !maintenanceOverride"
          @click="submit(confirm === 'apply' ? 'apply' : 'recover')">{{ text('confirm', 'Confirm once') }}</UiButton>
      </template>
    </UiDialog>
  </section>
</template>

<style scoped>
.runtime-updates { padding: 1.25rem; margin-block: 1.25rem; min-width: 0; background: var(--ui-surface); color: var(--ui-text); }
header, .actions { display: flex; align-items: start; justify-content: space-between; gap: .8rem; flex-wrap: wrap; }
header p, p { color: var(--ui-text-secondary); }
.runtime-updates > :not(:first-child) { margin-top: 1rem; }
header > div { flex: 1 1 20rem; min-width: 0; }
header p { margin-top: .5rem; }
dl { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); gap: .55rem 1rem; }
dd { margin: 0; min-width: 0; }
code { overflow-wrap: anywhere; white-space: pre-wrap; color: var(--ui-text); }
.candidate { border-block: 1px solid var(--ui-border); margin-block: 1rem; padding-block: .8rem; }
.candidate > :not(:first-child) { margin-top: .65rem; }
.check { display: flex; gap: .6rem; align-items: start; margin-block: 1rem; }
.error { color: var(--ui-danger); }
@media (max-width: 600px) { dl { grid-template-columns: minmax(0, 1fr); } dt { font-weight: 600; } dd { margin-bottom: .7rem; } }
</style>
