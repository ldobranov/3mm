<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useApplicationHost } from '@3mm/application-ui/v1'
const sessions=useApplicationHost().sessions
const state=ref('Not connected'), output=ref(''), target=ref<any>(null)
let sid='', remove=()=>{}
const append=(data:Uint8Array)=>{ output.value=(output.value+new TextDecoder().decode(data)).slice(-32768) }
async function refresh(){
  try{ const list=await sessions!.targets(); target.value=list.find(v=>v.available)||null }
  catch{ state.value='Current access unavailable' }
}
async function connect(){
  if(!sessions||!target.value||sid)return
  state.value='Connecting'
  try{
    const bytes=crypto.getRandomValues(new Uint8Array(16))
    const request_id='probe_'+Array.from(bytes,v=>v.toString(16).padStart(2,'0')).join('')
    const t=target.value
    const value=await sessions.open({session_request_version:1,request_id,device_id:t.deviceId,provider_id:t.providerId,
      capability_id:t.capabilityIds[0],access_mode:t.accessMode,options:t.options})
    sid=value.session_id
    remove=sessions.observe(sid,{onData:append,onClosed:()=>{sid='';state.value='Disconnected'}})
    state.value='Connected'
  }catch{state.value='Connection unconfirmed'}
}
async function facts(){ try{ await sessions!.sendData(sid,new TextEncoder().encode('facts')) }catch{state.value='Input unconfirmed'} }
async function resize(){
  try{ const id='resize_'+Array.from(crypto.getRandomValues(new Uint8Array(8)),v=>v.toString(16).padStart(2,'0')).join('')
    await sessions!.control({session_id:sid,control_id:id,action:'resize',arguments:{cols:99,rows:31}})
  }catch{state.value='Control unconfirmed'}
}
async function close(){ if(!sid)return; try{await sessions!.close(sid);sid='';state.value='Disconnected'}catch{state.value='Cleanup unconfirmed'} }
onMounted(refresh)
onBeforeUnmount(()=>{remove();void close()})
</script>
<template>
  <section><h1>Session platform probe</h1><p>Disposable independent SDK provider</p>
    <p role="status">{{state}}</p><p v-if="target">Target: {{target.deviceId}}</p>
    <button :disabled="!target||state==='Connecting'||state==='Connected'" @click="connect">Connect</button>
    <button :disabled="state!=='Connected'" @click="facts">Read isolation facts</button>
    <button :disabled="state!=='Connected'" @click="resize">Resize</button>
    <button :disabled="state!=='Connected'" @click="close">Disconnect</button>
    <pre style="white-space:pre-wrap;overflow-wrap:anywhere">{{output}}</pre>
  </section>
</template>
