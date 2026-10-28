<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useApplicationHost } from '@3mm/application-ui/v1'
import { UiSurface, UiButton, UiState } from '@3mm/ui/v1'

const files=useApplicationHost().files, selected=ref(null), fileId=ref('sample'), busy=ref(false), message=ref(''), items=ref([]), next=ref(null)
const key='3mm.file-probe.upload.v1', upload=ref(null), progress=ref(0), share=ref(null), preview=ref(null)
let stop=false
try { upload.value=JSON.parse(localStorage.getItem(key)||'null') } catch { upload.value=null }
function save(){if(upload.value)localStorage.setItem(key,JSON.stringify(upload.value));else localStorage.removeItem(key)}
async function run(action){if(busy.value)return;busy.value=true;message.value='';try{await action()}catch(error){message.value=error.code==='unconfirmed'?'Outcome unconfirmed. Use upload status or inspect the receipt before another action. Request: '+(error.requestId||'chunk; inspect saved offset'):String(error.message||error)}finally{busy.value=false}}
async function refresh(after=''){const value=await files.list(after);items.value=value.items;next.value=value.after}
function pick(event){selected.value=event.target.files?.[0]||null}
async function prepare(){await run(async()=>{
  if(!selected.value||selected.value.size>8*1024*1024)throw new Error('Choose a file up to 8 MiB')
  const sha256=await files.checksum(selected.value)
  const started=await files.begin(fileId.value,selected.value,{sha256,filename:selected.value.name,contentType:selected.value.type||'application/octet-stream'})
  upload.value={upload_id:started.upload_id,file_id:fileId.value,sha256,size_bytes:selected.value.size,offset:0};save();progress.value=0
})}
async function inspect(){await run(async()=>{if(!upload.value)return;const value=await files.uploadStatus(upload.value.upload_id);upload.value.offset=value.upload.offset;save();progress.value=value.upload.offset;message.value='Confirmed offset: '+value.upload.offset})}
async function send(){await run(async()=>{
  if(!upload.value||!selected.value)throw new Error('Select the original file to resume')
  if(selected.value.size!==upload.value.size_bytes||await files.checksum(selected.value)!==upload.value.sha256)throw new Error('Selected file does not match this upload')
  const value=await files.uploadStatus(upload.value.upload_id);upload.value.offset=value.upload.offset;stop=false
  while(upload.value.offset<selected.value.size&&!stop){const offset=upload.value.offset;const chunk=selected.value.slice(offset,offset+256*1024);const result=await files.append(upload.value.upload_id,offset,chunk);upload.value.offset=result.offset;progress.value=result.offset;save()}
  if(stop){message.value='Paused. Resume checks the confirmed offset.';return}
  const result=await files.finalize(upload.value.upload_id);message.value='Checksum confirmed: '+result.file.sha256;upload.value=null;save();await refresh()
})}
async function cancel(){await run(async()=>{await files.cancel(upload.value.upload_id);upload.value=null;save()})}
async function bytes(item){if(item.size_bytes>8*1024*1024)throw new Error('Demo download limit is 8 MiB');const stream=await files.download(item.file_id),reader=stream.getReader(),parts=[];for(;;){const part=await reader.read();if(part.done)break;parts.push(part.value)}return new Blob(parts,{type:item.origin?item.content_type:'application/octet-stream'})}
async function download(item){await run(async()=>{const url=URL.createObjectURL(await bytes(item)),anchor=document.createElement('a');anchor.href=url;anchor.download=item.filename;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000)})}
async function thumbnail(item){await run(async()=>{const value=await files.transform(item.file_id,item.sha256,{outputId:item.file_id.slice(0,52)+'_preview',width:256,height:256,format:'webp'});message.value='Image job: '+value.job.status+(value.job.error_code?' · '+value.job.error_code:'');await refresh()})}
async function show(item){await run(async()=>{if(!item.origin||!['image/png','image/jpeg','image/webp'].includes(item.content_type))throw new Error('Preview is available for verified image derivatives');if(preview.value)URL.revokeObjectURL(preview.value);preview.value=URL.createObjectURL(await bytes(item))})}
async function createLink(item){await run(async()=>{share.value=await files.createLink(item.file_id,item.sha256,{ttlSeconds:300,maxDownloads:3})})}
async function revokeLink(){await run(async()=>{await files.revokeLink(share.value.linkId);share.value=null;message.value='Link revoked'})}
async function remove(item){await run(async()=>{await files.remove(item.file_id,item.sha256);await refresh()})}
onMounted(()=>run(()=>refresh()))
onBeforeUnmount(()=>{stop=true;if(preview.value)URL.revokeObjectURL(preview.value)})
</script>
<template>
  <main class="file-probe"><h1>File and media probe</h1>
    <p>Private files · maximum 8 MiB per file / 32 MiB total / 64 files. Image processing is optional.</p>
    <UiState v-if="message" kind="empty" :message="message" />
    <UiSurface><h2>Upload</h2><label>Logical file ID <input v-model="fileId" pattern="[a-z][a-z0-9_]{0,63}" :disabled="busy||!!upload" /></label>
      <label>Choose a file <input type="file" @change="pick" :disabled="busy" /></label>
      <p v-if="selected">{{ selected.name }} · {{ selected.size }} bytes</p>
      <UiButton v-if="!upload" :disabled="busy||!selected" @click="prepare">Prepare upload</UiButton>
      <template v-else><p>Upload {{ upload.upload_id }} · {{ progress||upload.offset }} / {{ upload.size_bytes }} bytes</p>
        <progress :value="progress||upload.offset" :max="upload.size_bytes||1" aria-label="Upload progress" />
        <UiButton :disabled="busy" @click="inspect">Check confirmed offset</UiButton>
        <UiButton :disabled="busy||!selected" @click="send">Send / resume and finalize</UiButton>
        <UiButton v-if="busy" @click="stop=true">Pause after this chunk</UiButton>
        <UiButton :disabled="busy" @click="cancel">Cancel upload</UiButton>
      </template>
    </UiSurface>
    <UiSurface><h2>Stored files</h2><UiButton :disabled="busy" @click="run(()=>refresh())">Refresh first page</UiButton>
      <UiState v-if="!items.length" kind="empty" message="No files on this page" />
      <article v-for="item in items" :key="item.file_id"><h2>{{ item.filename }}</h2><p>{{ item.file_id }} · {{ item.size_bytes }} bytes · {{ item.content_type }}</p><p class="digest">{{ item.sha256 }}</p>
        <p v-if="item.origin">Derivative of {{ item.origin.file_id }} · job {{ item.origin.job_id }}</p>
        <UiButton :disabled="busy" @click="download(item)">Download</UiButton>
        <UiButton :disabled="busy" @click="thumbnail(item)">Create 256px image derivative</UiButton>
        <UiButton v-if="item.origin" :disabled="busy" @click="show(item)">Preview derivative</UiButton>
        <UiButton :disabled="busy" @click="createLink(item)">Share for 5 minutes / 3 downloads</UiButton>
        <UiButton :disabled="busy" @click="remove(item)">Delete file</UiButton>
      </article><UiButton v-if="next" :disabled="busy" @click="run(()=>refresh(next))">Next page</UiButton>
    </UiSurface>
    <UiSurface v-if="share"><h2>Temporary download link</h2><a :href="share.url" target="_blank" rel="noreferrer noopener">Open download link</a><p class="digest">{{ share.url }}</p><UiButton :disabled="busy" @click="revokeLink">Revoke link</UiButton></UiSurface>
    <UiSurface v-if="preview"><h2>Image derivative</h2><img :src="preview" alt="Generated image derivative" /></UiSurface>
  </main>
</template>
<style scoped>
.file-probe{max-width:64rem;margin:auto;padding:1rem}label{display:block;margin:.75rem 0}article{border-top:1px solid var(--ui-border);padding:1rem 0}.digest{overflow-wrap:anywhere}img{max-width:100%;height:auto}progress{display:block;max-width:100%}
</style>
