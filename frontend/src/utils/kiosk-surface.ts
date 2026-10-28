import { defineComponent,h,onMounted,onBeforeUnmount,ref,type Component } from 'vue'
import { kioskIdentity,kioskState,getKioskTokenFor } from './kiosk-session'
import { useKioskLabels } from './kiosk-labels'
import UiSurface from '../extension-ui/UiSurface.vue'
import UiButton from '../components/ui/UiButton.vue'
import type { CompiledUiPackage } from './compiled-ui'
import { useRouter } from 'vue-router'
export function withKioskSurface(pkg:CompiledUiPackage,component:Component){
  return defineComponent({inheritAttrs:false,props:{locale:String},setup(props,{attrs}){
    const allowed=ref(false),label=useKioskLabels(),router=useRouter();let disposed=false,timer:ReturnType<typeof setInterval>|undefined
    async function check(){try{await getKioskTokenFor(pkg.module_id,true);if(!disposed)allowed.value=true}catch{if(!disposed)allowed.value=false}}
    const visible=()=>{if(document.visibilityState!=='hidden')void check()}
    onMounted(()=>{void check();timer=setInterval(visible,30000);document.addEventListener('visibilitychange',visible);window.addEventListener('focus',visible)})
    onBeforeUnmount(()=>{disposed=true;clearInterval(timer);document.removeEventListener('visibilitychange',visible);window.removeEventListener('focus',visible)})
    return ()=>{
      const identity=kioskIdentity()
      const matches=identity?.module===pkg.module_id&&identity.artifact===pkg.source_sha256&&identity.build===(pkg.built_ui_sha256??null)
      if(allowed.value&&matches&&['ready','renewing'].includes(kioskState.value))return h(component,{...attrs,locale:props.locale})
      return h(UiSurface,{},()=>[h('p',{role:'status'},label(kioskState.value==='revoked'?'revoked':kioskState.value==='renewing'?'renewing':'offline')),
        h(UiButton,{onClick:()=>router.replace('/kiosk/connect')},()=>label('title'))])
    }
  }})
}
