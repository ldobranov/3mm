<script setup lang="ts">
import { ref,computed,onMounted,onBeforeUnmount } from 'vue'
import UiDialog from '../ui/UiDialog.vue'
import UiButton from '../ui/UiButton.vue'
import { useKioskLabels } from '@/utils/kiosk-labels'
import { kioskRequest,KioskError } from '@/utils/kiosk-api'
import { kioskRandomId } from '@/utils/kiosk-session'
const props=defineProps<{moduleId:string;name:string;active:boolean}>(),emit=defineEmits<{close:[]}>(),label=useKioskLabels()
type Terminal={terminal_id:string;label:string;enabled:boolean;needs_pairing:boolean;last_seen_at:string|null}
type Draft={request_id:string;label:string;expires_in_minutes:number}
const items=ref<Terminal[]>([]),name=ref(''),minutes=ref(15),busy=ref(false),message=ref(''),code=ref(''),expires=ref(''),copied=ref(false),draft=ref<Draft|null>(null)
const key='threeMmKioskEnrollmentV1:'+props.moduleId
const connectionLink=computed(()=>{if(!code.value)return '';const link=new URL('/kiosk/connect',location.origin);link.hash=new URLSearchParams({module:props.moduleId,code:code.value}).toString();return link.toString()})
const canCopy=typeof navigator.clipboard?.writeText==='function'
let disposed=false
function saveDraft(value:Draft|null){try{if(value)sessionStorage.setItem(key,JSON.stringify(value));else sessionStorage.removeItem(key)}catch{throw new KioskError('storage')}}
async function load(){
  const value=await kioskRequest(props.moduleId,'terminals',undefined,true)
  if(disposed)return
  const rows=(value as {items?:unknown}).items
  if(!Array.isArray(rows)||rows.some(v=>!v||typeof v.terminal_id!=='string'||!/^[a-f0-9]{32}$/.test(v.terminal_id)||typeof v.label!=='string'||typeof v.enabled!=='boolean'||typeof v.needs_pairing!=='boolean'))throw new KioskError('unavailable')
  items.value=rows.map(v=>({terminal_id:v.terminal_id,label:v.label,enabled:v.enabled,needs_pairing:v.needs_pairing,last_seen_at:v.last_seen_at}))
}
async function refresh(){if(busy.value)return;busy.value=true;message.value='';try{await load()}catch(error){if(!disposed){items.value=[];message.value=label(error instanceof KioskError?error.code:'unavailable')}}finally{if(!disposed)busy.value=false}}
async function create(){
  if(busy.value||!props.active)return
  busy.value=true;message.value='';copied.value=false
  try{
    if(!draft.value){const value={request_id:kioskRandomId(),label:name.value.trim(),expires_in_minutes:minutes.value};saveDraft(value);draft.value=value}
    const value=await kioskRequest(props.moduleId,'enrollments',draft.value,true) as Record<string,unknown>
    if(disposed)return
    if(value.request_id!==draft.value.request_id||typeof value.code!=='string'||!/^[A-Za-z0-9_-]{32}$/.test(value.code)||typeof value.expires_at!=='string'||!Number.isFinite(Date.parse(value.expires_at)))throw new KioskError('unavailable')
    code.value=value.code;expires.value=value.expires_at
  }catch(error){if(!disposed)message.value=label(error instanceof KioskError?error.code:'unavailable')}
  finally{if(!disposed)busy.value=false}
}
function discard(){try{saveDraft(null);draft.value=null;code.value='';expires.value='';message.value=''}catch{message.value=label('storage')}}
async function revoke(id:string){if(busy.value)return;busy.value=true;message.value='';try{await kioskRequest(props.moduleId,'terminals/'+id,undefined,true,'DELETE');if(!disposed)await load()}catch(error){if(!disposed)message.value=label(error instanceof KioskError?error.code:'unavailable')}finally{if(!disposed)busy.value=false}}
async function copy(){try{await navigator.clipboard.writeText(connectionLink.value);copied.value=true}catch{message.value=label('copyHelp')}}
onMounted(()=>{
  try{const raw=sessionStorage.getItem(key);if(raw){const v=JSON.parse(raw);if(!v||typeof v.request_id!=='string'||!/^[a-f0-9]{32}$/.test(v.request_id)||typeof v.label!=='string'||!v.label.trim()||v.label.length>120||!Number.isInteger(v.expires_in_minutes)||v.expires_in_minutes<1||v.expires_in_minutes>1440)throw new KioskError('storage');draft.value=v;name.value=v.label;minutes.value=v.expires_in_minutes}}catch{message.value=label('storage')}
  void refresh()
})
onBeforeUnmount(()=>{disposed=true;code.value=''})
</script>
<template>
  <UiDialog :open="true" :title="label('terminals')" :close-label="label('close')" @update:open="emit('close')">
    <h2>{{ props.name }}</h2>
    <p v-if="message" role="alert" class="error-message">{{ message }}</p>
    <p v-if="!props.active" class="ui-help">{{ label('stopped') }}</p>
    <form class="kiosk-form" @submit.prevent="create">
      <label>{{ label('label') }}<input v-model="name" class="ui-control" required maxlength="120" :disabled="busy || Boolean(draft)"></label>
      <label>{{ label('minutes') }}<input v-model.number="minutes" class="ui-control" required type="number" min="1" max="1440" :disabled="busy || Boolean(draft)"></label>
      <UiButton type="submit" variant="primary" :disabled="!props.active || !name.trim()" :loading="busy">{{ draft?label('recover'):label('create') }}</UiButton>
    </form>
    <p v-if="draft" class="ui-help">{{ label('request') }}: <code>{{ draft.request_id }}</code></p>
    <p v-if="draft && !code" role="status">{{ label('uncertain') }}</p>
    <div v-if="code" class="kiosk-code"><p>{{ label('codeHelp') }}</p><code>{{ code }}</code><p>{{ expires }}</p>
      <label>{{ label('connectionLink') }}<input class="ui-control" readonly :value="connectionLink" autocomplete="off"></label>
      <p class="ui-help">{{ label('copyHelp') }}</p><UiButton v-if="canCopy" @click="copy">{{ copied?label('copied'):label('copy') }}</UiButton>
    </div>
    <UiButton v-if="draft" :disabled="busy" @click="discard">{{ label('newCode') }}</UiButton>
    <div class="kiosk-list" aria-live="polite">
      <p v-if="!items.length && !busy">{{ label('empty') }}</p>
      <article v-for="item in items" :key="item.terminal_id" class="kiosk-terminal">
        <strong>{{ item.label }}</strong><code>{{ item.terminal_id }}</code>
        <span>{{ item.needs_pairing?label('pairAgain'):item.enabled?label('active'):label('revoked') }}</span>
        <UiButton :disabled="busy || (!item.enabled && !item.needs_pairing)" variant="danger" @click="revoke(item.terminal_id)">{{ label('revoke') }}</UiButton>
      </article>
    </div>
    <template #actions><UiButton :disabled="busy" @click="refresh">{{ label('refresh') }}</UiButton><UiButton @click="emit('close')">{{ label('close') }}</UiButton></template>
  </UiDialog>
</template>
<style scoped>
.kiosk-form,.kiosk-form label,.kiosk-terminal,.kiosk-code label{display:grid;gap:var(--ui-space-2,.5rem)}
.kiosk-list,.kiosk-code{margin-block:var(--ui-space-4,1.5rem)}
.kiosk-terminal{padding-block:var(--ui-space-3,1rem);border-top:1px solid var(--ui-border);overflow-wrap:anywhere}
.kiosk-code code{overflow-wrap:anywhere}
</style>
