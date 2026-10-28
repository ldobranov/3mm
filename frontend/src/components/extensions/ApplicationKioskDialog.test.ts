import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import {mount,flushPromises} from '@vue/test-utils'
import {ref,nextTick} from 'vue'
import Dialog from './ApplicationKioskDialog.vue'
import {KioskError} from '@/utils/kiosk-api'
const api=vi.hoisted(()=>({send:vi.fn()}))
vi.mock('@/utils/kiosk-api',async original=>({...await original<typeof import('@/utils/kiosk-api')>(),kioskRequest:api.send}))
vi.mock('@/utils/i18n',()=>({useI18n:()=>({currentLanguage:language})}))
const language=ref('en'),module='org.example.terminal',key='threeMmKioskEnrollmentV1:'+module
const mounted:ReturnType<typeof mount>[]=[]
const native=['showModal','close'].map(name=>({name,descriptor:Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype,name)}))
beforeEach(()=>{
  language.value='en';sessionStorage.clear();api.send.mockReset()
  for(const name of ['showModal','close'])Object.defineProperty(HTMLDialogElement.prototype,name,{configurable:true,value(){(this as HTMLDialogElement).open=name==='showModal'}})
  api.send.mockImplementation(async(_module,path,data)=>path==='terminals'?{items:[]}:{request_id:data.request_id,code:'x'.repeat(32),expires_at:'2099-01-01T00:00:00Z'})
})
afterEach(()=>{mounted.splice(0).forEach(w=>w.unmount());for(const {name,descriptor} of native){if(descriptor)Object.defineProperty(HTMLDialogElement.prototype,name,descriptor);else Reflect.deleteProperty(HTMLDialogElement.prototype,name)}})
async function render(active=true){const w=mount(Dialog,{props:{moduleId:module,name:'Example terminal',active}});mounted.push(w);await flushPromises();return w}
it('only reads on open and retains the entered name during live locale changes',async()=>{
  const w=await render();await w.get('input').setValue('Front desk');language.value='bg-BG';await nextTick()
  expect(w.text()).toContain('Kiosk терминали');expect((w.get('input').element as HTMLInputElement).value).toBe('Front desk')
  expect(api.send).toHaveBeenCalledExactlyOnceWith(module,'terminals',undefined,true)
})
it('recovers the same enrollment request on reopen without persisting its plaintext code',async()=>{
  api.send.mockImplementation(async(_module,path,data)=>{
    if(path==='terminals')return {items:[]}
    expect(JSON.parse(sessionStorage.getItem(key)!)).toEqual(data)
    throw new KioskError('unavailable')
  })
  const first=await render();await first.get('input').setValue('Front desk');await first.get('form').trigger('submit');await flushPromises()
  const original=api.send.mock.calls.find(c=>c[1]==='enrollments')![2]
  first.unmount();api.send.mockClear()
  const second=await render();expect(api.send.mock.calls.every(c=>c[1]==='terminals')).toBe(true)
  api.send.mockImplementation(async(_module,path,data)=>path==='terminals'?{items:[]}:{request_id:data.request_id,code:'x'.repeat(32),expires_at:'2099-01-01T00:00:00Z'})
  await second.get('form').trigger('submit');await flushPromises()
  expect(api.send.mock.calls.find(c=>c[1]==='enrollments')![2]).toEqual(original)
  expect(second.text()).toContain('x'.repeat(32));expect(sessionStorage.getItem(key)).not.toContain('x'.repeat(32))
})
it('lists and revokes on a stopped application while issuing is disabled',async()=>{
  const terminal='a'.repeat(32)
  api.send.mockResolvedValue({items:[{terminal_id:terminal,label:'Tablet',enabled:true,needs_pairing:false,last_seen_at:null}]})
  const w=await render(false)
  expect(w.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  await w.findAll('button').find(b=>b.text()==='Revoke')!.trigger('click');await flushPromises()
  expect(api.send).toHaveBeenCalledWith(module,'terminals/'+terminal,undefined,true,'DELETE')
  expect(api.send.mock.calls.some(c=>c[1]==='enrollments')).toBe(false)
})
