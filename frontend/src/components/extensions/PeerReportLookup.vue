<template>
  <details class="peer-lookup">
    <summary>{{ label('title') }}</summary>
    <p>{{ label('help') }}</p>
    <button type="button" class="ui-button" :disabled="listing || busy" @click="discover()">{{ label('find') }}</button>
    <p v-if="listFailed" role="alert">{{ label('failed') }}</p>
    <template v-if="choices">
      <p v-if="choices.length === 0" role="status">{{ label(continuation ? 'noMore' : 'empty') }}</p>
      <label v-else>{{ label('pick') }}
        <select :value="choices.findIndex(c => c.link_id === link && c.report_id === report)" @change="pick">
          <option :value="-1">{{ label('choose') }}</option>
          <option v-for="(c, n) in choices" :key="c.link_id" :value="n">{{ c.link_id }} · {{ c.report_id }}</option>
        </select>
      </label>
      <p v-if="limited">{{ label('limited') }}</p>
      <button v-if="limited && choices.length" type="button" class="ui-button" :disabled="listing || busy"
        @click="discover(choices[choices.length - 1]?.link_id)">{{ label('nextPage') }}</button>
    </template>
    <form @submit.prevent="check">
      <label>{{ label('link') }}
        <input v-model.trim="link" placeholder="peer_…" maxlength="37" autocomplete="off" :spellcheck="false">
      </label>
      <label>{{ label('report') }}
        <input v-model.trim="report" placeholder="report_…" maxlength="39" autocomplete="off" :spellcheck="false">
      </label>
      <button type="submit" class="ui-button" :disabled="!valid || busy || listing">{{ label(busy ? 'checking' : 'check') }}</button>
    </form>
    <p v-if="error" role="alert">{{ label('failed') }}</p>
    <div v-if="value" role="status">
      <p>{{ label(value.state) }}</p>
      <button type="button" class="ui-button" @click="saveDiagnosticJson(value, 'peer-report.json')">{{ label('save') }}</button>
    </div>
  </details>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'
import { saveDiagnosticJson } from '@/utils/save-diagnostic-json'

const props = defineProps<{ moduleId: string }>()
const { t } = useI18n()
const label = (k: string) => t('applicationLimits.peerReceipt.' + k)
const link = ref(''), report = ref(''), error = ref(false), busy = ref(false)
const valid = computed(() => /^peer_[0-9a-f]{32}$/.test(link.value) && /^report_[0-9a-f]{32}$/.test(report.value))
const states = ['not_observed_in_scope', 'outcome_unconfirmed', 'acknowledged', 'unavailable'] as const
type State = typeof states[number]
type Observation = {
  schema_version: 1; kind: 'peer_report_observation'; source: 'local_outbound_slot'; automatic_replay_allowed: false;
  module_id: string; link_id: string; report_id: string; state: State
}
const value = ref<Observation | null>(null)
type Reference = {link_id:string; report_id:string}
const choices = ref<Reference[] | null>(null), limited = ref(false), listFailed = ref(false), listing = ref(false)
const continuation = ref(false)
let discovery: AbortController | undefined
let request: AbortController | undefined
function clear() {
  request?.abort(); request = undefined; value.value = null; busy.value = false; error.value = false
}
watch([link, report, () => props.moduleId], clear, {flush: 'sync'})
function resetList() {
  discovery?.abort(); discovery = undefined; listing.value = false; listFailed.value = false
  choices.value = null; limited.value = false; continuation.value = false
}
watch(() => props.moduleId, () => { resetList(); link.value = ''; report.value = '' }, {flush:'sync'})
onBeforeUnmount(() => { clear(); resetList() })
async function discover(after?: string) {
  if (listing.value || busy.value) return
  clear()
  resetList()
  link.value = ''; report.value = ''
  const owner = props.moduleId, active = discovery = new AbortController()
  listing.value = true
  try {
    const { data } = await http.get('/api/v1/installation-peers/applications/' + encodeURIComponent(owner) +
      '/outbound/report-references', {signal:active.signal,timeout:10000,...(after ? {params:{after}} : {})})
    if (active !== discovery) return
    if (data?.module_id !== owner || typeof data.limited !== 'boolean' || !Array.isArray(data.references) ||
        data.references.length > 16 || !data.references.every((c: Reference) => typeof c?.link_id === 'string' &&
          /^peer_[0-9a-f]{32}$/.test(c.link_id) && typeof c.report_id === 'string' && /^report_[0-9a-f]{32}$/.test(c.report_id))) throw new Error()
    let last = after ?? ''
    for (const row of data.references) {
      if (row.link_id <= last) throw new Error()
      last = row.link_id
    }
    choices.value = data.references.map((c: Reference) => ({link_id:c.link_id,report_id:c.report_id}))
    limited.value = data.limited; continuation.value = after !== undefined
  } catch {
    if (active === discovery) listFailed.value = true
  } finally { if (active === discovery) listing.value = false }
}
function pick(event: Event) {
  const selected = choices.value?.[Number((event.target as HTMLSelectElement).value)]
  link.value = selected?.link_id ?? ''; report.value = selected?.report_id ?? ''
}
async function check() {
  if (!valid.value || busy.value || listing.value) return
  clear()
  const active = request = new AbortController()
  const owner = props.moduleId, id = link.value, refId = report.value
  busy.value = true
  try {
    const path = '/api/v1/installation-peers/applications/' + encodeURIComponent(owner) + '/outbound/' + id + '/reports/' + refId
    const { data } = await http.get(path, { signal: active.signal, timeout: 10000 })
    if (request !== active) return
    if (data?.kind !== 'peer_report_observation' || data.schema_version !== 1 || data.source !== 'local_outbound_slot' ||
        data.module_id !== owner || data.link_id !== id || data.report_id !== refId ||
        !states.includes(data.state) || data.automatic_replay_allowed !== false) throw new Error()
    value.value = {schema_version:1,kind:'peer_report_observation',source:'local_outbound_slot',module_id:owner,
      link_id:id,report_id:refId,state:data.state,automatic_replay_allowed:false}
  } catch {
    if (request === active) error.value = true
  } finally {
    if (request === active) busy.value = false
  }
}
</script>

<style scoped>
.peer-lookup { margin-top: .75rem; }
form { display: flex; flex-wrap: wrap; align-items: flex-end; gap: .65rem; }
label { display: grid; gap: .25rem; flex: 1 1 12rem; min-width: 0; }
input, select { box-sizing: border-box; width: 100%; min-width: 0; }
</style>
