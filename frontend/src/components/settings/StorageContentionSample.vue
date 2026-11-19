<template>
  <details class="storage-sample">
    <summary>{{ t('diagnostics.storageSample.title', 'Who is writing to the Core database?') }}</summary>
    <p>{{ t('diagnostics.storageSample.help', 'Measure five seconds of new Core connections. No queries, values or identities are recorded.') }}</p>
    <div class="sample-actions">
      <button type="button" class="ui-button ui-button--secondary" :disabled="busy" @click="collect">
        {{ busy ? t('diagnostics.storageSample.wait', 'Measuring…') : t('diagnostics.storageSample.start', 'Measure for 5 seconds') }}
      </button>
      <button v-if="sample" type="button" class="ui-button ui-button--secondary" @click="download">{{ t('diagnostics.storageSample.export', 'Save measurement') }}</button>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-if="sample" role="status">
      <p v-if="!sample.families.length">{{ t('diagnostics.storageSample.empty', 'No eligible writes were observed in this measurement.') }}</p>
      <p v-if="sample.limited">{{ t('diagnostics.storageSample.limited', 'Some observations were dropped.') }}</p>
      <ul v-if="sample.families.length">
        <li v-for="row in sample.families" :key="row.source">
          <strong>{{ t('diagnostics.storageSample.sources.' + row.source, sources[row.source]) }}</strong>:
          {{ row.observed }} {{ t('diagnostics.storageSample.transactions', 'transactions; longest observed') }}
          {{ row.longest_ms }} ms · {{ t('diagnostics.storageSample.open', 'open at end:') }} {{ row.open_at_end }}
        </li>
      </ul>
      <p>{{ t('diagnostics.storageSample.limit', 'Older connections and other processes are not measured. This is not proof of who blocked an earlier request.') }}</p>
    </div>
  </details>
</template>

<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'
import { saveDiagnosticJson } from '@/utils/save-diagnostic-json'

const { t } = useI18n()
const sources: Record<string, string> = {
  accounts: 'Accounts', application_tasks: 'Application tasks', application_events: 'Application events',
  application_commands: 'Application commands', applications: 'Applications', devices: 'Devices',
  installation: 'Installation', packages: 'Packages', system: 'System', other: 'Other Core work',
}
type Row = { source: string; observed: number; longest_ms: number; open_at_end: number }
type Sample = { schema_version: 1; kind: 'sqlite_write_sample'; coverage: 'new_core_engine_connections'; window_ms: number; limited: boolean; families: Row[] }
function checked(data: Sample): Sample {
  const bounded = (n: number, low: number, high: number) => Number.isSafeInteger(n) && n >= low && n <= high
  if (data?.kind !== 'sqlite_write_sample' || data.schema_version !== 1 || data.coverage !== 'new_core_engine_connections' ||
      typeof data.limited !== 'boolean' || !bounded(data.window_ms, 0, Number.MAX_SAFE_INTEGER) ||
      !Array.isArray(data.families) || data.families.length > Object.keys(sources).length) throw new Error()
  const seen = new Set<string>()
  let pending = 0
  const families = data.families.map(({ source, observed, longest_ms, open_at_end }) => {
    if (typeof source !== 'string' || !Object.prototype.hasOwnProperty.call(sources, source) || seen.has(source) ||
        !bounded(observed, 1, Number.MAX_SAFE_INTEGER) || !bounded(longest_ms, 0, data.window_ms) ||
        !bounded(open_at_end, 0, Math.min(64 - pending, observed))) throw new Error()
    seen.add(source); pending += open_at_end
    return { source, observed, longest_ms, open_at_end }
  })
  return { schema_version: 1, kind: data.kind, coverage: data.coverage, limited: data.limited, window_ms: data.window_ms, families }
}
const busy = ref(false), error = ref(''), sample = ref<Sample | null>(null)
let disposed = false
onUnmounted(() => { disposed = true })
async function collect() {
  if (busy.value) return
  busy.value = true; error.value = ''; sample.value = null
  try {
    const response = await http.post('/api/v1/diagnostics/storage-sample')
    if (!disposed) sample.value = checked(response.data)
  } catch (cause) {
    if (!disposed) error.value = (cause as { response?: { status?: number } })?.response?.status === 429
      ? t('diagnostics.storageSample.cooldown', 'A measurement is running or just finished. Wait a moment before measuring again.')
      : t('diagnostics.storageSample.failure', 'No current measurement is available.')
  } finally { if (!disposed) busy.value = false }
}
function download() {
  if (sample.value) saveDiagnosticJson(sample.value, 'core-database-sample.json')
}
</script>

<style scoped>
.storage-sample { margin: 1rem 0; }
summary { cursor: pointer; font-weight: 600; }
p,ul { margin: .55rem 0; }
.sample-actions { display: flex; flex-wrap: wrap; gap: .5rem; }
[role=alert] { color: var(--ui-danger); }
</style>
