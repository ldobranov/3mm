import { afterEach,beforeEach,expect,it,vi } from 'vitest'
import { mount,flushPromises } from '@vue/test-utils'
import { applicationHostKey } from '@3mm/application-ui/v1'
import CrudPage from '../frontend/CrudPage.vue'
const definition={name:{en:'Contacts',translations:{bg:'Контакти'}},entities:[{entity_id:'contact',label:{en:'Contact'},fields:[{field_id:'name',label:{en:'Name'},kind:'text',required:true}]}]}
const key='3mm.crud.pending:org.example.contacts:'+'a'.repeat(64)+':contact'
const mounted:ReturnType<typeof mount>[]=[]
beforeEach(()=>localStorage.clear())
afterEach(()=>{mounted.splice(0).forEach(w=>w.unmount());vi.restoreAllMocks();vi.unstubAllGlobals()})
function setup(fn?:any,actions=['list','create','update','delete','outcome']){
  const invoke=vi.fn(fn||(()=>({items:[],next:null})))
  const host={getInfo:vi.fn().mockResolvedValue({module_id:'org.example.contacts',artifact_sha256:'a'.repeat(64),operations:actions.map(a=>({operation_id:'contact_'+a}))}),invoke}
  const wrapper=mount(CrudPage,{props:{definition,entityId:'contact'},global:{provide:{[applicationHostKey as symbol]:host}}});mounted.push(wrapper);return {wrapper,host}
}
const button=(wrapper:ReturnType<typeof mount>,text:string)=>wrapper.findAll('button').find(b=>b.text()===text)!
it('uses fresh permitted operations and translated labels without Core HTTP',async()=>{
  const {wrapper,host}=setup(undefined,['list']);await flushPromises();await wrapper.setProps({language:'bg'})
  expect(wrapper.text()).toContain('Контакти');expect(wrapper.find('form').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('New Contact');expect(host.invoke).toHaveBeenCalledWith('contact_list',{after:''})
})
it('persists only a random ID before a single command and keeps it until review',async()=>{
  const {wrapper,host}=setup((name:string,payload:any,options:any)=>{
    if(name==='contact_list')return {items:[],next:null}
    expect(localStorage.getItem(key)).toBe(options.idempotencyKey)
    expect(localStorage.getItem(key)).not.toContain('Private name')
    expect(payload.data.name).toBe('Private name');return {status:'stored',record:null}
  });await flushPromises();await button(wrapper,'New Contact').trigger('click')
  await wrapper.get('form input').setValue('Private name');await wrapper.get('form').trigger('submit');await flushPromises()
  expect(host.invoke.mock.calls.filter(c=>c[0]==='contact_create')).toHaveLength(1)
  expect(wrapper.text()).toContain('Record saved.')
  expect(wrapper.text()).not.toContain('stored')
  expect(button(wrapper,'New Contact').attributes('disabled')).toBeDefined()
  await button(wrapper,'Refresh').trigger('click');await flushPromises()
  expect(host.invoke.mock.calls.filter(c=>c[0]==='contact_create')).toHaveLength(1)
})
it('survives reload and checks an ambiguous outcome without replay',async()=>{
  localStorage.setItem(key,'b'.repeat(32))
  const {wrapper,host}=setup((name:string)=>name==='contact_outcome'?{status:'not_found',record:null}:{items:[],next:null});await flushPromises()
  await button(wrapper,'Check outcome').trigger('click');await flushPromises()
  expect(host.invoke.mock.calls.every(c=>['contact_list','contact_outcome'].includes(c[0]))).toBe(true)
  expect(button(wrapper,'Clear reviewed request').attributes('disabled')).toBeDefined()
  await wrapper.get('input[type=checkbox]').setValue(true);await button(wrapper,'Clear reviewed request').trigger('click')
  expect(localStorage.getItem(key)).toBeNull()
})
it('keeps failed writes locked and refuses a command if its ID cannot be saved',async()=>{
  const {wrapper,host}=setup((name:string)=>{if(name==='contact_create')throw new Error('lost');return {items:[],next:null}});await flushPromises()
  vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('denied')})
  await button(wrapper,'New Contact').trigger('click');await wrapper.get('form input').setValue('Name');await wrapper.get('form').trigger('submit');await flushPromises()
  expect(host.invoke.mock.calls.map(c=>c[0])).toEqual(['contact_list'])
  expect(wrapper.text()).toContain('Changes are blocked')
})
it('clears visible personal data when fresh access is revoked',async()=>{
  const {wrapper,host}=setup(()=>({items:[{record_id:'c'.repeat(32),data:{name:'Private name'},revision:1}],next:null}));await flushPromises()
  expect(wrapper.text()).toContain('Private name');host.getInfo.mockRejectedValue(new Error('revoked'))
  await button(wrapper,'Refresh').trigger('click');await flushPromises()
  expect(wrapper.text()).not.toContain('Private name');expect(wrapper.text()).toContain('Access or storage is unavailable')
})

it('submits on HTTP LAN without randomUUID and preserves the exact pending ID',async()=>{
  const rng=crypto.getRandomValues.bind(crypto)
  vi.stubGlobal('crypto',{getRandomValues:rng})
  const {wrapper,host}=setup((name:string)=>name==='contact_create'?{status:'stored',record:null}:{items:[],next:null})
  await flushPromises();await button(wrapper,'New Contact').trigger('click')
  await wrapper.get('form input').setValue('HTTP draft');await wrapper.get('form').trigger('submit');await flushPromises()
  const calls=host.invoke.mock.calls.filter(c=>c[0]==='contact_create')
  expect(calls).toHaveLength(1)
  expect(calls[0]![2].idempotencyKey).toMatch(/^[0-9a-f]{32}$/)
  expect(localStorage.getItem(key)).toBe(calls[0]![2].idempotencyKey)
})

it('refuses a mutation visibly when secure request identity cannot be obtained',async()=>{
  vi.stubGlobal('crypto',{getRandomValues:()=>{throw new Error('unavailable')}})
  const {wrapper,host}=setup();await flushPromises();await button(wrapper,'New Contact').trigger('click')
  await wrapper.get('form input').setValue('Draft');await wrapper.get('form').trigger('submit');await flushPromises()
  expect(host.invoke.mock.calls.map(c=>c[0])).toEqual(['contact_list'])
  expect(wrapper.get('[role=alert]').text()).toContain('Changes are blocked')
  expect(localStorage.getItem(key)).toBeNull()
})

it('uses the controlled table pagination without fetching or repeating mutations on render',async()=>{
  const {wrapper,host}=setup((name:string,payload:any)=>({items:[{record_id:payload.after?'b':'a',data:{name:payload.after?'Second':'First'},revision:1}],next:payload.after?null:'cursor-a'}),['list'])
  await flushPromises();expect(wrapper.get('caption').text()).toBe('Contact')
  expect(host.invoke).toHaveBeenCalledTimes(1)
  await button(wrapper,'Next page').trigger('click');await flushPromises()
  expect(host.invoke.mock.calls.map(c=>c[1])).toEqual([{after:''},{after:'cursor-a'}])
  expect(wrapper.get('tbody').text()).toContain('Second');expect(wrapper.get('tbody').text()).not.toContain('First')
  await wrapper.setProps({language:'bg'});await flushPromises()
  expect(host.invoke).toHaveBeenCalledTimes(2)
  expect(wrapper.get('nav').attributes('aria-label')).toBe('Страници')
})
