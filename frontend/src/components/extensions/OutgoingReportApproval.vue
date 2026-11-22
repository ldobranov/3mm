<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'

const props = defineProps<{ moduleId: string }>()
const { t } = useI18n()
const title = (k: string) => t('outgoingReports.' + k)
const base = computed(() => '/api/v1/installation-peers/applications/' + encodeURIComponent(props.moduleId))
type Review = { review_hash: string; approved: boolean; sequence: number; checkpoint: string; contact: string;
  review: { module_id: string; link_id: string; target: string; origin: string; receiver_id: string;
    receiver_key: string; package_sha256: string; metadata: { consent: {
      summary_fields: string[]; node_ids: string[]; node_fields: string[] } } } }
const links = ref<string[]>(), card = ref<Review>(), busy = ref(false), note = ref('')
let generation = 0
const id = (v: unknown) => typeof v === 'string' && /^peer_[0-9a-f]{32}$/.test(v)
const sha = (v: unknown) => typeof v === 'string' && /^[0-9a-f]{64}$/.test(v)
function reset() { generation++; links.value = undefined; card.value = undefined; busy.value = false; note.value = '' }
watch(() => props.moduleId, reset, { flush: 'sync' })
onBeforeUnmount(reset)
async function read(link?: string) {
  if (busy.value || (link && !links.value?.includes(link))) return
  const epoch = generation
  busy.value = true; card.value = undefined; note.value = ''
  try {
    if (!link) {
      links.value = undefined
      const { data } = await http.get(base.value + '/sender-links', { timeout: 10000 })
      if (epoch !== generation) return
      if (data.module_id !== props.moduleId || !Array.isArray(data.links) || data.links.length > 32 || !data.links.every(id)) throw Error()
      links.value = data.links
    } else {
      const { data } = await http.get(base.value + '/outbound/' + link + '/sender-approval', { timeout: 10000 })
      if (epoch !== generation) return
      const r = data?.review, c = r?.metadata?.consent
      if (r?.module_id !== props.moduleId || r.link_id !== link || r.contract !== 'installation.status.report.v2'
        || !sha(data.review_hash) || !sha(r.package_sha256) || !sha(r.receiver_key)
        || typeof r.origin !== 'string' || !r.origin.startsWith('https://') || typeof r.receiver_id !== 'string' || !r.target
        || typeof data.approved !== 'boolean' || !Number.isSafeInteger(data.sequence) || data.sequence < 0
        || !['no_sample', 'unconfirmed', 'acknowledged'].includes(data.checkpoint)
        || !['online', 'offline', 'stale', 'unknown'].includes(data.contact)
        || ![c?.summary_fields,c?.node_ids,c?.node_fields].every(a => Array.isArray(a) && a.length <= 64 && a.every(v => typeof v === 'string'))) throw Error()
      card.value = data
    }
  } catch { if (epoch === generation) note.value = 'unavailable' }
  finally { if (epoch === generation) busy.value = false }
}
async function decide() {
  const selected = card.value
  if (!selected || busy.value) return
  const epoch = generation
  busy.value = true
  try {
    const { status } = await http.post(base.value + '/outbound/' + selected.review.link_id + '/sender-approval',
      { expected_review_hash: selected.review_hash, allow: !selected.approved }, { timeout: 15000 })
    if (status !== 204) throw Error()
    if (epoch === generation) note.value = selected.approved ? 'withdrawn' : 'saved'
  } catch { if (epoch === generation) note.value = 'uncertain' }
  finally { if (epoch === generation) { card.value = undefined; links.value = undefined; busy.value = false } }
}
</script>
<template>
  <details class="authority-details">
    <summary>{{ title('title') }}</summary>
    <p>{{ title('help') }}</p>
    <button type="button" class="ui-button" :disabled="busy" @click="read()">{{ title('check') }}</button>
    <p v-if="note" role="status">{{ title(note) }}</p>
    <p v-if="links?.length === 0">{{ title('empty') }}</p>
    <ul v-if="links?.length"><li v-for="link in links" :key="link">
      <button type="button" class="ui-button" :disabled="busy" @click="read(link)">{{ title('review') }} · {{ link }}</button>
    </li></ul>
    <section v-if="card">
      <dl>
        <dt>{{ title('destination') }}</dt><dd>{{ card.review.origin }} · {{ card.review.target }}</dd>
        <dt>{{ title('identity') }}</dt><dd>{{ card.review.receiver_id }} · {{ card.review.receiver_key }}</dd>
        <dt>{{ title('package') }}</dt><dd>{{ card.review.package_sha256 }}</dd>
        <dt>{{ t('incomingReports.summary') }}</dt><dd>{{ card.review.metadata.consent.summary_fields.join(', ') || t('incomingReports.none') }}</dd>
        <dt>{{ t('incomingReports.devices') }}</dt><dd>{{ card.review.metadata.consent.node_ids.join(', ') || t('incomingReports.none') }}</dd>
        <dt>{{ t('incomingReports.fields') }}</dt><dd>{{ card.review.metadata.consent.node_fields.join(', ') || t('incomingReports.none') }}</dd>
        <dt>{{ title('checkpoint') }}</dt><dd>{{ card.sequence }} · {{ title(card.checkpoint) }}</dd>
        <dt>{{ title('contact') }}</dt><dd>{{ title(card.contact) }}</dd>
      </dl>
      <button type="button" class="ui-button" :disabled="busy" @click="decide">{{ title(card.approved ? 'withdraw' : 'allow') }}</button>
    </section>
  </details>
</template>
<style scoped>li, dd { overflow-wrap: anywhere; } dt { font-weight: 600; } dd { margin: 0 0 .5rem; }</style>
