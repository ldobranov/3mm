<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import UiSurface from '@/extension-ui/UiSurface.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { useKioskLabels } from '@/utils/kiosk-labels'
import { beginKioskClaim,recoverKioskClaim,kioskClaimInfo,kioskIdentity,forgetKioskConnection,takeKioskLink,getKioskTokenFor } from '@/utils/kiosk-session'
import { KioskError } from '@/utils/kiosk-api'
import { getCompiledUiCatalog } from '@/utils/compiled-ui'
import { reloadCompiledUiRoutes } from '@/router'
const label=useKioskLabels(),router=useRouter(),draft=takeKioskLink()
const module=ref(draft?.module||''),code=ref(draft?.code||''),busy=ref(false),message=ref(''),reviewed=ref(false)
const pending=ref<ReturnType<typeof kioskClaimInfo>>(null),identity=ref<ReturnType<typeof kioskIdentity>>(null)
function sync(){try{pending.value=kioskClaimInfo();identity.value=kioskIdentity();if(pending.value)module.value=pending.value.module;else if(identity.value)module.value=identity.value.module}catch{message.value=label('storage')}}
sync()
async function open(){
  const current=kioskIdentity();if(!current)throw new KioskError('denied')
  await getKioskTokenFor(current.module,true)
  const binding=kioskIdentity()!,catalog=await getCompiledUiCatalog(true)
  const pkg=catalog.find(p=>p.module_id===binding.module&&p.source_sha256===binding.artifact&&(p.built_ui_sha256??null)===binding.build)
  const destination=pkg?.entrypoints.find(e=>e.kind==='route'&&e.application_audience==='kiosk'&&typeof e.route==='string'&&/^\/(?!\/)[^?#\\\s]*$/.test(e.route))?.route
  if(!destination)throw new KioskError('unavailable')
  await reloadCompiledUiRoutes(router,catalog)
  await router.replace(destination)
}
async function submit(recover=false){
  if(busy.value)return
  busy.value=true;message.value=''
  try{if(!identity.value){if(recover)await recoverKioskClaim();else await beginKioskClaim(module.value.trim(),code.value.trim());code.value='';sync()}await open()}
  catch(error){sync();message.value=label(error instanceof KioskError?error.code:'unavailable')}
  finally{busy.value=false}
}
function forget(){if(!reviewed.value)return;try{forgetKioskConnection();code.value='';reviewed.value=false;message.value='';sync()}catch{message.value=label('storage')}}
</script>
<template>
  <UiSurface class="kiosk-connect">
    <h1>{{ label('title') }}</h1><p class="ui-help">{{ label('help') }}</p>
    <p v-if="message" role="alert" class="error-message">{{ message }}</p>
    <form v-if="!identity && !pending" @submit.prevent="submit()" class="kiosk-form">
      <label>{{ label('module') }}<input v-model="module" class="ui-control" required :disabled="busy" autocomplete="off" autocapitalize="none" spellcheck="false"></label>
      <label>{{ label('code') }}<input v-model="code" class="ui-control" required :disabled="busy" autocomplete="off" autocapitalize="none" spellcheck="false" type="password"></label>
      <UiButton type="submit" variant="primary" :loading="busy">{{ busy?label('working'):label('connect') }}</UiButton>
    </form>
    <template v-else>
      <p>{{ label('module') }}: <strong>{{ module }}</strong></p>
      <template v-if="pending"><p role="status">{{ label('uncertain') }}</p><p>{{ label('request') }}: <code>{{ pending.request_id }}</code></p></template>
      <UiButton :loading="busy" variant="primary" @click="submit(Boolean(pending))">{{ pending?label('recover'):label('open') }}</UiButton>
    </template>
    <div v-if="pending || identity || message" class="kiosk-reset">
      <p class="ui-help">{{ label('forgetHelp') }}</p>
      <label><input v-model="reviewed" type="checkbox" :disabled="busy"> {{ label('review') }}</label>
      <UiButton :disabled="!reviewed || busy" @click="forget">{{ label('forget') }}</UiButton>
    </div>
  </UiSurface>
</template>
<style scoped>
.kiosk-connect{width:min(100%,38rem);margin:clamp(1rem,5vw,3rem) auto;padding:clamp(1rem,4vw,2rem);overflow-wrap:anywhere}
.kiosk-form,.kiosk-form label,.kiosk-reset{display:grid;gap:var(--ui-space-3,1rem)}
.kiosk-reset{margin-top:var(--ui-space-5,2rem);border-top:1px solid var(--ui-border);padding-top:var(--ui-space-4,1.5rem)}
</style>
