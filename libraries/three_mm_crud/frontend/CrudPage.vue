<template>
  <UiSurface class="crud-page">
    <header><h1>{{ label(definition.name) }}</h1><button :disabled="busy" @click="refresh()">{{ t.refresh }}</button></header>
    <UiState v-if="error" kind="error" :message="error" />
    <UiState v-if="busy && !records.length" kind="loading" :message="tableLabels.loading" />
    <section v-if="pending" class="panel" aria-live="polite">
      <p>{{ t.pending }} <code>{{ pending }}</code></p><p v-if="outcome">{{ statusText }}</p>
      <button :disabled="busy" @click="checkOutcome">{{ t.check }}</button>
      <label><input type="checkbox" v-model="reviewed" /> {{ t.review }}</label>
      <button :disabled="busy || !reviewed" @click="clearPending">{{ t.clear }}</button>
    </section>
    <button v-if="can('create')" :disabled="busy || !!pending" @click="start()">{{ t.new }} {{ label(entity?.label) }}</button>
    <UiForm v-if="editing" class="panel fields" :busy="busy" @submit="save">
      <UiField v-for="field in editable" :key="field.field_id" :id="`${formId}-${field.field_id}`"
        :label="label(field.label)" v-model="form[field.field_id]" :type="fieldType(field.kind)"
        :step="field.kind === 'number' ? 'any' : undefined" :required="field.required" />
      <div class="actions"><button type="submit" :disabled="busy || !!pending">{{ t.save }}</button><button type="button" :disabled="busy" @click="editing=false">{{ t.cancel }}</button></div>
    </UiForm>
    <UiTable v-if="!busy || records.length" class="panel" :rows="records" :columns="columns" :row-key="record => record.record_id"
      :caption="label(entity?.label)" :empty-label="t.empty" :busy="busy" :has-previous="!!cursor" :has-next="!!next"
      :previous-label="t.first" :next-label="t.next" :pagination-label="tableLabels.pages"
      @previous="cursor=''; refresh()" @next="cursor=next; refresh()">
      <template #cell="{ row, column }">
        <span v-if="column.key !== '__actions'">{{ format(row.data[column.key]) }}</span>
        <span v-else class="actions"><button v-if="can('update')" :disabled="busy || !!pending" @click="start(row)">{{ t.edit }}</button><button v-if="can('delete')" :disabled="busy || !!pending" @click="remove(row)">{{ t.delete }}</button></span>
      </template>
    </UiTable>
  </UiSurface>
</template>
<script setup lang="ts">
import { computed,onMounted,ref,useId } from 'vue'
import { UiSurface,UiForm,UiField,UiTable,UiState } from '@3mm/ui/v1'
import { useApplicationHost,type ApplicationPayload } from '@3mm/application-ui/v1'
type Localized={en:string;translations?:Record<string,string>}
type Field={field_id:string;label:Localized;kind:string;required?:boolean;read_only?:boolean}
type Entity={entity_id:string;label:Localized;fields:Field[]}
type Row={record_id:string;data:Record<string,any>;revision:number}
const props=defineProps<{definition:{name:Localized;entities:Entity[]};entityId:string;language?:string}>()
const host=useApplicationHost(),entity=computed(()=>props.definition.entities.find(e=>e.entity_id===props.entityId))
const formId=useId()
const editable=computed(()=>entity.value?.fields.filter(f=>!f.read_only)||[])
const columns=computed(()=>[...(entity.value?.fields.map(field=>({key:field.field_id,label:label(field.label)}))||[]),{key:'__actions',label:t.value.actions}])
const label=(value?:Localized)=>value?.translations?.[props.language||'en']||value?.en||''
const messages={en:{refresh:'Refresh',new:'New',edit:'Edit',delete:'Delete',save:'Save',cancel:'Cancel',empty:'No records.',actions:'Actions',first:'First page',next:'Next page',pending:'Review the outcome of this saved request:',check:'Check outcome',review:'I reviewed the current records and the command outcome.',clear:'Clear reviewed request',unavailable:'Access or storage is unavailable. No automatic retry.',confirm:'Delete this record?',storage:'Cannot preserve the request ID. Changes are blocked.'},
bg:{refresh:'Обнови',new:'Нов',edit:'Редактирай',delete:'Изтрий',save:'Запази',cancel:'Отказ',empty:'Няма записи.',actions:'Действия',first:'Първа страница',next:'Следваща страница',pending:'Прегледайте резултата от запазената заявка:',check:'Провери резултата',review:'Прегледах текущите записи и резултата от командата.',clear:'Освободи прегледаната заявка',unavailable:'Достъпът или данните са недостъпни. Няма автоматичен повторен опит.',confirm:'Да се изтрие ли този запис?',storage:'Идентификаторът на заявката не може да се запази. Промените са блокирани.'}}
const t=computed(()=>props.language?.startsWith('bg')?messages.bg:messages.en)
const tableLabels=computed(()=>props.language?.startsWith('bg')?{loading:'Зареждане…',pages:'Страници'}:{loading:'Loading…',pages:'Page navigation'})
const results={en:{stored:'Record saved.',deleted:'Record deleted.',missing:'The record is already absent.',conflict:'The record changed. Review the current data.',erased:'The old request belongs to erased data and was not repeated.',not_found:'No confirmed outcome for this actor. Review current records.',invalid:'The data was refused. Review the fields before a new request.',request_conflict:'This request ID already belongs to another change.',full:'The application limit was reached. Administrator maintenance is required.'},
bg:{stored:'Записът е запазен.',deleted:'Записът е изтрит.',missing:'Записът вече липсва.',conflict:'Записът е променен. Прегледайте текущите данни.',erased:'Старата заявка принадлежи на изтрити данни и не е повторена.',not_found:'Няма потвърден резултат за този потребител. Прегледайте текущите записи.',invalid:'Данните са отказани. Прегледайте полетата преди нова заявка.',request_conflict:'Идентификаторът вече принадлежи на друга промяна.',full:'Достигнат е лимитът на приложението. Нужна е администраторска поддръжка.'}}
const statusText=computed(()=>(results[props.language?.startsWith('bg')?'bg':'en'] as Record<string,string>)[outcome.value]||t.value.unavailable)
const records=ref<Row[]>([]),allowed=ref<string[]>([]),busy=ref(false),error=ref(''),cursor=ref(''),next=ref('')
const editing=ref(false),selected=ref<Row|null>(null),form=ref<Record<string,any>>({})
const pending=ref(''),reviewed=ref(false),outcome=ref('');let storageKey=''
const can=(action:string)=>allowed.value.includes(props.entityId+'_'+action)
const fieldType=(kind:string):'text'|'textarea'|'checkbox'|'number'|'date'|'datetime-local'=>{
  if(kind==='multiline')return 'textarea'
  if(kind==='boolean')return 'checkbox'
  if(kind==='integer'||kind==='number')return 'number'
  if(kind==='date')return 'date'
  if(kind==='datetime')return 'datetime-local'
  return 'text'
}
const format=(value:any)=>value===null||value===undefined?'—':typeof value==='boolean'?(value?'✓':'—'):String(value)
function start(row:Row|null=null){selected.value=row;form.value=Object.fromEntries(editable.value.map(f=>[f.field_id,row?.data[f.field_id]??(f.kind==='boolean'?false:'')]));editing.value=true}
async function read(){
  records.value=[];next.value=''
  const info=await host.getInfo();allowed.value=info.operations.map(item=>item.operation_id)
  storageKey=`3mm.crud.pending:${info.module_id}:${info.artifact_sha256}:${props.entityId}`
  pending.value=localStorage.getItem(storageKey)||''
  if(!can('list'))return
  const result=await host.invoke(props.entityId+'_list',{after:cursor.value})
  if(!Array.isArray(result.items)||!(result.next===null||typeof result.next==='string'))throw new Error('Invalid list response')
  records.value=result.items as unknown as Row[];next.value=typeof result.next==='string'?result.next:''
}
async function refresh(){if(busy.value)return;busy.value=true;error.value='';try{await read()}catch{records.value=[];allowed.value=[];error.value=t.value.unavailable}finally{busy.value=false}}
function clearPending(){if(!reviewed.value||busy.value)return;try{localStorage.removeItem(storageKey);pending.value='';reviewed.value=false;outcome.value=''}catch{error.value=t.value.storage}}
async function checkOutcome(){if(busy.value||!pending.value)return;busy.value=true;try{const result=await host.invoke(props.entityId+'_outcome',{request_id:pending.value});outcome.value=String(result.status);await read()}catch{error.value=t.value.unavailable}finally{busy.value=false}}
async function command(action:string,payload:ApplicationPayload){
  if(busy.value||pending.value)return
  let request:string
  try{
    request=Array.from(crypto.getRandomValues(new Uint8Array(16)),byte=>byte.toString(16).padStart(2,'0')).join('')
    if(!storageKey)throw new Error();localStorage.setItem(storageKey,request)
  }catch{error.value=t.value.storage;return}
  pending.value=request;reviewed.value=false;busy.value=true;error.value=''
  try{
    const result=await host.invoke(props.entityId+'_'+action,payload,{idempotencyKey:request})
    if(!['stored','deleted','missing','conflict','erased','invalid','request_conflict','full'].includes(String(result.status)))throw new Error('Invalid result')
    outcome.value=String(result.status);editing.value=false
    // Explicit refresh reads data and never repeats a command. Keep the ID until
    // the user reviews the outcome, including stale-revision conflicts.
    await read()
  }catch{error.value=t.value.unavailable}finally{busy.value=false}
}
async function save(){
  const data:ApplicationPayload={}
  for(const field of editable.value){const value=form.value[field.field_id];data[field.field_id]=value===''&&!field.required?null:['integer','number'].includes(field.kind)?Number(value):value}
  if(selected.value)await command('update',{record_id:selected.value.record_id,expected_revision:selected.value.revision,data})
  else await command('create',{data})
}
async function remove(row:Row){if(window.confirm(t.value.confirm))await command('delete',{record_id:row.record_id,expected_revision:row.revision})}
onMounted(refresh)
</script>
<style scoped>
.crud-page{display:grid;gap:1rem;min-width:0;color:var(--text-primary)}
header,.actions{display:flex;gap:.6rem;justify-content:space-between;align-items:center}h1{font-size:1.8rem}
.panel{min-width:0;padding:1.2rem;background:var(--card-bg);border:1px solid var(--card-border);border-radius:.7rem}
.fields :deep(fieldset){grid-template-columns:repeat(2,minmax(0,1fr))}.fields .actions{grid-column:1/-1}
button{color:var(--text-primary);background:var(--input-bg,var(--card-bg));border:1px solid var(--card-border);border-radius:.4rem;padding:.5rem .7rem}button:disabled{opacity:.55}
@media(max-width:700px){.fields :deep(fieldset){grid-template-columns:1fr}header{align-items:flex-start}.actions{flex-wrap:wrap}}
</style>
