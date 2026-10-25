<template>
  <section class="debug-workspace" aria-labelledby="debug-workspace-title">
    <div class="workspace-heading">
      <div><h3 id="debug-workspace-title">{{ t('diagnostics.workspace.title', 'Operation diagnostics') }}</h3>
        <p>{{ t('diagnostics.workspace.help', 'Trace a selected operation for a limited time. Diagnostics do not change execution permissions.') }}</p></div>
      <button class="ui-button ui-button--secondary" :disabled="busy || loading" @click="refresh">{{ t('diagnostics.workspace.refresh', 'Refresh observations') }}</button>
    </div>
    <p v-if="error" class="workspace-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">{{ t('diagnostics.loading', 'Checking device…') }}</p>
    <div class="component-grid">
      <article v-for="item in components" :key="item.component" class="component-card">
        <div><strong>{{ componentName(item.component) }}</strong><span class="ui-badge" :class="{ 'workspace-warning': item.health !== 'ready' }">{{ healthName(item.health) }}</span></div>
        <code v-if="item.version">{{ item.version }}</code>
        <code v-else-if="item.loaded_build_id || item.build_id" :title="item.loaded_build_id || item.build_id || undefined">{{ (item.loaded_build_id || item.build_id || '').slice(0, 12) }}</code>
        <small v-else>{{ t('diagnostics.workspace.noVersion', 'Version unavailable') }}</small>
        <small>{{ reasonName(item.reason) }}</small>
      </article>
    </div>
    <details v-if="Object.keys(coreServices).length" class="core-services">
      <summary>{{ t('diagnostics.workspace.coreServices', 'Core service observations') }}</summary>
      <p v-for="(item, name) in coreServices" :key="name"><code>{{ name }}</code> · {{ item.state }} · {{ item.reason }}</p>
    </details>
    <div class="session-state" role="status">
      <strong>{{ active ? t('diagnostics.workspace.active', 'Diagnostic session active') : t('diagnostics.workspace.normal', 'Normal mode — detailed recording is off') }}</strong>
      <span v-if="session?.session_id">{{ remaining }} s · {{ session.records }} {{ t('diagnostics.workspace.records', 'records') }} · {{ dropped }} {{ t('diagnostics.workspace.dropped', 'dropped') }}</span>
      <small>{{ t('diagnostics.workspace.expiry', 'Recording expires automatically. Restarting a component does not resume it.') }}</small>
    </div>
    <form class="session-form" @submit.prevent="start">
      <label>{{ t('diagnostics.workspace.profile', 'Profile') }}<select v-model="profile" :disabled="active || busy"><option value="diagnostic">{{ t('diagnostics.workspace.diagnostic', 'Diagnostic session') }}</option><option value="development">{{ t('diagnostics.workspace.development', 'Development') }}</option></select></label>
      <label>{{ t('diagnostics.workspace.ttl', 'Duration') }}<select v-model.number="ttl" :disabled="active || busy"><option v-for="seconds in [60, 300, 600, 1800]" :key="seconds" :value="seconds">{{ seconds / 60 }} min</option></select></label>
      <label>{{ t('diagnostics.workspace.operation', 'Operation') }}<select v-model="operation" :disabled="active || busy"><option value="">{{ t('diagnostics.workspace.allOperations', 'All supported operations') }}</option><option v-for="value in operations" :key="value" :value="value">{{ value }}</option></select></label>
      <label>{{ t('diagnostics.workspace.instance', 'Instance ID (optional)') }}<input v-model.trim="instance" pattern="[0-9a-f]{24}" maxlength="24" :disabled="active || busy" autocomplete="off" /></label>
      <div class="session-actions"><button type="submit" class="ui-button ui-button--primary" :disabled="active || busy">{{ t('diagnostics.workspace.start', 'Start recording') }}</button>
        <button type="button" class="ui-button ui-button--secondary" :disabled="!active || busy" @click="stop">{{ t('diagnostics.workspace.stop', 'Stop now') }}</button>
        <button type="button" class="ui-button ui-button--secondary" :disabled="busy || !session?.session_id" @click="download">{{ t('diagnostics.workspace.export', 'Export safe records') }}</button></div>
    </form>
    <div class="timeline-heading"><h4>{{ t('diagnostics.workspace.timeline', 'Shared timeline') }}</h4>
      <label class="import-control">{{ t('diagnostics.workspace.import', 'Merge a local producer export') }}<input type="file" accept=".ndjson" :disabled="busy" @change="importRecords" /></label>
    </div>
    <p class="workspace-note">{{ t('diagnostics.workspace.safe', 'Only fixed metadata is recorded. Request bodies, files, terminal output, tokens and arbitrary logs are excluded.') }}</p>
    <p class="workspace-note">{{ t('diagnostics.workspace.clock', 'Time order reflects producer clocks; trace IDs correlate a transport hop.') }}</p>
    <p v-if="imported" class="workspace-note">{{ t('diagnostics.workspace.imported', 'Imported records are a local snapshot, not live component state. Refresh clears this merge.') }}</p>
    <ul v-if="producerSessions.length" class="producer-sessions"><li v-for="item in producerSessions" :key="item.component">{{ componentName(item.component) }} · {{ t('diagnostics.workspace.atExport', 'At export:') }} {{ item.records }} {{ t('diagnostics.workspace.records', 'records') }} · {{ Object.values(item.dropped).reduce((a,b) => a+b,0) }} {{ t('diagnostics.workspace.dropped', 'dropped') }}</li></ul>
    <button v-if="imported" class="ui-button ui-button--secondary" @click="saveMerged">{{ t('diagnostics.workspace.saveMerged', 'Save merged snapshot') }}</button>
    <p v-if="missing.length" class="workspace-note">{{ t('diagnostics.workspace.missing', 'No trace export from:') }} {{ missing.map(componentName).join(', ') }}</p>
    <p v-if="truncated" class="workspace-warning" role="status">{{ t('diagnostics.workspace.truncated', 'The display is limited. Export records for the complete bounded snapshot.') }}</p>
    <label class="trace-filter">{{ t('diagnostics.workspace.trace', 'Filter by trace ID') }}<input v-model.trim="traceFilter" maxlength="48" autocomplete="off" /></label>
    <div class="timeline-scroll" tabindex="0" :aria-label="t('diagnostics.workspace.timeline', 'Shared timeline')">
      <table v-if="filtered.length"><thead><tr><th>{{ t('diagnostics.workspace.when', 'Time') }}</th><th>{{ t('diagnostics.workspace.component', 'Component') }}</th><th>{{ t('diagnostics.workspace.stage', 'Operation / stage') }}</th><th>{{ t('diagnostics.workspace.result', 'Result / reason') }}</th><th>ms</th><th>Trace ID</th></tr></thead>
        <tbody><tr v-for="(item,index) in filtered" :key="index"><td>{{ new Date(item.timestamp * 1000).toLocaleTimeString() }}</td><td>{{ componentName(item.component) }}<small v-if="item.source === 'imported'">{{ t('diagnostics.workspace.importedLabel', 'Imported') }}</small></td><td>{{ item.operation }}<small>{{ item.span_id }}</small></td><td>{{ item.result }}<small>{{ item.reason }}</small></td><td>{{ item.duration_ms }}</td><td><button class="trace-link" @click="traceFilter = item.trace_id">{{ item.trace_id }}</button></td></tr></tbody></table>
      <p v-else>{{ t('diagnostics.workspace.empty', 'No matching records. Start a session and perform the selected operation.') }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'
const { t } = useI18n()
type Component = { component: string; version?: string; build_id: string | null; loaded_build_id?: string; health: string; reason: string }
type Session = { session_id: string | null; active: boolean; remaining_seconds: number; records: number; dropped: Record<string,number>; scope?: { profile: string; operation: string | null; instance_id: string | null } }
type RecordRow = { timestamp: number; component: string; operation: string; span_id: string; result: string; reason: string; duration_ms: number; trace_id: string; source: string }
const components = ref<Component[]>([]), coreServices = ref<Record<string,{state:string;reason:string}>>({})
const session = ref<Session | null>(null), rows = ref<RecordRow[]>([]), missing = ref<string[]>([])
const operations = ref<string[]>([]), profile = ref('diagnostic'), operation = ref(''), instance = ref(''), ttl = ref(600)
const producerSessions = ref<{component:string;records:number;dropped:Record<string,number>}[]>([])
const mergedSnapshot = ref<any>(null)
const traceFilter = ref(''), error = ref(''), busy = ref(false), loading = ref(false), remaining = ref(0), truncated = ref(false), imported = ref(false)
const active = computed(() => !!session.value?.active && remaining.value > 0)
const dropped = computed(() => Object.values(session.value?.dropped || {}).reduce((a,b) => a+b,0))
const filtered = computed(() => rows.value.filter(row => !traceFilter.value || row.trace_id.includes(traceFilter.value)))
let expiryAt = 0, generation = 0, disposed = false, timer: ReturnType<typeof setInterval> | undefined
function componentName(value:string) { return t('diagnostics.components.' + value, ({core:'Core',sdk:'SDK',runtime:'Platform Runtime','platform-runtime':'Platform Runtime','connector-worker':'Connector worker',agent:'Agent',setup:'Setup','application-host':'Application host','public-web':'Public HTTP','session-worker':'Session worker'} as Record<string,string>)[value] || value) }
function healthName(value:string) { return t('diagnostics.workspace.health.'+value, ({ready:'Ready',unavailable:'Unavailable',unknown:'Not observed'} as Record<string,string>)[value] || 'Not observed') }
function reasonName(value:string) { return t('diagnostics.workspace.reason.'+value, ({collector_busy:'Another observation is in progress; refresh shortly',core_management:'Management API responding',live_probe:'Live component response',passive_metadata:'Installed; process health has not been observed',metadata_unavailable:'Installed metadata is unavailable',probe_unavailable:'No confirmed component response'} as Record<string,string>)[value] || 'Observation unavailable') }
function failure() { error.value = t('diagnostics.workspace.failed','Diagnostics are unavailable. Check your access and refresh observations.') }
function applySession(value:Session) { session.value=value;remaining.value=Math.max(0,value.remaining_seconds || 0);expiryAt=Date.now()+remaining.value*1000;if(value.active && value.scope){profile.value=value.scope.profile;operation.value=value.scope.operation || '';instance.value=value.scope.instance_id || ''} }
function applyTimeline(data:any) { mergedSnapshot.value=data;producerSessions.value=Array.isArray(data.sessions)?data.sessions.filter((value:any)=>value.source==='imported'):[];rows.value=Array.isArray(data.records)?data.records:[];missing.value=Array.isArray(data.missing_components)?data.missing_components:[];truncated.value=!!data.truncated }
async function refresh() {
  const current=++generation;loading.value=true;error.value=''
  const results=await Promise.allSettled([http.get('/api/v1/diagnostics/workspace'),http.get('/api/v1/diagnostics/session'),http.get('/api/v1/diagnostics/timeline')])
  if(disposed || current!==generation)return
  const [workspace,state,timeline]=results
  if(workspace.status==='fulfilled'){components.value=Array.isArray(workspace.value.data.components)?workspace.value.data.components:[];coreServices.value=workspace.value.data.core_services?.components || {};operations.value=workspace.value.data.operations || []}
  if(state.status==='fulfilled')applySession(state.value.data)
  if(timeline.status==='fulfilled'){applyTimeline(timeline.value.data);imported.value=false}
  if(results.some(result=>result.status==='rejected'))failure()
  loading.value=false
}
async function change(action:()=>Promise<any>) { busy.value=true;error.value='';++generation;let failed=false;try{const response=await action();if(!disposed)applySession(response.data)}catch{failed=true}finally{if(!disposed){busy.value=false;await refresh();if(failed)failure()}} }
async function start(){await change(()=>http.post('/api/v1/diagnostics/session',{ttl_seconds:ttl.value,profile:profile.value,operation:operation.value || null,instance_id:instance.value || null}))}
async function stop(){await change(()=>http.delete('/api/v1/diagnostics/session'))}
async function download(){busy.value=true;error.value='';try{const response=await http.get('/api/v1/diagnostics/session/records',{responseType:'blob'});if(disposed)return;const url=URL.createObjectURL(new Blob([response.data],{type:'application/x-ndjson'}));try{const anchor=document.createElement('a');anchor.href=url;anchor.download='3mm-operation-records.ndjson';anchor.click()}finally{URL.revokeObjectURL(url)}}catch{if(!disposed)failure()}finally{if(!disposed)busy.value=false}}
function saveMerged(){if(!mergedSnapshot.value)return;const url=URL.createObjectURL(new Blob([JSON.stringify(mergedSnapshot.value,null,2)],{type:'application/json'}));try{const anchor=document.createElement('a');anchor.href=url;anchor.download='3mm-merged-diagnostics.json';anchor.click()}finally{URL.revokeObjectURL(url)}}
async function importRecords(event:Event){const input=event.target as HTMLInputElement;const file=input.files?.[0];if(!file)return;input.value='';if(file.size>4*1024*1024){error.value=t('diagnostics.workspace.tooLarge','Export exceeds the 4 MiB import limit.');return}busy.value=true;error.value='';const current=++generation;try{const response=await http.post('/api/v1/diagnostics/timeline/merge',await file.text(),{headers:{'Content-Type':'application/x-ndjson'}});if(!disposed && current===generation){applyTimeline(response.data);imported.value=true}}catch{if(!disposed)failure()}finally{if(!disposed)busy.value=false}}
onMounted(()=>{void refresh();timer=setInterval(()=>{remaining.value=Math.max(0,Math.ceil((expiryAt-Date.now())/1000))},1000)})
onUnmounted(()=>{disposed=true;++generation;if(timer)clearInterval(timer)})
</script>

<style scoped>
.debug-workspace { margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px solid var(--ui-border); }
.workspace-heading,.timeline-heading { display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap; }
h3,h4,p { margin:0 0 .6rem; } h3 { font-size:1.1rem; } h4 { font-size:1rem; }
.workspace-heading p,.workspace-note,small { color:var(--ui-text-muted); }
.component-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.65rem; margin:1rem 0; }
.component-card { padding:.85rem; border:1px solid var(--ui-border); border-radius:var(--ui-radius-sm); background:var(--ui-surface-alt); min-width:0; }
.component-card>div { display:flex; justify-content:space-between; gap:.5rem; margin-bottom:.5rem; } small { display:block; overflow-wrap:anywhere; }
.session-state { display:grid; gap:.35rem; border-left:3px solid var(--ui-accent); padding:.8rem 1rem; margin:1rem 0; background:var(--ui-surface-alt); }
.session-form { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,12rem),1fr)); gap:.75rem; margin-bottom:1.5rem; }
label { display:grid; gap:.35rem; min-width:0; font-size:.9rem; }
input,select { width:100%; min-width:0; color:var(--ui-text); background:var(--ui-surface); border:1px solid var(--ui-border); border-radius:var(--ui-radius-sm); padding:.5rem; }
.session-actions { grid-column:1/-1; display:flex; flex-wrap:wrap; gap:.5rem; }.workspace-error { color:var(--ui-danger); }.workspace-warning { color:var(--ui-warning); }
.trace-filter { max-width:32rem; margin:1rem 0; }.timeline-scroll { overflow-x:auto; border:1px solid var(--ui-border); border-radius:var(--ui-radius-sm); padding:.5rem; }
table { width:100%; border-collapse:collapse; font-size:.85rem; }th,td { text-align:left; padding:.6rem; vertical-align:top; border-bottom:1px solid var(--ui-border); }th { white-space:nowrap; }
.trace-link { color:var(--ui-accent); background:none; border:0; padding:0; font-family:monospace; text-align:left; overflow-wrap:anywhere; }
.core-services p { font-size:.85rem; }.import-control { max-width:22rem; }.workspace-note { font-size:.85rem; margin:.6rem 0; }
@media(max-width:950px){.component-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }}
@media(max-width:600px){.component-grid { grid-template-columns:minmax(0,1fr); }.workspace-heading>.ui-button,.session-actions .ui-button { width:100%; }.component-card>div { flex-wrap:wrap; }}
</style>
