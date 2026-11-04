import { flushPromises,mount } from '@vue/test-utils'
import { afterEach,beforeEach,describe,expect,it,vi } from 'vitest'
const http=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}))
vi.mock('@/utils/dynamic-http',()=>({default:http}))
vi.mock('@/utils/i18n',()=>({useI18n:()=>({t:(_k:string,f:string)=>f})}))
import RemoteAgentUpdates from './RemoteAgentUpdates.vue'
const DEVICE='dev_'+'a'.repeat(32),OP='nodeupd_'+'b'.repeat(32),SHA='c'.repeat(64)
function state(){return {device_id:DEVICE,operation_id:OP,release_id:'v0.3.6',archive_sha256:SHA,archive_size_bytes:1024,
  state:'prepared',apply_command_id:null as string|null,apply_command_status:null as string|null,installation:null as null|Record<string,unknown>}}
const methods=['showModal','close'].map(name=>({name,descriptor:Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype,name)}))
function button(w:ReturnType<typeof mount>,label:string){return w.findAll('button').find(b=>b.text()===label)!}
describe('per-Node signed OTA controls',()=>{
  let data:ReturnType<typeof state>
  beforeEach(()=>{
    vi.clearAllMocks();vi.useFakeTimers();sessionStorage.clear();data=state()
    http.get.mockImplementation(async(path:string)=>({data:path.endsWith('/nodes')?{nodes:[{device_id:DEVICE,label:'Test Node',current_release_id:'v0.3.5',latest_operation_id:OP}]}:
      path.includes('/check?')?{current_release_id:'v0.3.5',latest_release_id:'v0.3.6',latest_version:'0.3.6',update_available:true}:structuredClone(data)}))
    http.post.mockImplementation(async(path:string)=>({data:path.endsWith('/prepare')?{prepared:{device_id:DEVICE,operation_id:OP}}:{operation_id:OP}}))
    for(const name of ['showModal','close'])Object.defineProperty(HTMLDialogElement.prototype,name,{configurable:true,value:function(this:HTMLDialogElement){this.open=name==='showModal'}})
  })
  afterEach(()=>{
    vi.clearAllTimers();vi.useRealTimers();vi.restoreAllMocks()
    for(const{name,descriptor}of methods){if(descriptor)Object.defineProperty(HTMLDialogElement.prototype,name,descriptor);else Reflect.deleteProperty(HTMLDialogElement.prototype,name)}
  })
  it('does not contact a release catalog, prepare, install or poll on page load',async()=>{
    const w=mount(RemoteAgentUpdates);await flushPromises();await vi.advanceTimersByTimeAsync(15000)
    expect(http.get).toHaveBeenCalledTimes(2);expect(http.get.mock.calls.some(c=>c[0].includes('/check'))).toBe(false)
    expect(http.post).not.toHaveBeenCalled();w.unmount()
  })
  it('checks and prepares only the selected Node after explicit actions',async()=>{
    const w=mount(RemoteAgentUpdates);await flushPromises()
    await button(w,'Check published package').trigger('click');await flushPromises()
    expect(http.get.mock.calls.at(-1)![0]).toBe('/api/v1/devices/'+DEVICE+'/node-updates/check?channel=stable')
    await button(w,'Download and prepare on this Node').trigger('click');await flushPromises()
    expect(http.post.mock.calls).toEqual([['/api/v1/devices/'+DEVICE+'/node-updates/prepare',{channel:'stable'}]])
    expect(w.text()).toContain(SHA);w.unmount()
  })
  it('requires exact device/release/hash review and separate maintenance acknowledgement',async()=>{
    const w=mount(RemoteAgentUpdates,{props:{maintenanceOverrideRequired:true}});await flushPromises()
    await button(w,'Review this Node update').trigger('click');await flushPromises()
    expect(w.find('dialog').text()).toContain(DEVICE);expect(w.find('dialog').text()).toContain(SHA)
    const checks=w.findAll('dialog input');await checks[0]!.setValue(true)
    expect(button(w,'Confirm once').attributes('disabled')).toBeDefined()
    await checks[1]!.setValue(true);await button(w,'Confirm once').trigger('click');await flushPromises()
    expect(http.post.mock.calls).toEqual([['/api/v1/devices/'+DEVICE+'/node-updates/'+OP+'/apply',{confirmed_install:true,maintenance_override:true}]])
    w.unmount()
  })
  it('never treats an accepted apply command as successful installation or retries it',async()=>{
    data.apply_command_id='cmd_'+'d'.repeat(32);data.apply_command_status='succeeded'
    const w=mount(RemoteAgentUpdates);await flushPromises()
    expect(w.text()).toContain('a queued command is not installed software')
    expect(button(w,'Review this Node update').attributes('disabled')).toBeDefined()
    await vi.advanceTimersByTimeAsync(200000);const count=http.get.mock.calls.length
    await vi.advanceTimersByTimeAsync(10000);expect(http.get).toHaveBeenCalledTimes(count);expect(http.post).not.toHaveBeenCalled();w.unmount()
  })
  it('retains the original apply identity across a lost reply and remount',async()=>{
    http.post.mockRejectedValue(new Error('lost'))
    let w=mount(RemoteAgentUpdates);await flushPromises();await button(w,'Review this Node update').trigger('click');await flushPromises()
    await w.find('dialog input').setValue(true);await button(w,'Confirm once').trigger('click');await flushPromises();w.unmount()
    data.apply_command_id='cmd_'+'d'.repeat(32);data.apply_command_status='delivered'
    w=mount(RemoteAgentUpdates);await flushPromises();expect(w.text()).toContain(OP)
    expect(button(w,'Review this Node update').attributes('disabled')).toBeDefined();expect(http.post).toHaveBeenCalledOnce();w.unmount()
  })
  it('invalidates acknowledged approval when preparation expires',async()=>{
    const w=mount(RemoteAgentUpdates);await flushPromises();await button(w,'Review this Node update').trigger('click');await flushPromises()
    await w.find('dialog input').setValue(true);data.state='expired'
    await button(w,'Refresh status').trigger('click');await flushPromises()
    expect((w.find('dialog input').element as HTMLInputElement).checked).toBe(false)
    expect(button(w,'Confirm once').attributes('disabled')).toBeDefined();expect(http.post).not.toHaveBeenCalled();w.unmount()
  })
  it('shows verified rollback without reporting the candidate as installed',async()=>{
    data.apply_command_id='cmd_'+'d'.repeat(32)
    data.installation={device_id:DEVICE,operation_id:OP,release_id:'v0.3.6',archive_sha256:SHA,status:'rolled_back',previous_release_id:'v0.3.5',error_code:'installer_failed'}
    const w=mount(RemoteAgentUpdates);await flushPromises();expect(w.text()).toContain('rolled_back');expect(w.text()).toContain('v0.3.5')
    expect(button(w,'Review this Node update').attributes('disabled')).toBeDefined();w.unmount()
  })
  it('refuses a status receipt for another device',async()=>{
    data.device_id='dev_'+'f'.repeat(32)
    const w=mount(RemoteAgentUpdates);await flushPromises();expect(w.text()).toContain('Node status is unavailable')
    expect(http.post).not.toHaveBeenCalled();w.unmount()
  })
})
