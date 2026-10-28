import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import {mount,flushPromises} from '@vue/test-utils'
import {defineComponent,h,ref,nextTick} from 'vue'
import {withKioskSurface} from './kiosk-surface'
import type {CompiledUiPackage} from './compiled-ui'
import {kioskState} from './kiosk-session'
const api=vi.hoisted(()=>({renew:vi.fn(),identity:vi.fn(),replace:vi.fn()}))
vi.mock('./kiosk-session',async()=>({getKioskTokenFor:api.renew,kioskIdentity:api.identity,kioskState:(await import('vue')).ref('ready')}))
vi.mock('./i18n',()=>({useI18n:()=>({currentLanguage:language})}))
vi.mock('vue-router',()=>({useRouter:()=>({replace:api.replace})}))
const status=kioskState as import('vue').Ref<string>,language=ref('en'),pkg:CompiledUiPackage={module_id:'org.example.terminal',name:'Terminal',version:'1.0.0',source_sha256:'a'.repeat(64),built_ui_sha256:'b'.repeat(64),styles:[],entrypoints:[]}
let wrapper:ReturnType<typeof mount>|undefined
beforeEach(()=>{vi.useFakeTimers();vi.clearAllMocks();status.value='ready';language.value='en';api.renew.mockResolvedValue('token');api.identity.mockReturnValue({module:pkg.module_id,artifact:pkg.source_sha256,build:pkg.built_ui_sha256})})
afterEach(()=>{wrapper?.unmount();vi.useRealTimers()})
it('checks before mounting app code, preserves a form during locale and auth renewal, and removes it on revoke',async()=>{
  const destroyed=vi.fn(),rendered=vi.fn()
  const {onBeforeUnmount}=await import('vue')
  const child=defineComponent({props:{locale:String},setup(props){rendered();onBeforeUnmount(destroyed);return()=>h('div',[h('span',props.locale),h('input',{value:'draft'})])}})
  wrapper=mount(withKioskSurface(pkg,child),{props:{locale:'en'}})
  expect(rendered).not.toHaveBeenCalled();await flushPromises();expect(rendered).toHaveBeenCalledOnce()
  const input=wrapper.get('input').element
  await wrapper.setProps({locale:'bg-BG'});language.value='bg';await nextTick()
  expect(wrapper.get('span').text()).toBe('bg-BG');expect(wrapper.get('input').element).toBe(input)
  status.value='renewing';await nextTick();expect(wrapper.get('input').element).toBe(input)
  api.renew.mockImplementation(async()=>{status.value='revoked';throw Error('revoked')})
  window.dispatchEvent(new Event('focus'));await flushPromises()
  expect(wrapper.find('input').exists()).toBe(false);expect(destroyed).toHaveBeenCalledOnce()
  expect(wrapper.get('[role="status"]').text()).toBe('Отменен')
  await wrapper.get('button').trigger('click');expect(api.replace).toHaveBeenCalledWith('/kiosk/connect')
  wrapper.unmount();api.renew.mockClear();window.dispatchEvent(new Event('focus'));await vi.advanceTimersByTimeAsync(60000)
  expect(api.renew).not.toHaveBeenCalled()
})
it('never mounts another package build with an otherwise valid terminal',async()=>{
  api.identity.mockReturnValue({module:pkg.module_id,artifact:'f'.repeat(64),build:pkg.built_ui_sha256})
  const child=vi.fn(()=>h('div','Application'))
  wrapper=mount(withKioskSurface(pkg,defineComponent({render:child})));await flushPromises()
  expect(child).not.toHaveBeenCalled()
})
