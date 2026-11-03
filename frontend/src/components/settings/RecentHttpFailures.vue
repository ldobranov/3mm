<template>
  <section class="recent-failures" aria-labelledby="recent-failures-title">
    <h4 id="recent-failures-title">{{ t('diagnostics.recent.title', 'Recent HTTP failures') }}</h4>
    <p>{{ t('diagnostics.recent.help', 'Always-on, safe metadata: up to 100 failures for 15 minutes in this Core process memory. Restart clears it. Detailed recording is separate.') }}</p>
    <p>{{ t('diagnostics.recent.traceHelp', 'Match Trace ID with the X-3mm-Trace-Id response header in the browser Network tab. Selecting it also filters detailed records when available.') }}</p>
    <div class="recent-actions">
      <button class="ui-button ui-button--secondary" :disabled="loading" @click="refresh">{{ t('diagnostics.recent.refresh', 'Refresh failures') }}</button>
      <button class="ui-button ui-button--secondary" :disabled="loading || !ready" @click="download">{{ t('diagnostics.recent.export', 'Export recent failures') }}</button>
      <label>{{ t('diagnostics.workspace.trace', 'Filter by trace ID') }}<input v-model.trim="filter" maxlength="48" autocomplete="off" /></label>
    </div>
    <p v-if="error" role="alert">{{ t('diagnostics.recent.failed', 'Recent failure observations are unavailable. Previously loaded rows may be stale.') }}</p>
    <p v-if="loading" role="status">{{ t('diagnostics.loading', 'Checking device…') }}</p>
    <p v-if="ready && !rows.length">{{ t('diagnostics.recent.empty', 'No recent Core HTTP failures recorded. Requests that never reached Core are not included.') }}</p>
    <p v-if="Object.values(dropped).some(value => value > 0)" class="recent-limits">{{ t('diagnostics.recent.limits', 'This is bounded history, not a complete audit. Omitted / expired records:') }} {{ Object.entries(dropped).map(([key, value]) => `${key}: ${value}`).join(' · ') }}</p>
    <div v-if="groups.length" class="recent-scroll" tabindex="0" :aria-label="t('diagnostics.recent.title', 'Recent HTTP failures')">
      <table>
        <thead><tr><th>{{ t('diagnostics.workspace.when', 'Time') }}</th><th>HTTP</th><th>{{ t('diagnostics.recent.cause', 'Stage / reason') }}</th><th>{{ t('diagnostics.recent.outcome', 'Execution state') }}</th><th>ms</th><th>Trace ID</th></tr></thead>
        <tbody><tr v-for="group in groups" :key="group.key">
          <td>{{ new Date(group.latest.timestamp * 1000).toLocaleTimeString() }}<small v-if="group.rows.length > 1">× {{ group.rows.length }}</small></td>
          <td>{{ group.latest.status }} · {{ group.latest.method }}<code>{{ group.latest.route }}</code></td>
          <td><code>{{ group.latest.stage }}</code><code>{{ group.latest.reason }}</code></td>
          <td>{{ phaseName(group.latest.phase) }}</td><td>{{ group.latest.duration_ms }}</td>
          <td><button type="button" class="trace-link" @click="$emit('trace', group.latest.trace_id)">{{ group.latest.trace_id }}</button>
            <details v-if="group.rows.length > 1"><summary>{{ t('diagnostics.recent.occurrences', 'All retained occurrences') }}</summary>
              <button v-for="row in group.rows" :key="row.trace_id" type="button" class="trace-link" @click="$emit('trace', row.trace_id)">{{ new Date(row.timestamp * 1000).toLocaleTimeString() }} · {{ row.trace_id }}</button>
            </details>
          </td>
        </tr></tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'
const { t } = useI18n()
defineEmits<{ trace: [id: string] }>()
type Failure = { trace_id: string; timestamp: number; method: string; route: string; status: number;
  duration_ms: number; stage: string; reason: string; phase: string; retryable: false }
const rows = ref<Failure[]>([]), dropped = ref<Record<string, number>>({}), filter = ref('')
const loading = ref(false), error = ref(false), ready = ref(false)
let disposed = false
const groups = computed(() => {
  const grouped = new Map<string, { key: string; latest: Failure; rows: Failure[] }>()
  for (const row of rows.value.filter(row => !filter.value || row.trace_id.includes(filter.value))) {
    const key = JSON.stringify([row.method, row.route, row.status, row.stage, row.reason, row.phase])
    if (!grouped.has(key)) grouped.set(key, { key, latest: row, rows: [] })
    grouped.get(key)!.rows.push(row)
  }
  return [...grouped.values()]
})
function phaseName(value: string) {
  if (value === 'not_dispatched') return t('diagnostics.recent.notDispatched', 'Application was not dispatched')
  if (value === 'execution_unconfirmed') return t('diagnostics.recent.unconfirmed', 'Execution unconfirmed — read the original outcome; do not resend')
  if (value === 'completed') return t('diagnostics.recent.completed', 'Application completion confirmed')
  return t('diagnostics.recent.unknown', 'Dispatch state not recorded — do not infer non-execution')
}
async function refresh() {
  if (loading.value) return
  loading.value = true; error.value = false
  try {
    const response = await http.get('/api/v1/diagnostics/failures')
    if (disposed) return
    if (response.data?.status !== 'ready' || !Array.isArray(response.data.records)) throw new Error()
    rows.value = response.data.records.slice(0, 100)
    dropped.value = response.data.dropped || {}
    ready.value = true
  } catch { if (!disposed) error.value = true }
  finally { if (!disposed) loading.value = false }
}
async function download() {
  if (loading.value) return
  loading.value = true; error.value = false
  try {
    const response = await http.get('/api/v1/diagnostics/failures/export', { responseType: 'blob' })
    if (disposed) return
    const url = URL.createObjectURL(new Blob([response.data], { type: 'application/json' }))
    try {
      const link = document.createElement('a'); link.href = url
      link.download = '3mm-recent-http-failures.json'; link.click()
    } finally { URL.revokeObjectURL(url) }
  } catch { if (!disposed) error.value = true }
  finally { if (!disposed) loading.value = false }
}
onMounted(() => { void refresh() })
onUnmounted(() => { disposed = true })
</script>

<style scoped>
.recent-failures { margin:1rem 0; padding:1rem; border:1px solid var(--ui-border); border-radius:var(--ui-radius-sm); background:var(--ui-surface-alt); }
h4,p { margin:0 0 .7rem; } p,small { color:var(--ui-text-muted); }
.recent-actions { display:flex; gap:.6rem; flex-wrap:wrap; align-items:end; margin-bottom:.8rem; }
label { display:grid; gap:.25rem; } input { min-width:15rem; max-width:100%; }
.recent-scroll { overflow:auto; max-height:30rem; } table { width:100%; border-collapse:collapse; }
th,td { text-align:left; vertical-align:top; padding:.5rem; border-bottom:1px solid var(--ui-border); }
code,small { display:block; overflow-wrap:anywhere; } code { font-size:.8rem; }
.trace-link { display:block; color:var(--ui-accent); background:none; border:0; text-align:left; padding:0; font-family:monospace; overflow-wrap:anywhere; }
[role="alert"] { color:var(--ui-danger); } summary { cursor:pointer; margin-top:.35rem; }
</style>
