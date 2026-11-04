<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, useId } from 'vue'
import { UiButton, UiField } from '@/extension-ui/v1'
import UiDialog from '@/components/ui/UiDialog.vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'

const props = withDefaults(defineProps<{ maintenanceOverrideRequired?: boolean }>(), { maintenanceOverrideRequired: false })
const { t } = useI18n(), prefix = useId()
const text = (key: string, fallback: string) => t('componentUpdates.' + key, fallback)
type Target = { component: 'agent' | 'application_host'; target_id: string; label: string }
type Candidate = { candidate_id: string; build_id: string; sha256: string; bytes: number; compatible: boolean }
type Operation = { request_id: string; component: Target['component']; target_id: string; state: string; reason: string | null }
type Status = { component: Target['component']; target_id: string; current_build_id: string | null; previous_build_id: string | null;
  ready: boolean; recovery_required: boolean; candidate: Candidate | null; operation: Operation | null }
type Action = 'apply' | 'rollback' | 'recover'
const base = '/api/v1/system-updates/components', storage = '3mm-component-update-pending'
const targets = ref<Target[]>([]), selection = ref(''), status = ref<Status | null>(null)
const loading = ref(false), sending = ref(false), error = ref(''), unknown = ref(false), requestId = ref('')
const dialog = ref<Action | null>(null), acknowledged = ref(false), override = ref(false), invalidated = ref(false)
const reviewed = ref<{ build: string | null; sha: string | null; candidate: string | null; operation: string | null; current: string | null } | null>(null)
const busyStates = ['queued', 'preparing', 'applying', 'recovering']
const key = (target: Pick<Target, 'component' | 'target_id'>) => target.component + '/' + target.target_id
const selected = computed(() => targets.value.find(target => key(target) === selection.value))
const busy = computed(() => sending.value || !!status.value?.operation && busyStates.includes(status.value.operation.state))
const idle = computed(() => !!status.value && !busy.value && !unknown.value && !status.value.recovery_required && status.value.ready)
const canApply = computed(() => idle.value && status.value?.candidate?.compatible && status.value.candidate.build_id !== status.value.current_build_id)
const canRollback = computed(() => idle.value && !!status.value?.previous_build_id && status.value.previous_build_id !== status.value.current_build_id)
const canRecover = computed(() => !busy.value && !unknown.value && status.value?.recovery_required &&
  (!status.value.operation || key(status.value.operation) === selection.value))
const eligible = computed(() => dialog.value === 'apply' ? canApply.value : dialog.value === 'rollback' ? canRollback.value : canRecover.value)
const reviewCurrent = computed(() => !invalidated.value && !!reviewed.value && reviewed.value.operation === (status.value?.operation?.request_id ?? null)
  && reviewed.value.current === status.value?.current_build_id
  && (dialog.value !== 'apply' || reviewed.value.candidate === status.value?.candidate?.candidate_id && reviewed.value.sha === status.value?.candidate?.sha256 && reviewed.value.build === status.value?.candidate?.build_id)
  && (dialog.value !== 'rollback' || reviewed.value.build === status.value?.previous_build_id))
let live = true, generation = 0, polls = 0, timer: ReturnType<typeof setTimeout> | null = null
const hash = (v: unknown, length = 64) => typeof v === 'string' && new RegExp('^[0-9a-f]{' + length + '}$').test(v)
function validTarget(v: Pick<Target, 'component' | 'target_id'>) { return !!v && (v.component === 'agent' && v.target_id === 'local' || v.component === 'application_host' && hash(v.target_id, 24)) }
function decode(value: unknown, target: Target): Status {
  const s = value as Status
  if (!s || key(s) !== key(target) || typeof s.ready !== 'boolean' || typeof s.recovery_required !== 'boolean'
    || s.current_build_id !== null && !hash(s.current_build_id) || s.previous_build_id !== null && !hash(s.previous_build_id)
    || s.candidate && (!hash(s.candidate.candidate_id, 32) || !hash(s.candidate.build_id) || !hash(s.candidate.sha256)
      || !Number.isSafeInteger(s.candidate.bytes) || s.candidate.bytes < 1 || typeof s.candidate.compatible !== 'boolean')
    || s.operation && (!validTarget(s.operation) || !hash(s.operation.request_id, 32)
      || ![...busyStates, 'succeeded', 'failed', 'recovery_required'].includes(s.operation.state))) throw new Error('Invalid component status')
  return s
}
function schedule() {
  if (timer) clearTimeout(timer)
  timer = null
  if (live && (busy.value || unknown.value) && polls < 40) timer = setTimeout(() => { polls++; void refresh() }, 3000)
}
async function refresh() {
  if (loading.value || !selected.value) return
  const target = { ...selected.value }, currentGeneration = generation
  loading.value = true
  try {
    const result = await http.get(base + '/' + key(target))
    if (!live || currentGeneration !== generation) return
    status.value = decode(result.data, target); error.value = ''
    if (requestId.value && status.value.operation?.request_id === requestId.value) {
      unknown.value = false
      if (!busyStates.includes(status.value.operation.state)) sessionStorage.removeItem(storage)
    }
    if (dialog.value && !sending.value && (!reviewCurrent.value || !eligible.value)) {
      invalidated.value = true; acknowledged.value = false; override.value = false
    }
  } catch { if (live && currentGeneration === generation) error.value = text('unavailable', 'Component status is unavailable. Other administration remains available.') }
  finally { loading.value = false; schedule() }
}
async function load() {
  loading.value = true
  try {
    const result = await http.get(base + '/targets')
    if (!live) return
    const items = result.data.targets as Target[]
    if (!Array.isArray(items) || items.length > 129 || items.some(v => !validTarget(v) || typeof v.label !== 'string')) throw new Error()
    targets.value = items
    const pending = JSON.parse(sessionStorage.getItem(storage) || 'null')
    if (pending && hash(pending.request_id, 32) && items.some(v => key(v) === pending.target)) {
      selection.value = pending.target; requestId.value = pending.request_id; unknown.value = true
    } else selection.value = items[0] ? key(items[0]) : ''
  } catch { if (live) error.value = text('unavailable', 'Component status is unavailable. Other administration remains available.') }
  finally { loading.value = false; if (live) await refresh() }
}
async function changeTarget(value: unknown) {
  if (busy.value || unknown.value || loading.value) return
  selection.value = String(value); generation++; status.value = null; requestId.value = ''; dialog.value = null; polls = 0
  await refresh()
}
function review(action: Action) {
  acknowledged.value = false; override.value = false; invalidated.value = false
  reviewed.value = { build: action === 'rollback' ? status.value?.previous_build_id ?? null : status.value?.candidate?.build_id ?? null,
    sha: status.value?.candidate?.sha256 ?? null, candidate: status.value?.candidate?.candidate_id ?? null,
    operation: status.value?.operation?.request_id ?? null, current: status.value?.current_build_id ?? null }
  dialog.value = action
}
async function submit(action: Action | 'prepare') {
  if (!selected.value || !status.value || sending.value || unknown.value || action === 'prepare' && !idle.value) return
  if (action !== 'prepare' && (dialog.value !== action || !eligible.value || !reviewCurrent.value || !acknowledged.value
      || action !== 'recover' && props.maintenanceOverrideRequired && !override.value)) return
  let dispatched = false, refused = false
  sending.value = true; error.value = ''; polls = 0
  try {
    requestId.value = Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('')
    sessionStorage.setItem(storage, JSON.stringify({ target: selection.value, request_id: requestId.value }))
    const payload: Record<string, unknown> = { request_id: requestId.value,
      expected_operation_id: status.value.operation?.request_id ?? null }
    if (action === 'apply' || action === 'rollback') {
      const build = reviewed.value!.build!
      Object.assign(payload, { build_id: build,
        confirmation: action.toUpperCase() + ' ' + selected.value.component + ' ' + selected.value.target_id + ' ' + build,
        maintenance_override: props.maintenanceOverrideRequired && override.value })
      if (action === 'apply') payload.candidate_id = reviewed.value!.candidate
    }
    dispatched = true; unknown.value = true
    const result = await http.post(base + '/' + selection.value + '/' + action, payload)
    if (result.data.request_id !== requestId.value) throw new Error('Unconfirmed identity')
    if (live) dialog.value = null
  } catch (failure) {
    refused = (failure as { response?: { data?: { detail?: { code?: string } } } })?.response?.data?.detail?.code === 'component_update_not_accepted'
    if (live) error.value = refused ? text('refused', 'Not accepted; no update was scheduled. Refresh and review the current state.')
      : text('unconfirmed', 'Outcome unconfirmed. Preserve the request ID and read status; do not resend.')
    if (!dispatched || refused) {
      unknown.value = false; sessionStorage.removeItem(storage)
      invalidated.value = true; acknowledged.value = false; override.value = false
    }
  } finally {
    sending.value = false
    if (live && dispatched) await refresh()
    if (live && refused) error.value = text('refused', 'Not accepted; no update was scheduled. Refresh and review the current state.')
  }
}
function reason(code: string | null) {
  const messages: Record<string, string> = {
    candidate_prepared: 'Candidate prepared. The running component has not changed.', component_updated: 'Updated and checked. Core stayed running.',
    component_rolled_back: 'Previous build restored and checked.', component_recovered: 'Interrupted operation reconciled; update was not replayed.',
    preparation_failed: 'Preparation failed; no switch requested. Installed dependencies must match the Core lock.',
    previous_component_ready: 'Operation failed; previous component is confirmed ready.',
    component_outcome_unconfirmed: 'Outcome unconfirmed. Explicit recovery is required.', worker_interrupted: 'Worker interrupted. Review recovery; do not repeat the update.',
  }
  return code ? text('reason.' + code, messages[code] || code) : ''
}
onMounted(() => { void load() })
onUnmounted(() => { live = false; generation++; if (timer) clearTimeout(timer) })
</script>

<template>
  <section class="component-updates card ui-v2" :aria-labelledby="prefix + '-title'">
    <header><div><h2 :id="prefix + '-title'">{{ text('title', 'Agent and application hosts') }}</h2>
      <p>{{ text('help', 'Prepare from this installed Core, then separately approve an exact component build. No downloads or dependency installation.') }}</p></div>
      <UiButton :disabled="loading || sending" @click="targets.length ? refresh() : load()">{{ text('refresh', 'Refresh status') }}</UiButton></header>
    <UiField :id="prefix + '-target'" type="select" :model-value="selection" :disabled="loading || busy || unknown"
      :label="text('target', 'Component to manage')" :options="targets.map(item => ({ value: key(item), label: item.component === 'agent' ? text('agent', 'Local Agent') : item.label }))"
      @update:model-value="changeTarget" />
    <p>{{ text('boundary', 'Only the selected component restarts. Core, Runtime, other host pins, the default host, applications, data and rights remain unchanged. An Agent restart briefly interrupts its capabilities.') }}</p>
    <p>{{ text('consent', 'Saved application consent may resume hardware output after reconnecting. This page does not grant rights or invoke Start/Send.') }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="unknown" role="alert">{{ text('unconfirmed', 'Outcome unconfirmed. Preserve the request ID and read status; do not resend.') }}</p>
    <p v-if="requestId">{{ text('requestId', 'Preserve request ID:') }} <code>{{ requestId }}</code></p>
    <template v-if="status">
      <dl><dt>{{ text('current', 'Current build') }}</dt><dd><code>{{ status.current_build_id || '—' }}</code></dd>
        <dt>{{ text('previous', 'Previous build') }}</dt><dd><code>{{ status.previous_build_id || '—' }}</code></dd>
        <dt>{{ text('health', 'Live readiness') }}</dt><dd>{{ status.ready ? text('ready', 'Ready') : text('notReady', 'Not confirmed') }}</dd></dl>
      <p v-if="status.operation" role="status"><code>{{ status.operation.component }} / {{ status.operation.target_id }}</code> ·
        {{ t('runtimeUpdates.state.' + status.operation.state, status.operation.state) }} · {{ reason(status.operation.reason) }}</p>
      <div v-if="status.candidate" class="candidate"><h3>{{ text('candidate', 'Prepared candidate') }}</h3>
        <code>{{ status.candidate.build_id }}</code><p>SHA-256: <code>{{ status.candidate.sha256 }}</code></p>
        <p v-if="status.candidate.build_id === status.current_build_id">{{ text('same', 'This build is already selected. No update is needed.') }}</p>
        <p v-else-if="!status.candidate.compatible">{{ text('stale', 'The reviewed component or Core changed. Prepare a fresh candidate.') }}</p></div>
      <div class="actions">
        <UiButton :disabled="!idle" @click="submit('prepare')">{{ text('prepare', 'Prepare from installed Core') }}</UiButton>
        <UiButton variant="primary" :disabled="!canApply" @click="review('apply')">{{ text('update', 'Review update') }}</UiButton>
        <UiButton :disabled="!canRollback" @click="review('rollback')">{{ text('rollback', 'Review previous build') }}</UiButton>
        <UiButton v-if="status.recovery_required" :disabled="!canRecover" @click="review('recover')">{{ text('recover', 'Review interrupted-operation recovery') }}</UiButton>
      </div>
    </template>
    <p v-else-if="loading" role="status">{{ text('loading', 'Reading selected component…') }}</p>
    <UiDialog :open="dialog !== null" :title="text('confirmTitle', 'Review component operation')" :close-label="text('close', 'Close')"
      @update:open="value => { if (!value && !sending) dialog = null }">
      <p><strong>{{ selected?.component === 'agent' ? text('agent', 'Local Agent') : selected?.label }}</strong></p>
      <p>{{ dialog === 'recover' ? text('confirmRecovery', 'Reconcile the interrupted transaction and check this component. This can restart it but never replays an update or application operation.') : text('confirmSwitch', 'Switch only this component to the exact build below. Failed health checks must restore the previous build or leave an explicit recovery-required result.') }}</p>
      <code v-if="dialog !== 'recover'">{{ reviewed?.build }}</code>
      <p v-if="!reviewCurrent" role="alert">{{ text('reviewChanged', 'The reviewed state changed. Close and review it again.') }}</p>
      <label class="check"><input v-model="acknowledged" type="checkbox" :disabled="sending">{{ text('acknowledge', 'I reviewed this exact target, build and temporary interruption.') }}</label>
      <label v-if="dialog !== 'recover' && maintenanceOverrideRequired" class="check"><input v-model="override" type="checkbox" :disabled="sending">{{ text('override', 'I explicitly approve switching outside the maintenance window.') }}</label>
      <template #actions><UiButton :disabled="sending" @click="dialog = null">{{ text('close', 'Close') }}</UiButton>
        <UiButton variant="primary" :disabled="sending || !acknowledged || !reviewCurrent || !eligible || dialog !== 'recover' && maintenanceOverrideRequired && !override"
          @click="dialog && submit(dialog)">{{ text('confirm', 'Confirm once') }}</UiButton></template>
    </UiDialog>
  </section>
</template>

<style scoped>
.component-updates { margin-block: 1.25rem; padding: 1.25rem; min-width: 0; color: var(--ui-text); background: var(--ui-surface); }
header, .actions { display: flex; flex-wrap: wrap; gap: .8rem; justify-content: space-between; align-items: start; }
header > div { flex: 1 1 20rem; min-width: 0; }
.component-updates > :not(:first-child), header p { margin-top: 1rem; }
p { color: var(--ui-text-secondary); }
dl { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,2fr); gap: .55rem 1rem; }
dd { margin: 0; min-width: 0; } code { overflow-wrap: anywhere; white-space: pre-wrap; color: var(--ui-text); }
.candidate { padding-block: .8rem; border-block: 1px solid var(--ui-border); } .candidate p { margin-top: .65rem; }
.check { display: flex; align-items: start; gap: .6rem; margin-block: 1rem; } [role="alert"] { color: var(--ui-danger); }
@media(max-width:600px) { dl { grid-template-columns: minmax(0,1fr); } dt { font-weight: 600; } dd { margin-bottom: .7rem; } }
</style>
