import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_key: string, fallback: string) => fallback }) }))
import IndependentComponentUpdates from './IndependentComponentUpdates.vue'
const HOST = 'c'.repeat(24), OLD = 'a'.repeat(64), NEW = 'b'.repeat(64), ID = 'c'.repeat(32)
const targets = [{ component: 'agent', target_id: 'local', label: 'Local Agent' },
  { component: 'application_host', target_id: HOST, label: 'Selected application' }]
function response() {
  return { component: 'agent', target_id: 'local', current_build_id: OLD, previous_build_id: 'd'.repeat(64),
    ready: true, recovery_required: false, operation: null as null | Record<string, unknown>,
    candidate: { candidate_id: ID, build_id: NEW, sha256: 'e'.repeat(64), bytes: 1024, compatible: true } }
}
function button(w: ReturnType<typeof mount>, label: string) { return w.findAll('button').find(b => b.text() === label)! }
const methods = ['showModal','close'].map(name => ({ name, descriptor: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype,name) }))
describe('explicit independent component controls', () => {
  let data: ReturnType<typeof response>
  beforeEach(() => {
    vi.clearAllMocks(); vi.useFakeTimers(); sessionStorage.clear(); data = response()
    http.get.mockImplementation(async (path: string) => ({ data: path.endsWith('/targets') ? { targets } : structuredClone(data) }))
    http.post.mockImplementation(async (_path: string, payload: { request_id: string }) => ({ data: { request_id: payload.request_id } }))
    for (const name of ['showModal','close']) Object.defineProperty(HTMLDialogElement.prototype,name,
      { configurable: true, value: function(this: HTMLDialogElement) { this.open = name === 'showModal' } })
  })
  afterEach(() => {
    vi.clearAllTimers(); vi.useRealTimers(); vi.restoreAllMocks()
    for (const { name,descriptor } of methods) {
      if (descriptor) Object.defineProperty(HTMLDialogElement.prototype,name,descriptor)
      else Reflect.deleteProperty(HTMLDialogElement.prototype,name)
    }
  })
  it('reads only the selected target and never polls healthy idle targets', async () => {
    const w = mount(IndependentComponentUpdates); await flushPromises()
    expect(http.get.mock.calls.map(c => c[0])).toEqual(['/api/v1/system-updates/components/targets','/api/v1/system-updates/components/agent/local'])
    await vi.advanceTimersByTimeAsync(18000)
    expect(http.get).toHaveBeenCalledTimes(2); expect(http.post).not.toHaveBeenCalled(); w.unmount()
  })
  it('requires separate exact-build approval and maintenance acknowledgement', async () => {
    const w = mount(IndependentComponentUpdates,{ props: { maintenanceOverrideRequired: true } }); await flushPromises()
    await button(w,'Review update').trigger('click'); await flushPromises()
    expect(w.find('dialog').text()).toContain(NEW)
    expect(button(w,'Confirm once').attributes('disabled')).toBeDefined()
    const checks = w.findAll('dialog input[type=checkbox]'); await checks[0]!.setValue(true)
    expect(button(w,'Confirm once').attributes('disabled')).toBeDefined()
    await checks[1]!.setValue(true); await button(w,'Confirm once').trigger('click'); await flushPromises()
    expect(http.post).toHaveBeenCalledOnce()
    expect(http.post.mock.calls[0]).toEqual(['/api/v1/system-updates/components/agent/local/apply',expect.objectContaining({
      build_id: NEW, candidate_id: ID, confirmation: 'APPLY agent local '+NEW, maintenance_override: true })]); w.unmount()
  })
  it('prepares once on LAN HTTP and never applies automatically', async () => {
    const randomUUID = vi.spyOn(crypto,'randomUUID').mockImplementation(() => { throw new Error('LAN') })
    const w = mount(IndependentComponentUpdates); await flushPromises()
    await button(w,'Prepare from installed Core').trigger('click'); await flushPromises()
    expect(http.post.mock.calls[0]![0]).toBe('/api/v1/system-updates/components/agent/local/prepare')
    expect(http.post.mock.calls[0]![1].request_id).toMatch(/^[a-f0-9]{32}$/)
    expect(randomUUID).not.toHaveBeenCalled(); expect(http.post).toHaveBeenCalledOnce(); w.unmount()
  })
  it('selects a single application instance without fan-out or default-host publication', async () => {
    const w = mount(IndependentComponentUpdates); await flushPromises()
    data.component = 'application_host'; data.target_id = HOST
    await w.find('select').setValue('application_host/'+HOST); await flushPromises()
    expect(http.get.mock.calls.at(-1)![0]).toBe('/api/v1/system-updates/components/application_host/'+HOST)
    await button(w,'Review update').trigger('click'); await flushPromises()
    await w.find('dialog input').setValue(true); await button(w,'Confirm once').trigger('click'); await flushPromises()
    expect(http.post.mock.calls[0]![1].confirmation).toBe('APPLY application_host '+HOST+' '+NEW); w.unmount()
  })
  it('invalidates acknowledgement on candidate drift, including later recovery of eligibility', async () => {
    const w = mount(IndependentComponentUpdates); await flushPromises()
    await button(w,'Review update').trigger('click'); await flushPromises(); await w.find('dialog input').setValue(true)
    data.candidate.compatible = false
    await button(w,'Refresh status').trigger('click'); await flushPromises()
    expect((w.find('dialog input').element as HTMLInputElement).checked).toBe(false)
    data.candidate.compatible = true
    await button(w,'Refresh status').trigger('click'); await flushPromises()
    expect(button(w,'Confirm once').attributes('disabled')).toBeDefined(); expect(http.post).not.toHaveBeenCalled(); w.unmount()
  })
  it('requires a new review if reading the selected component fails before confirmation', async () => {
    const w = mount(IndependentComponentUpdates); await flushPromises()
    await button(w,'Review previous build').trigger('click'); await flushPromises()
    await w.find('dialog input').setValue(true)
    let fail!: (reason: Error) => void
    http.get.mockImplementationOnce(() => new Promise((_ok, reject) => { fail = reject }))
    await button(w,'Refresh status').trigger('click')
    expect(button(w,'Confirm once').attributes('disabled')).toBeDefined()
    fail(new Error('status unavailable')); await flushPromises()
    expect(w.findAll('.actions button')).toHaveLength(0)
    expect((w.find('dialog input').element as HTMLInputElement).checked).toBe(false)
    await button(w,'Refresh status').trigger('click'); await flushPromises()
    await w.find('dialog input').setValue(true)
    expect(button(w,'Confirm once').attributes('disabled')).toBeDefined()
    expect(http.post).not.toHaveBeenCalled(); w.unmount()
  })
  it('reviews the exact previous build rather than treating rollback as recovery', async () => {
    const w = mount(IndependentComponentUpdates); await flushPromises()
    await button(w,'Review previous build').trigger('click'); await flushPromises()
    await w.find('dialog input').setValue(true); await button(w,'Confirm once').trigger('click'); await flushPromises()
    expect(http.post.mock.calls[0]).toEqual(['/api/v1/system-updates/components/agent/local/rollback',expect.objectContaining({
      build_id:'d'.repeat(64),confirmation:'ROLLBACK agent local '+'d'.repeat(64) })]); w.unmount()
  })
  it('retains a lost request across remount and never retries or generates a replacement', async () => {
    http.post.mockRejectedValue(new Error('lost reply'))
    let w = mount(IndependentComponentUpdates); await flushPromises()
    await button(w,'Prepare from installed Core').trigger('click'); await flushPromises()
    const id = http.post.mock.calls[0]![1].request_id
    expect(w.text()).toContain(id); w.unmount()
    w = mount(IndependentComponentUpdates); await flushPromises()
    expect(w.text()).toContain(id); expect(button(w,'Prepare from installed Core').attributes('disabled')).toBeDefined()
    await vi.advanceTimersByTimeAsync(150000)
    const count = http.get.mock.calls.length; await vi.advanceTimersByTimeAsync(20000)
    expect(http.get).toHaveBeenCalledTimes(count); expect(http.post).toHaveBeenCalledOnce(); w.unmount()
  })
  it('releases only an explicitly refused request, without automatically retrying it',async()=>{
    http.post.mockImplementation(async (_url, body) => {throw {response:{status:409,data:{detail:{code:'component_update_not_accepted',request_id:body.request_id}}}}})
    const w=mount(IndependentComponentUpdates);await flushPromises()
    await button(w,'Prepare from installed Core').trigger('click');await flushPromises()
    expect(sessionStorage.getItem('3mm-component-update-pending')).toBeNull()
    expect(w.text()).toContain('Not accepted; no update was scheduled')
    expect(button(w,'Prepare from installed Core').attributes('disabled')).toBeUndefined()
    await vi.advanceTimersByTimeAsync(10000);expect(http.post).toHaveBeenCalledOnce();w.unmount()
  })
  it.each([[409, 'a different request'], [409, undefined], [503, 'same']])('keeps an uncorrelated refusal pending (%s, %s)', async (status, id) => {
    http.post.mockImplementation(async (_url, body) => {throw {response:{status,data:{detail:{code:'component_update_not_accepted',request_id:id==='same'?body.request_id:id}}}}})
    const w=mount(IndependentComponentUpdates);await flushPromises()
    await button(w,'Prepare from installed Core').trigger('click');await flushPromises()
    expect(w.text()).toContain('Outcome unconfirmed')
    const pending=JSON.parse(sessionStorage.getItem('3mm-component-update-pending')!)
    expect(pending.request_id).toBe(http.post.mock.calls[0]![1].request_id)
    expect(button(w,'Prepare from installed Core').attributes('disabled')).toBeDefined()
    expect(http.post).toHaveBeenCalledOnce();w.unmount()
  })
  it('reads the original accepted result to release the pending-request fence', async () => {
    sessionStorage.setItem('3mm-component-update-pending',JSON.stringify({ target:'agent/local', request_id:ID }))
    data.operation = { request_id: ID, component:'agent', target_id:'local', state:'succeeded', reason:'candidate_prepared' }
    const w = mount(IndependentComponentUpdates); await flushPromises()
    expect(button(w,'Prepare from installed Core').attributes('disabled')).toBeUndefined()
    expect(sessionStorage.getItem('3mm-component-update-pending')).toBeNull(); w.unmount()
  })
  it.each([true,false])('accepts a historical result only for the recorded target (matches=%s)', async match => {
    const key='3mm-component-update-pending'
    sessionStorage.setItem(key,JSON.stringify({target:'agent/local',request_id:ID}))
    data.operation={request_id:'e'.repeat(32),component:'agent',target_id:'local',state:'queued',reason:null}
    const receipt={request_id:ID,component:match?'agent':'application_host',target_id:match?'local':HOST,
      state:'succeeded',reason:'candidate_prepared'}
    http.get.mockImplementation(async (url:string) => ({data:url.endsWith('/targets')?{targets}:{...data,requested_receipt:receipt}}))
    const w=mount(IndependentComponentUpdates);await flushPromises()
    expect(http.get).toHaveBeenCalledWith('/api/v1/system-updates/components/agent/local',{params:{receipt_id:ID}})
    expect(w.text().includes('Result for your earlier request:')).toBe(match)
    expect(w.text().includes('Outcome unconfirmed')).toBe(!match)
    expect(sessionStorage.getItem(key)===null).toBe(match)
    expect(http.post).not.toHaveBeenCalled();w.unmount()
  })
  it('keeps the original ID when its target is absent and offers a read-only refresh', async () => {
    const saved=JSON.stringify({target:'application_host/'+HOST,request_id:ID})
    sessionStorage.setItem('3mm-component-update-pending',saved)
    http.get.mockResolvedValueOnce({data:{targets:[targets[0]]}})
    const w=mount(IndependentComponentUpdates);await flushPromises()
    expect(w.text()).toContain(ID);expect(w.text()).toContain('original target is not currently listed')
    expect(http.get).toHaveBeenCalledTimes(1)
    expect(w.findAll('button').some(b=>b.text()==='Prepare from installed Core')).toBe(false)
    http.get.mockResolvedValueOnce({data:{targets}}).mockResolvedValueOnce({data:{
      ...response(),component:'application_host',target_id:HOST,operation:{request_id:ID,component:'application_host',target_id:HOST,state:'succeeded',reason:'candidate_prepared'}
    }})
    await button(w,'Refresh status').trigger('click');await flushPromises()
    expect(http.get.mock.lastCall?.[0]).toBe('/api/v1/system-updates/components/application_host/'+HOST)
    expect(sessionStorage.getItem('3mm-component-update-pending')).toBeNull();expect(http.post).not.toHaveBeenCalled();w.unmount()
  })
  it('never submits when tab storage will not retain an ID', async () => {
    const w=mount(IndependentComponentUpdates);await flushPromises()
    vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('unavailable')})
    await button(w,'Prepare from installed Core').trigger('click');await flushPromises()
    expect(http.post).not.toHaveBeenCalled();expect(w.text()).toContain('No request was sent')
    expect(w.text()).not.toContain('Outcome unconfirmed');w.unmount()
  })
  it('requires explicit recovery for the original target and does not replay apply', async () => {
    data.recovery_required = true
    data.operation = { request_id: ID, component:'agent',target_id:'local',state:'recovery_required',reason:'worker_interrupted' }
    const w = mount(IndependentComponentUpdates); await flushPromises()
    expect(button(w,'Review update').attributes('disabled')).toBeDefined()
    await button(w,'Review interrupted-operation recovery').trigger('click'); await flushPromises()
    await w.find('dialog input').setValue(true); await button(w,'Confirm once').trigger('click'); await flushPromises()
    expect(http.post.mock.calls[0]![0]).toBe('/api/v1/system-updates/components/agent/local/recover')
    expect(http.post.mock.calls[0]![1]).not.toHaveProperty('build_id'); w.unmount()
  })
  it('does not offer a stale or already-current candidate', async () => {
    data.candidate.build_id = OLD
    const w = mount(IndependentComponentUpdates); await flushPromises()
    expect(w.text()).toContain('No update is needed'); expect(button(w,'Review update').attributes('disabled')).toBeDefined(); w.unmount()
  })
  it('keeps the card non-mutating when the helper is unavailable or returns the wrong target', async () => {
    data.target_id = HOST
    const w = mount(IndependentComponentUpdates); await flushPromises()
    expect(w.text()).toContain('Other administration remains available')
    expect(http.post).not.toHaveBeenCalled(); w.unmount()
  })
})
