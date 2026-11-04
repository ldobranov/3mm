<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, useId } from 'vue'
import { UiButton, UiField } from '@/extension-ui/v1'
import UiDialog from '@/components/ui/UiDialog.vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'
const props = withDefaults(defineProps<{ maintenanceOverrideRequired?: boolean }>(), { maintenanceOverrideRequired: false })
const { t } = useI18n(), prefix = useId()
const text = (key: string, fallback: string) => t('remoteAgentUpdates.' + key, fallback)
type Node = { device_id: string; label: string; current_release_id: string | null; latest_operation_id: string | null }
type Outcome = { operation_id: string; device_id: string; release_id: string; archive_sha256: string;
  status: string; previous_release_id: string | null; error_code: string | null }
type Status = { operation_id: string; device_id: string; release_id: string; archive_sha256: string; archive_size_bytes: number;
  state: string; apply_command_id: string | null; apply_command_status: string | null; installation: Outcome | null }
type Check = { current_release_id: string | null; latest_release_id: string; latest_version: string; update_available: boolean | null }
const nodes = ref<Node[]>([]), selected = ref(''), channel = ref('stable'), status = ref<Status | null>(null), catalog = ref<Check | null>(null)
const loading = ref(false), sending = ref(false), unknown = ref(false), error = ref(''), operationId = ref(''), review = ref(false)
const acknowledged = ref(false), override = ref(false), frozen = ref(''), invalidated = ref(false)
const storage = '3mm-node-update-pending', terminal = ['succeeded','rolled_back','failed']
const node = computed(() => nodes.value.find(n => n.device_id === selected.value))
const installed = computed(() => status.value?.installation)
const busy = computed(() => sending.value || unknown.value || !!status.value && (
  ['queued','preparing'].includes(status.value.state) || !!status.value.apply_command_id && !terminal.includes(status.value.installation?.status || '')))
const canPrepare = computed(() => !!catalog.value && catalog.value.update_available !== false && !busy.value && !loading.value)
const canApply = computed(() => !!status.value && status.value.state === 'prepared' && !status.value.apply_command_id && !busy.value)
const identity = () => JSON.stringify([selected.value, status.value?.operation_id, status.value?.release_id, status.value?.archive_sha256])
const reviewCurrent = computed(() => !invalidated.value && frozen.value === identity())
const base = () => '/api/v1/devices/' + selected.value + '/node-updates'
const validId = (v: unknown) => typeof v === 'string' && /^nodeupd_[0-9a-f]{32}$/.test(v)
let live = true, timer: ReturnType<typeof setTimeout> | null = null, polls = 0
function schedule() {
  if (timer) clearTimeout(timer); timer = null
  if (live && busy.value && polls < 60) timer = setTimeout(() => { polls++; void refresh() }, 3000)
}
function decode(value: unknown): Status {
  const s = value as Status
  if (!s || s.device_id !== selected.value || s.operation_id !== operationId.value || !validId(s.operation_id)
    || !/^v[0-9A-Za-z.-]+$/.test(s.release_id) || !/^[a-f0-9]{64}$/.test(s.archive_sha256)
    || !['queued','preparing','prepared','failed','expired'].includes(s.state)
    || s.installation && (s.installation.device_id !== s.device_id || s.installation.operation_id !== s.operation_id
      || s.installation.release_id !== s.release_id || s.installation.archive_sha256 !== s.archive_sha256
      || !['accepted','running','succeeded','rolled_back','failed','unknown'].includes(s.installation.status))) throw new Error('Unconfirmed Node identity')
  return s
}
async function registry() {
  const result = await http.get('/api/v1/system-updates/components/nodes')
  const list = result.data.nodes as Node[]
  if (!Array.isArray(list) || list.length > 128 || list.some(n => !/^dev_[a-f0-9]{32}$/.test(n.device_id) || typeof n.label !== 'string')) throw new Error()
  if (live) nodes.value = list
}
async function refresh() {
  if (loading.value || !selected.value) return
  loading.value = true
  try {
    // Recover the server's durable preparation identity after a lost preparation
    // reply. This is read-only; installation still requires a fresh exact review.
    if (!operationId.value) { await registry(); operationId.value = node.value?.latest_operation_id || '' }
    if (operationId.value) {
      const result = await http.get(base() + '/' + operationId.value)
      if (!live) return
      status.value = decode(result.data); unknown.value = false
      if (review.value && (!reviewCurrent.value || !canApply.value)) { invalidated.value = true; acknowledged.value = false; override.value = false }
      if (installed.value && terminal.includes(installed.value.status) || ['failed','expired'].includes(status.value.state)) sessionStorage.removeItem(storage)
    } else unknown.value = false // Preparation cannot install software, so a new explicit preparation remains safe.
    error.value = ''
  } catch { if (live) error.value = text('unavailable','Node status is unavailable. Read the original operation; do not repeat installation.') }
  finally { loading.value = false; schedule() }
}
async function load() {
  loading.value = true
  try {
    await registry()
    const pending = JSON.parse(sessionStorage.getItem(storage) || 'null')
    selected.value = pending && nodes.value.some(n => n.device_id === pending.device_id) ? pending.device_id : nodes.value[0]?.device_id || ''
    operationId.value = pending && validId(pending.operation_id) ? pending.operation_id : node.value?.latest_operation_id || ''
    unknown.value = !!pending
  } catch { if (live) error.value = text('unavailable','Node status is unavailable. Read the original operation; do not repeat installation.') }
  finally { loading.value = false; if (live && selected.value) await refresh() }
}
async function select(value: unknown) {
  if (busy.value || loading.value) return
  selected.value = String(value); status.value = null; catalog.value = null; review.value = false; polls = 0
  operationId.value = node.value?.latest_operation_id || ''; await refresh()
}
async function check() {
  if (loading.value || busy.value || !selected.value) return
  loading.value = true; catalog.value = null
  try {
    const result = await http.get(base() + '/check?channel=' + channel.value)
    if (!live) return
    const value = result.data as Check
    if (!value || typeof value.latest_release_id !== 'string' || !/^v[0-9A-Za-z.-]+$/.test(value.latest_release_id)) throw new Error()
    catalog.value = value; error.value = ''
  } catch { if (live) error.value = text('catalogUnavailable','No supported published Node package was confirmed. Check the Node profile and its pinned Hub identity.') }
  finally { loading.value = false }
}
async function prepare() {
  if (!canPrepare.value) return
  sending.value = true; operationId.value = ''; status.value = null; polls = 0
  try {
    sessionStorage.setItem(storage,JSON.stringify({device_id:selected.value,operation_id:null}))
    unknown.value = true
    const result = await http.post(base()+'/prepare',{channel:channel.value})
    if (!live) return
    if (result.data.prepared.device_id !== selected.value || !validId(result.data.prepared.operation_id)) throw new Error()
    operationId.value = result.data.prepared.operation_id
    sessionStorage.setItem(storage,JSON.stringify({device_id:selected.value,operation_id:operationId.value}))
  } catch { if (live) error.value = text('unconfirmed','Result unconfirmed. Read status; installation is never automatically repeated.') }
  finally { sending.value = false; if (live) await refresh() }
}
function openReview() { frozen.value = identity(); invalidated.value = false; acknowledged.value = false; override.value = false; review.value = true }
async function apply() {
  if (!canApply.value || !reviewCurrent.value || !acknowledged.value || props.maintenanceOverrideRequired && !override.value) return
  sending.value = true; polls = 0
  try {
    sessionStorage.setItem(storage,JSON.stringify({device_id:selected.value,operation_id:operationId.value}))
    unknown.value = true
    const result = await http.post(base()+'/'+operationId.value+'/apply',{
      confirmed_install:true,maintenance_override:props.maintenanceOverrideRequired && override.value })
    if (result.data.operation_id !== operationId.value) throw new Error()
    if (live) review.value = false
  } catch { if (live) error.value = text('unconfirmed','Result unconfirmed. Read status; installation is never automatically repeated.') }
  finally { sending.value = false; if (live) await refresh() }
}
onMounted(() => { void load() })
onUnmounted(() => { live = false; if (timer) clearTimeout(timer) })
</script>

<template>
  <section class="remote-agents card ui-v2" :aria-labelledby="prefix+'-title'">
    <header><div><h2 :id="prefix+'-title'">{{ text('title','Remote Node Agents') }}</h2>
      <p>{{ text('help','Update one Node through its signed OTA mechanism. Core is not updated. This uses the supported published ARMv6 Node package, including its Agent and Node service files; it is not a local native-host build.') }}</p></div>
      <UiButton :disabled="loading || sending" @click="nodes.length ? refresh() : load()">{{ text('refresh','Refresh status') }}</UiButton></header>
    <p>{{ text('safety','The Node must have signed-update support, the pinned Hub identity, fresh state and no conflicting physical commands. Its installer preserves device identity and data and verifies health or rollback. Unsupported profiles are refused, not upgraded by guessing.') }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="!nodes.length && !loading">{{ text('empty','No approved remote Node devices are registered.') }}</p>
    <template v-if="nodes.length">
      <UiField :id="prefix+'-device'" :label="text('device','Node device')" type="select" :model-value="selected"
        :options="nodes.map(n=>({value:n.device_id,label:n.label}))" :disabled="loading || busy" @update:model-value="select" />
      <p><code>{{ selected }}</code> · {{ text('current','Last confirmed release') }}: <code>{{ node?.current_release_id || '—' }}</code></p>
      <UiField :id="prefix+'-channel'" v-model="channel" type="select" :label="text('channel','Published channel')"
        :options="[{value:'stable',label:'Stable'},{value:'beta',label:'Beta'},{value:'test',label:'Test'}]" :disabled="loading || busy" @update:model-value="catalog=null" />
      <p v-if="catalog">{{ text('published','Published release') }}: <code>{{ catalog.latest_release_id }}</code></p>
      <div class="actions"><UiButton :disabled="loading || busy" @click="check">{{ text('check','Check published package') }}</UiButton>
        <UiButton :disabled="!canPrepare" @click="prepare">{{ text('prepare','Download and prepare on this Node') }}</UiButton></div>
      <p v-if="operationId">{{ text('operation','Original operation') }}: <code>{{ operationId }}</code></p>
      <template v-if="status"><dl><dt>{{ text('release','Prepared release') }}</dt><dd><code>{{ status.release_id }}</code></dd>
        <dt>SHA-256</dt><dd><code>{{ status.archive_sha256 }}</code></dd>
        <dt>{{ text('preparation','Preparation') }}</dt><dd>{{ t('remoteAgentUpdates.state.'+status.state,status.state) }}</dd>
        <dt>{{ text('installation','Verified installation outcome') }}</dt><dd>{{ installed ? t('remoteAgentUpdates.state.'+installed.status,installed.status) : text('notInstalled','Not confirmed; a queued command is not installed software.') }}</dd></dl>
        <p v-if="installed?.previous_release_id">{{ text('previous','Previous release') }}: <code>{{ installed.previous_release_id }}</code></p>
        <p v-if="installed?.error_code" role="alert"><code>{{ installed.error_code }}</code></p>
        <UiButton variant="primary" :disabled="!canApply" @click="openReview">{{ text('review','Review this Node update') }}</UiButton></template>
      <p v-if="unknown" role="alert">{{ text('unconfirmed','Result unconfirmed. Read status; installation is never automatically repeated.') }}</p>
    </template>
    <UiDialog :open="review" :title="text('confirmTitle','Confirm exact Node update')" :close-label="text('close','Close')" @update:open="v=>{if(!v && !sending) review=false}">
      <p>{{ node?.label }} · <code>{{ selected }}</code></p><code>{{ status?.release_id }}</code><p>SHA-256: <code>{{ status?.archive_sha256 }}</code></p>
      <p>{{ text('confirmHelp','Restart this Node Agent through the verified Node installer. Temporary disconnection is expected. No bulk update, Core restart, device reset or new application rights.') }}</p>
      <p v-if="!reviewCurrent" role="alert">{{ text('changed','The reviewed operation changed. Close and review again.') }}</p>
      <label class="check"><input v-model="acknowledged" type="checkbox" :disabled="sending">{{ text('acknowledge','I approve this exact device, release and package hash.') }}</label>
      <label v-if="maintenanceOverrideRequired" class="check"><input v-model="override" type="checkbox" :disabled="sending">{{ text('override','I explicitly approve installation outside the maintenance window.') }}</label>
      <template #actions><UiButton :disabled="sending" @click="review=false">{{ text('close','Close') }}</UiButton>
        <UiButton variant="primary" :disabled="!canApply || !reviewCurrent || !acknowledged || maintenanceOverrideRequired && !override" @click="apply">{{ text('confirm','Confirm once') }}</UiButton></template>
    </UiDialog>
  </section>
</template>
<style scoped>
.remote-agents { margin-block:1.25rem; padding:1.25rem; min-width:0; color:var(--ui-text); background:var(--ui-surface); }
header,.actions { display:flex; flex-wrap:wrap; gap:.8rem; justify-content:space-between; align-items:start; }
header>div { flex:1 1 20rem; min-width:0; } .remote-agents>:not(:first-child),header p { margin-top:1rem; }
p { color:var(--ui-text-secondary); } dl { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,2fr); gap:.6rem 1rem; }
dd { margin:0; min-width:0; } code { overflow-wrap:anywhere; white-space:pre-wrap; color:var(--ui-text); }
.check { display:flex; align-items:start; gap:.6rem; margin-block:1rem; } [role=alert] { color:var(--ui-danger); }
@media(max-width:600px) { dl { grid-template-columns:minmax(0,1fr); } dt { font-weight:600; } }
</style>
