<template>
  <section class="diagnostic-cases" aria-labelledby="diagnostic-cases-title">
    <div class="case-heading">
      <div><h4 id="diagnostic-cases-title">{{ compact ? t('diagnostics.simple.title', 'Recent problems') : t('diagnostics.cases.title', 'Diagnostic cases') }}</h4>
        <p v-if="compact">{{ t('diagnostics.simple.intro', 'Check what was observed in the last 15 minutes. Save the report if you need help.') }}</p>
        <p v-else>{{ t('diagnostics.cases.help', 'Safe failure history: up to 100 groups for 15 minutes. Repetitions are counted; process and page restarts clear their own history.') }}</p></div>
      <div class="case-actions">
        <button type="button" class="ui-button ui-button--secondary" :disabled="loading" @click="collect">{{ compact ? t('diagnostics.simple.refresh', 'Check again') : t('diagnostics.cases.collect', 'Collect observations') }}</button>
        <button type="button" class="ui-button ui-button--primary" :disabled="loading || !snapshot" @click="download">{{ compact ? t('diagnostics.simple.save', 'Download report') : t('diagnostics.cases.export', 'Save diagnostic bundle') }}</button>
        <button v-if="canClear && !confirmClear" type="button" class="ui-button ui-button--secondary" :disabled="loading" @click="confirmClear = true">{{ t('diagnostics.simple.clear', 'Clear history') }}</button>
      </div>
    </div>
    <div v-if="confirmClear" class="case-confirm">
      <p>{{ t('diagnostics.simple.clearHelp', 'Clear recent Core errors and observations in this browser tab? New errors will still appear. Audit records and recordings are kept.') }}</p>
      <div class="case-actions">
        <button type="button" class="ui-button ui-button--secondary" :disabled="loading" @click="confirmClear = false">{{ t('diagnostics.simple.cancel', 'Cancel') }}</button>
        <button type="button" class="ui-button ui-button--secondary" :disabled="loading" @click="clearHistory">{{ t('diagnostics.simple.confirmClear', 'Yes, clear history') }}</button>
      </div>
    </div>
    <p v-if="clearFailed" role="alert">{{ t('diagnostics.simple.clearFailed', 'Clearing was not confirmed. Check again before trying to clear history.') }}</p>
    <p v-if="loading" role="status">{{ t('diagnostics.loading', 'Checking device…') }}</p>
    <p v-if="error" role="alert">{{ t('diagnostics.cases.failed', 'Collection was not confirmed. Previously collected observations may be stale.') }}</p>
    <template v-if="snapshot">
      <p class="case-note">{{ t('diagnostics.cases.collected', 'Collected at:') }} {{ new Date(snapshot.generated_at).toLocaleString() }}<template v-if="!compact"> · {{ snapshot.status }}</template></p>
      <div v-if="compact" aria-live="polite">
        <p v-if="snapshot.status === 'partial'">{{ t('diagnostics.simple.partial', 'Some checks did not return a result. This report is incomplete.') }}</p>
        <template v-if="snapshot.cases.length">
          <strong>{{ t('diagnostics.simple.count', 'Recorded Core failures:') }} {{ failureCount }}</strong>
          <p v-for="group in groups" :key="group.reason" class="compact-reason">{{ t('diagnostics.reason.' + group.reason, group.summary) }} · × {{ group.count }}</p>
          <small>{{ t('diagnostics.simple.full', 'The download includes all retained cases and their request identifiers.') }}</small>
        </template>
        <p v-else>{{ t('diagnostics.simple.none', 'No recent Core failure was retained. This is not a health guarantee.') }}</p>
        <p v-if="snapshot.browser?.records.length">{{ t('diagnostics.simple.browser', 'Separate browser observations:') }} {{ snapshot.browser.records.length }}</p>
      </div>
      <template v-else>
      <label class="case-filter">{{ t('diagnostics.cases.filter', 'Case or request identifier') }}<input v-model.trim="filter" maxlength="48" autocomplete="off" /></label>
      <p v-if="!cases.length && !clientRows.length">{{ t('diagnostics.cases.empty', 'No matching failure is retained. This is not proof that everything succeeded.') }}</p>
      <article v-for="item in cases" :key="item.case_id" class="case-card">
        <div class="case-heading"><strong>{{ t('diagnostics.reason.' + item.evidence.reason, item.summary) }}</strong><span class="ui-badge">{{ item.evidence.transport }} {{ item.evidence.status ?? '' }} · × {{ item.evidence.occurrences }}</span></div>
        <p v-if="item.evidence.handled_refusal === true">{{ t('diagnostics.cases.handledRefusal', 'HTTP succeeded, but a resource check was refused. The returned list may omit that resource; this is not a successful session opening.') }}</p>
        <dl>
          <dt>{{ t('diagnostics.cases.where', 'Where it stopped') }}</dt><dd><code>{{ item.evidence.stage }} · {{ item.evidence.reason }}</code><code>{{ item.evidence.method }} {{ item.evidence.route }}</code></dd>
          <template v-if="olderAttempt(item)"><dt>{{ t('diagnostics.simple.stepTime', 'Time in failed step') }}</dt><dd>{{ t('diagnostics.cases.olderTiming', 'Timing and the last passed check were not retained for this request.') }}</dd></template>
          <template v-else-if="item.evidence.failed_step_ms !== undefined"><dt>{{ t('diagnostics.simple.stepTime', 'Time in failed step') }}</dt><dd>{{ item.evidence.failed_step_ms }} ms</dd>
            <template v-if="item.evidence.last_passed_stage"><dt>{{ t('diagnostics.cases.lastCheck', 'Last passed check') }}</dt><dd><code>{{ item.evidence.last_passed_stage }}</code></dd></template>
          </template>
          <dt>{{ t('diagnostics.cases.execution', 'What is confirmed') }}</dt><dd>{{ phaseName(item.execution) }}</dd>
          <dt>{{ t('diagnostics.cases.next', 'Next read-only check') }}</dt><dd>{{ t('diagnostics.next.' + item.next_check, item.next_check_help) }}</dd>
        </dl>
        <div class="case-actions"><button type="button" class="case-reference" @click="$emit('trace', item.case_id)">{{ item.case_id }}</button>
          <button v-if="item.operation && recordableOperations?.includes(item.operation)" type="button" class="ui-button ui-button--secondary" :disabled="recordingActive" @click="$emit('record', item.operation, item.evidence.instance_id ?? null)">{{ t('diagnostics.cases.record', 'Record next user attempt (2 min)') }}</button></div>
        <details><summary>{{ t('diagnostics.cases.evidence', 'Evidence and retained request identifiers') }}</summary>
          <p v-if="!olderAttempt(item)"><span v-if="item.evidence.occurrences > 1">{{ t('diagnostics.cases.latestTiming', 'Time and duration of the latest occurrence:') }} </span>{{ new Date(item.evidence.timestamp * 1000).toLocaleString() }} · {{ item.evidence.duration_ms }} ms · {{ item.trace_records.length }} {{ t('diagnostics.cases.traceRecords', 'detailed stage records') }}</p>
          <button v-for="id in item.evidence.trace_ids" :key="id" type="button" class="case-reference" @click="$emit('trace', id)">{{ id }}</button>
          <p>{{ t('diagnostics.cases.traceLimit', 'A repeated group retains its count and the latest 8 request identifiers. Earlier identifiers may no longer be available.') }}</p>
        </details>
      </article>
      <article v-for="item in clientRows" :key="item.case_id" class="case-card case-browser">
        <strong>{{ item.cause ? t('diagnostics.browser.' + item.cause, BROWSER_CAUSES[item.cause]) : clientReason(item.reason) }}</strong>
        <p>{{ t('diagnostics.cases.clientTrust', 'Browser observation only — not a confirmed Core outcome.') }}</p>
        <code>{{ item.operation }} · {{ item.status ?? (item.response_observed ? 'HTTP response received; local check refused' : 'HTTP outcome not recorded') }} · × {{ item.occurrences }}</code>
        <dl v-if="item.stage">
          <dt>{{ t('diagnostics.cases.firstCheck', 'First failed check') }}</dt><dd><code>{{ item.stage }} · {{ item.cause || item.reason }}</code></dd>
          <template v-if="item.last_passed_stage"><dt>{{ t('diagnostics.cases.lastCheck', 'Last passed check') }}</dt><dd><code>{{ item.last_passed_stage }}</code></dd></template>
        </dl>
        <code>{{ item.case_id }}</code>
        <button v-if="item.trace_id" type="button" class="case-reference" @click="$emit('trace', item.trace_id)">{{ item.trace_id }}</button>
        <p>{{ t('diagnostics.cases.clientUnknown', 'An absent response does not establish DNS failure, non-execution or permission to resend.') }}</p>
      </article>
      <details class="case-coverage"><summary>{{ t('diagnostics.cases.coverage', 'Coverage and missing evidence') }}</summary>
        <p v-for="item in snapshot.coverage" :key="item.boundary"><code>{{ item.boundary }} · {{ item.status }}</code></p>
        <p>{{ t('diagnostics.cases.loss', 'Core omitted / expired groups:') }} {{ JSON.stringify(snapshot.failure_history.dropped || {}) }}</p>
        <p v-for="item in snapshot.limitations" :key="item">{{ item }}</p>
      </details>
      </template>
    </template>
    <p v-if="!compact" class="case-note">{{ t('diagnostics.cases.readOnly', 'Collection does not invoke applications, reconnect sessions, change permissions or repeat actions. Detailed recording is separate. The saved JSON contains the same observations shown here, including this page’s bounded browser metadata.') }}</p>
  </section>
</template>

<script setup lang="ts">
import { saveDiagnosticJson } from '@/utils/save-diagnostic-json'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'
import { BROWSER_CAUSES, browserDiagnosticSnapshot, clearBrowserDiagnostics } from '@/utils/diagnostic-client'
const { t } = useI18n()
defineEmits<{ trace: [id: string]; record: [operation: string, instance: string | null] }>()
const props = defineProps<{ compact?: boolean; producerSnapshot?: unknown; recordingActive?: boolean; recordableOperations?: string[] }>()
type Case = { case_id: string; timing_trace_id?: string; summary: string; next_check: string; next_check_help: string;
  operation: string | null; execution: string; trace_records: unknown[];
  evidence: { trace_ids: string[]; instance_id?: string | null; occurrences: number; timestamp: number; duration_ms: number; failed_step_ms?: number; last_passed_stage?: string | null;
    method: string; route: string; reason: string; stage: string; status: number | null; transport: string; handled_refusal?: boolean } }
type Snapshot = { schema_version: number; generated_at: string; status: string; cases: Case[];
  failure_history: { history_id?: string; dropped?: Record<string, number> }; limitations: string[];
  coverage: { boundary: string; status: string }[]; browser?: ReturnType<typeof browserDiagnosticSnapshot> }
const snapshot = ref<Snapshot | null>(null), loading = ref(false), error = ref(false), filter = ref('')
let disposed = false
let pendingRead: ReturnType<typeof http.get> | null = null
function pendingObservation() {
  // Reuse only a live read on this page, never an old report or an imported file.
  return pendingRead?.then(({ data }) => {
    const sample = data?.observations
    return !disposed && data?.schema_version === 1 && sample?.schema_version === 1
      && sample.probe_status === 'complete' && Array.isArray(sample.components) && Array.isArray(sample.operations)
      ? { data: sample } : null
  })
}
defineExpose({ pendingObservation })
const confirmClear = ref(false), clearFailed = ref(false)
const canClear = computed(() => !!snapshot.value?.failure_history.history_id && !clearFailed.value
  && (!!snapshot.value.cases.length || !!snapshot.value.browser?.records.length))
const failureCount = computed(() => snapshot.value?.cases.reduce((n, item) => n + item.evidence.occurrences, 0) ?? 0)
const groups = computed(() => {
  const totals = new Map<string, { reason: string; summary: string; count: number }>()
  for (const item of snapshot.value?.cases ?? []) {
    const key = item.evidence.reason
    const group = totals.get(key) ?? { reason: key, summary: item.summary, count: 0 }
    group.count += item.evidence.occurrences
    totals.set(key, group)
  }
  return [...totals.values()].sort((a, b) => b.count - a.count).slice(0, 3)
})
const cases = computed(() => (snapshot.value?.cases || []).filter(item => !filter.value
  || item.case_id.includes(filter.value) || item.evidence.trace_ids.some(id => id.includes(filter.value))))
function olderAttempt(item: Case) {
  return item.evidence.trace_ids.includes(filter.value) && filter.value !== (item.timing_trace_id ?? item.case_id)
}
const clientRows = computed(() => (snapshot.value?.browser?.records || []).filter(item => !filter.value
  || item.case_id.includes(filter.value) || item.trace_id?.includes(filter.value)))
function phaseName(phase: string) {
  if (phase === 'not_dispatched') return t('diagnostics.cases.unsent', 'No application/executor dispatch was observed for this request. This is not a replay instruction.')
  if (phase === 'execution_unconfirmed') return t('diagnostics.cases.unconfirmed', 'Execution is unconfirmed. Read the original outcome; do not resend.')
  if (phase === 'completed') return t('diagnostics.cases.completed', 'Completion was confirmed; this is not optical or external-effect verification.')
  return t('diagnostics.cases.unknown', 'Execution state was not recorded. Do not infer non-execution.')
}
function clientReason(reason: string) {
  if (reason === 'transport_unavailable') return t('diagnostics.cases.network', 'The browser did not observe a usable network response.')
  if (reason === 'deadline_exceeded') return t('diagnostics.cases.timeout', 'The browser request exceeded its deadline.')
  if (reason === 'http_refused') return t('diagnostics.cases.http', 'The browser observed an HTTP refusal; match the Core request identifier.')
  return t('diagnostics.cases.client', 'The browser adapter refused or could not complete the operation.')
}
async function collect() {
  if (loading.value) return
  loading.value = true; error.value = false
  try {
    pendingRead = http.get('/api/v1/diagnostics/cases')
    const { data } = await pendingRead
    if (disposed) return
    if (data?.schema_version !== 1 || !['ready', 'partial'].includes(data.status)
      || !Array.isArray(data.cases) || data.cases.length > 100 || !Array.isArray(data.coverage)) throw new Error()
    clearFailed.value = false
    confirmClear.value = false
    const browser = browserDiagnosticSnapshot()
    snapshot.value = { ...data, browser, coverage: data.coverage.map((item: { boundary: string; status: string }) =>
      item.boundary === 'browser' ? { ...item, status: 'collected_untrusted_page_memory' } : item) }
  } catch { if (!disposed) error.value = true }
  finally { pendingRead = null; if (!disposed) loading.value = false }
}
async function clearHistory() {
  const id = snapshot.value?.failure_history.history_id
  if (loading.value || !id || !confirmClear.value || !canClear.value) return
  loading.value = true
  try {
    const { data } = await http.delete('/api/v1/diagnostics/cases/history', { params: { history_id: id } })
    if (disposed) return
    if (data?.status !== 'cleared') throw new Error()
    clearBrowserDiagnostics()
    snapshot.value = null
  } catch {
    if (!disposed) clearFailed.value = true
    return
  } finally {
    if (!disposed) { loading.value = false; confirmClear.value = false }
  }
  await collect()
}
function download() {
  if (!snapshot.value) return
  const value = props.producerSnapshot ? { ...snapshot.value, producer_snapshot: props.producerSnapshot,
    coverage: snapshot.value.coverage.map(item => item.boundary === 'remote_producers'
      ? { ...item, status: 'explicitly_imported_unverified_snapshot' } : item) } : snapshot.value
  saveDiagnosticJson(value, 'diagnostic-cases.json')
}
onMounted(() => { void collect() })
onUnmounted(() => { disposed = true })
</script>

<style scoped>
.diagnostic-cases{margin:1rem 0;padding:1rem;border:1px solid var(--ui-border);border-radius:var(--ui-radius-sm);background:var(--ui-surface-alt)}
.case-heading,.case-actions{display:flex;gap:.65rem;align-items:center;justify-content:space-between;flex-wrap:wrap}.case-actions{justify-content:flex-start}
h4,p{margin:0 0 .6rem}.case-note,.case-coverage p{color:var(--ui-text-muted);font-size:.875rem}.case-filter{display:grid;gap:.3rem;margin:.8rem 0;max-width:32rem}
.compact-reason{margin:.5rem 0}
input{min-width:0;width:100%;padding:.5rem;color:var(--ui-text);background:var(--ui-surface);border:1px solid var(--ui-border);border-radius:var(--ui-radius-sm)}
.case-card{padding:1rem;margin:.7rem 0;border:1px solid var(--ui-border);border-radius:var(--ui-radius-sm);background:var(--ui-surface)}
dl{display:grid;grid-template-columns:minmax(7rem,1fr) minmax(0,4fr);gap:.45rem;margin:.8rem 0}dt{font-weight:600}dd{margin:0}code{display:block;overflow-wrap:anywhere;color:var(--ui-text-muted);font-size:.8rem}
.case-reference{display:block;max-width:100%;background:none;border:0;padding:.2rem 0;color:var(--ui-accent);font-family:monospace;text-align:left;overflow-wrap:anywhere}
details{margin:.65rem 0}summary{cursor:pointer}details p{margin-top:.5rem}[role=alert]{color:var(--ui-danger)}.case-browser{border-left:3px solid var(--ui-warning)}
@media(max-width:600px){dl{grid-template-columns:minmax(0,1fr)}.case-actions .ui-button{width:100%}.diagnostic-cases{padding:.7rem}}
</style>
