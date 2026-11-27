import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const http=vi.hoisted(()=>({get:vi.fn(),post:vi.fn(),delete:vi.fn()}))
vi.mock('@/utils/dynamic-http',()=>({default:http}))
vi.mock('@/utils/i18n',()=>({useI18n:()=>({t:(_key:string,fallback:string)=>fallback})}))
import Workspace from './DiagnosticWorkspace.vue'
import Cases from './DiagnosticCases.vue'
const state=(active=false)=>({session_id:active?'a'.repeat(32):null,active,remaining_seconds:active?60:0,records:0,dropped:{full:0,rate:0,invalid:0,busy:0},scope:{profile:'diagnostic',operation:null,instance_id:null}})
let current=state(),wrappers:ReturnType<typeof mount>[]=[]
function mountView(advanced=true){const wrapper=mount(Workspace);wrappers.push(wrapper);if(advanced)void wrapper.get('button[aria-controls="diagnostic-tools"]').trigger('click');return wrapper}
it('opens with a single read, no automatic recording, raw identifiers or expert panels',async()=>{
  const wrapper=mountView(false);await flushPromises()
  expect(http.get).toHaveBeenCalledExactlyOnceWith('/api/v1/diagnostics/cases')
  expect(wrapper.text()).toContain('Recent problems')
  expect(wrapper.find('form').exists()).toBe(false)
  expect(wrapper.find('.case-filter').exists()).toBe(false)
  expect(http.post).not.toHaveBeenCalled()
})
it('opening tools shares the in-flight case observation; an explicit refresh takes a new one',async()=>{
  const existing=http.get.getMockImplementation()!
  let finish!: (report:unknown)=>void
  const reply=new Promise(resolve=>{finish=resolve})
  http.get.mockImplementation((url:string)=>url.endsWith('/cases')?reply:existing(url))
  const wrapper=mountView(false);await flushPromises()
  await wrapper.get('button[aria-controls="diagnostic-tools"]').trigger('click')
  const workspaceReads=()=>http.get.mock.calls.filter(([url])=>url.endsWith('/workspace')).length
  expect(workspaceReads()).toBe(0)
  const observed={schema_version:1,probe_status:'complete',components:[{component:'agent',version:'observed-first',
    build_id:null,health:'ready',reason:'live_probe'}],core_services:{components:{}},operations:[]}
  finish({data:{schema_version:1,generated_at:'2026-11-27T10:00:00Z',status:'ready',cases:[],coverage:[],
    failure_history:{},limitations:[],observations:observed}})
  await flushPromises()
  expect(wrapper.get('.component-card').text()).toContain('observed-first')
  expect(workspaceReads()).toBe(0)
  await wrapper.get('.workspace-heading button').trigger('click');await flushPromises()
  expect(workspaceReads()).toBe(1)
  expect(wrapper.get('.component-card').text()).not.toContain('observed-first')
  expect(http.post).not.toHaveBeenCalled()
})
it.each(['refused','left page'])('does not start another observation when the shared read is %s',async(reason)=>{
  const base=http.get.getMockImplementation()!
  let finish!: (v:unknown)=>void, fail!: (error:Error)=>void
  const pending=new Promise((resolve,reject)=>{finish=resolve;fail=reject})
  http.get.mockImplementation((url:string)=>url.endsWith('/cases')?pending:base(url))
  const view=mountView(false);await flushPromises()
  await view.get('button[aria-controls="diagnostic-tools"]').trigger('click')
  if(reason==='refused') fail(new Error('denied'))
  else { view.unmount(); finish({data:{}}) }
  await flushPromises()
  expect(http.get).not.toHaveBeenCalledWith('/api/v1/diagnostics/workspace')
  if(reason==='refused')expect(view.text()).toContain('Diagnostics are unavailable')
  expect(http.post).not.toHaveBeenCalled()
})
it('shows both validated builds only in technical tools, without treating a mismatch as a missing response',async()=>{
  const existing=http.get.getMockImplementation()!
  const selected='a'.repeat(64),running='b'.repeat(64)
  http.get.mockImplementation(async(url:string)=>url.endsWith('/workspace')?{data:{components:[
    {component:'agent',build_id:selected,loaded_build_id:running,health:'unknown',reason:'build_mismatch'}
  ],core_services:{components:{}},operations:[]}}:existing(url))
  const wrapper=mountView(false);await flushPromises()
  expect(wrapper.text()).not.toContain(selected.slice(0,12))
  await wrapper.get('button[aria-controls="diagnostic-tools"]').trigger('click');await flushPromises()
  const card=wrapper.get('.component-card')
  expect(card.text()).toContain('Different build')
  expect(card.text()).toContain('Selected build')
  expect(card.text()).toContain('Running build')
  expect(card.findAll('code').map(x=>[x.text(),x.attributes('title')])).toEqual([
    [selected.slice(0,12),selected],[running.slice(0,12),running]])
  expect(card.text()).not.toContain('No confirmed component response')
  expect(http.post).not.toHaveBeenCalled()
})
it.each([null,'c'.repeat(24)])('records the next case without widening an instance filter (%s)', async caseInstance => {
  const view=mountView();await flushPromises()
  await view.find('input[pattern]').setValue('b'.repeat(24))
  view.getComponent(Cases).vm.$emit('record','checkpoint.get',caseInstance)
  await flushPromises()
  expect(http.post).toHaveBeenCalledWith('/api/v1/diagnostics/session',{
    ttl_seconds:120,profile:'diagnostic',operation:'checkpoint.get',instance_id:caseInstance ?? 'b'.repeat(24)})
})
beforeEach(()=>{vi.clearAllMocks();current=state();http.get.mockImplementation(async(url:string)=>({data:url.endsWith('/workspace')?{components:[{component:'agent',build_id:'a'.repeat(64),health:'unknown',reason:'passive_metadata'}],operations:['checkpoint.get'],core_services:{components:{}}}:url.endsWith('/session')?current:url.endsWith('/failures')?{status:'ready',records:[],dropped:{}}:{records:[],missing_components:['runtime'],truncated:false}}));http.post.mockImplementation(async()=>{current=state(true);return{data:current}});http.delete.mockImplementation(async()=>{current=state();return{data:current}})})
afterEach(()=>{wrappers.forEach(w=>w.unmount());wrappers=[];vi.useRealTimers();vi.unstubAllGlobals()})
it('shows unknown health, missing producers and starts an explicitly scoped session',async()=>{const wrapper=mountView();await flushPromises();expect(wrapper.text()).toContain('Not observed');expect(wrapper.text()).toContain('No trace export from:');const selects=wrapper.findAll('select');await selects[0].setValue('development');await selects[2].setValue('checkpoint.get');await wrapper.find('input[pattern]').setValue('b'.repeat(24));await wrapper.find('form').trigger('submit');await flushPromises();expect(http.post).toHaveBeenCalledWith('/api/v1/diagnostics/session',{ttl_seconds:600,profile:'development',operation:'checkpoint.get',instance_id:'b'.repeat(24)});expect(wrapper.text()).toContain('Diagnostic session active');const stop=wrapper.findAll('button').find(b=>b.text()==='Stop now')!;await stop.trigger('click');await flushPromises();expect(http.delete).toHaveBeenCalledWith('/api/v1/diagnostics/session');expect(wrapper.text()).toContain('Normal mode')})
it('expires the display without restarting a diagnostic session',async()=>{vi.useFakeTimers();current=state(true);const wrapper=mountView();await flushPromises();await vi.advanceTimersByTimeAsync(61000);expect(wrapper.text()).toContain('Normal mode');expect(http.post).not.toHaveBeenCalled()})
it('retains a fixed error after a refused control request without echoing backend text',async()=>{http.post.mockRejectedValue({response:{data:{detail:'password=secret'}}});const wrapper=mountView();await flushPromises();await wrapper.find('form').trigger('submit');await flushPromises();expect(wrapper.get('#diagnostic-tools [role="alert"]').text()).toContain('Diagnostics are unavailable');expect(wrapper.text()).not.toContain('password=secret')})
it('bounds imports before reading and sending them',async()=>{const wrapper=mountView();await flushPromises();const input=wrapper.find('input[type=file]');Object.defineProperty(input.element,'files',{value:[{size:4*1024*1024+1,text:vi.fn()}]});await input.trigger('change');await flushPromises();expect(wrapper.text()).toContain('4 MiB import limit');expect(http.post).not.toHaveBeenCalled()})
it('ignores a late refresh after unmounting',async()=>{let resolve:(v:any)=>void=()=>{};http.get.mockImplementation(()=>new Promise(r=>{resolve=r}));const wrapper=mountView();wrapper.unmount();resolve({data:{records:[{reason:'late'}]}});await flushPromises();expect(http.post).not.toHaveBeenCalled()})

it('shows imported drop counters and saves the same bounded merged snapshot',async()=>{const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});const createObjectURL=vi.fn(()=> 'blob:merged');const revokeObjectURL=vi.fn();vi.stubGlobal('URL',{createObjectURL,revokeObjectURL});const wrapper=mountView();await flushPromises();http.post.mockResolvedValueOnce({data:{records:[],sessions:[{component:'sdk',source:'imported',records:4,dropped:{full:0,rate:2,invalid:0,busy:0}}],missing_components:['runtime'],truncated:false}});const input=wrapper.find('input[type=file]');Object.defineProperty(input.element,'files',{value:[{size:10,text:async()=> '{}'}]});await input.trigger('change');await flushPromises();expect(wrapper.text()).toContain('SDK · At export: 4 records · 2 dropped');await wrapper.findAll('button').find(b=>b.text()==='Save merged snapshot')!.trigger('click');expect(createObjectURL).toHaveBeenCalled();expect(click).toHaveBeenCalled();expect(revokeObjectURL).toHaveBeenCalledWith('blob:merged');click.mockRestore()})
