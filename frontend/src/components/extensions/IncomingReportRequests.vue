<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'

const props = defineProps<{moduleId: string}>()
const { t } = useI18n()
const label = (key: string) => t('incomingReports.' + key)
type Entry = {binding_id: string; sender_id: string; sender_key_id: string; generation: number;
  receiver_artifact: string; receiver_incarnation: string;
  metadata_hash: string; consent_revision: number; intent: string; expires_at: string;
  consent: {consent_version: 1; summary_fields: string[]; node_ids: string[]; node_fields: string[]}}
const base = computed(() => '/api/v1/installation-peers/applications/' + encodeURIComponent(props.moduleId) + '/incoming-report-requests')
const entries = ref<Entry[] | null>(null), chosen = ref<Entry>(), busy = ref(false)
const limited = ref(false), notice = ref('')
let epoch = 0
function clear() { ++epoch; entries.value = null; chosen.value = undefined; limited.value = false; notice.value = ''; busy.value = false }
watch(() => props.moduleId, clear, {flush:'sync'})
onBeforeUnmount(clear)
const digest = /^[0-9a-f]{64}$/
const token = (value: unknown, pattern: RegExp) =>
  typeof value === 'string' && value === value.trim() && pattern.test(value)
function isEntry(e: Entry) {
  const c = e?.consent
  const fields = (a: unknown, max: number, valid: (v:string)=>boolean) =>
    Array.isArray(a) && a.length <= max && a.every(v=>typeof v==='string' && valid(v)) && new Set(a).size===a.length
  return e && token(e.binding_id, /^peer_[0-9a-f]{32}$/) && token(e.sender_id, /^inst_[0-9a-f]{32}$/)
    && token(e.sender_key_id, digest) && token(e.metadata_hash, digest) && token(e.intent, /^[A-Za-z0-9_-]{1,256}$/)
    && token(e.receiver_artifact, digest) && token(e.receiver_incarnation, /^[0-9a-f]{32}$/)
    && Number.isSafeInteger(e.generation) && e.generation > 0 && Number.isSafeInteger(e.consent_revision) && e.consent_revision > 0
    && typeof e.expires_at==='string' && Number.isFinite(Date.parse(e.expires_at)) && c?.consent_version===1
    && fields(c.summary_fields, 3, v=>['core_version','protocol_version','sdk_version'].includes(v))
    && fields(c.node_ids, 64, v=>token(v, /^dev_[0-9a-f]{32}$/))
    && fields(c.node_fields, 9, v=>['display_name','role','protocol_version','agent_version','online','last_seen_at','architecture','memory_total_bytes','root_free_bytes'].includes(v))
    && Boolean(c.node_ids.length) === Boolean(c.node_fields.length)
}
async function load() {
  if (busy.value) return
  clear(); const attempt = epoch; busy.value = true
  try {
    const {data} = await http.get(base.value, {timeout:10000})
    if (attempt !== epoch) return
    if (data?.module_id !== props.moduleId || typeof data.limited !== 'boolean' || !Array.isArray(data.requests)
        || data.requests.length > 32 || !data.requests.every(isEntry)
        || new Set(data.requests.map((e: Entry)=>e.binding_id)).size !== data.requests.length) throw Error()
    entries.value = data.requests; limited.value = data.limited
  } catch { if (attempt === epoch) notice.value = 'unavailable' }
  finally { if (attempt === epoch) busy.value = false }
}
async function approve() {
  const entry = chosen.value
  if (!entry || busy.value) return
  if (Date.parse(entry.expires_at) <= Date.now()) { clear(); notice.value='expired'; return }
  const attempt = epoch; busy.value = true; notice.value = ''
  try {
    const {status} = await http.post(base.value + '/' + entry.binding_id + '/approve', {
      expected_generation:entry.generation, expected_metadata_revision:entry.consent_revision,
      expected_metadata_hash:entry.metadata_hash,
      expected_receiver_artifact:entry.receiver_artifact, expected_receiver_incarnation:entry.receiver_incarnation,
    }, {timeout:15000})
    if (status !== 204) throw Error()
    if (epoch === attempt) notice.value = 'approved'
  } catch { if (epoch === attempt) notice.value = 'unconfirmed' }
  finally {
    // Never resubmit an uncertain decision or keep an old review actionable.
    if (epoch === attempt) { busy.value=false; chosen.value=undefined; entries.value=null; limited.value=false }
  }
}
</script>

<template>
  <details class="authority-details">
    <summary>{{ label('title') }}</summary>
    <p>{{ label('help') }}</p>
    <button type="button" class="ui-button" :disabled="busy" @click="load">{{ label('check') }}</button>
    <p v-if="notice" role="status">{{ label(notice) }}</p>
    <p v-if="entries?.length===0" role="status">{{ label('empty') }}</p>
    <p v-if="limited">{{ label('limited') }}</p>
    <ul v-if="entries?.length">
      <li v-for="entry in entries" :key="entry.binding_id">
        <button type="button" class="ui-button" :disabled="busy" @click="chosen=entry">{{ label('review') }} · {{ entry.sender_id }}</button>
      </li>
    </ul>
    <section v-if="chosen" class="ui-stack">
      <dl>
        <dt>{{ label('sender') }}</dt><dd><code>{{ chosen.sender_id }}</code></dd>
        <dt>{{ label('key') }}</dt><dd><code>{{ chosen.sender_key_id }}</code></dd>
        <dt>{{ label('intent') }}</dt><dd><code>{{ chosen.intent }}</code></dd>
        <dt>{{ label('summary') }}</dt><dd>{{ chosen.consent.summary_fields.join(', ') || label('none') }}</dd>
        <dt>{{ label('devices') }}</dt><dd>{{ chosen.consent.node_ids.join(', ') || label('none') }}</dd>
        <dt>{{ label('fields') }}</dt><dd>{{ chosen.consent.node_fields.join(', ') || label('none') }}</dd>
        <dt>{{ label('expires') }}</dt><dd>{{ new Date(chosen.expires_at).toLocaleString() }}</dd>
      </dl>
      <button type="button" class="ui-button" :disabled="busy" @click="approve">{{ label('approve') }}</button>
    </section>
  </details>
</template>

<style scoped>
dd, li { overflow-wrap: anywhere; }
dt { font-weight: 600; }
dd { margin: 0 0 .5rem; }
</style>
