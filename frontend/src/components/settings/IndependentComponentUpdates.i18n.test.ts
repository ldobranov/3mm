import { flushPromises,mount } from '@vue/test-utils'
import { afterEach,expect,it,vi } from 'vitest'
import bg from '../../../../modules/language-bg/language-extension.json'
vi.mock('@/utils/dynamic-http',()=>({default:{get:async(path:string)=>({data:path.endsWith('/nodes')?{nodes:[]}:
  path.endsWith('/targets')?{targets:[{component:'agent',target_id:'local',label:'Local Agent'}]}:
  {component:'agent',target_id:'local',current_build_id:'a'.repeat(64),previous_build_id:null,ready:true,recovery_required:false,candidate:null,operation:null}}),post:vi.fn()}}))
vi.mock('@/utils/language-api',async()=>{
  const pack=(await import('../../../../modules/language-bg/language-extension.json')).default
  return {readFrontendTranslations:async()=>pack.frontend,readAvailableLanguages:async()=>['en','bg'],saveCurrentUserLanguage:vi.fn()}
})
import { i18n } from '@/utils/i18n'
import Local from './IndependentComponentUpdates.vue'
import Remote from './RemoteAgentUpdates.vue'
afterEach(async()=>{await i18n.setLanguage('en',false)})
it('delivers local and remote component controls from the actual Bulgarian language source',async()=>{
  await i18n.setLanguage('bg',false)
  const local=mount(Local),remote=mount(Remote);await flushPromises()
  expect(local.text()).toContain(bg.frontend.componentUpdates.title)
  expect(local.text()).toContain(bg.frontend.componentUpdates.boundary)
  expect(local.find('select').text()).toContain(bg.frontend.componentUpdates.agent)
  expect(remote.text()).toContain(bg.frontend.remoteAgentUpdates.title)
  expect(remote.text()).toContain(bg.frontend.remoteAgentUpdates.empty)
  await i18n.setLanguage('en',false)
  expect(local.text()).toContain('Agent and application hosts')
  local.unmount();remote.unmount()
})
