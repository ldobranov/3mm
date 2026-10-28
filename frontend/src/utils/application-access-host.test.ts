import { describe, expect, it, vi } from 'vitest'
import { createApplicationAccess, readActorAccess, readDelegation } from './application-access-host'
import { ApplicationHostError, type ApplicationPayload } from '../extension-ui/application-v1'

const binding = { moduleId:'org.example.neutral', artifact:'a'.repeat(64), entrypoint:'operations', audience:'operator', build:'b'.repeat(64) }
const subject = 'usr_'+'7'.repeat(32)
const executor = { kind:'application', module_id:binding.moduleId, instance_id:'c'.repeat(24), artifact_sha256:binding.artifact }
const access = () => ({ access_version:1, entrypoint_id:binding.entrypoint, audience:binding.audience, built_ui_sha256:binding.build,
  actor:{ kind:'user', user_id:7, subject_id:subject, terminal_id:null, platform_administrator:false }, executor:{...executor},
  permission_ids:['records_read'], allowed_operation_ids:['read'], delegated_operation_ids:['read'], service_authority:'separate', admission_required:true })
const receipt = () => ({ delegation_version:1, delegation_id:'d'.repeat(32), operation_id:'read', module_id:binding.moduleId,
  status:'pending', initiator:{kind:'user',user_id:7,subject_id:subject}, executor:{...executor},
  expires_at:'2026-10-27T15:00:00Z', result:null, error_code:null, automatic_retry:false })
const copy = (p: ApplicationPayload) => structuredClone(p)
function setup() {
  const request=vi.fn(async (_path:string, data?:unknown):Promise<unknown> => data===undefined ? access() : receipt())
  const live=vi.fn()
  return { ...createApplicationAccess({...binding,request,live,copyPayload:copy}), request, live }
}

describe('current actor access and finite delegation',()=>{
  it('keeps human business rights separate from platform administration and service authority',()=>{
    const value=access(); value.actor.platform_administrator=true
    const parsed=readActorAccess(value,binding)
    expect(parsed.actor.subject_id).toBe(subject)
    expect(parsed.permission_ids).toEqual(['records_read'])
    expect(Object.isFrozen(parsed.actor)).toBe(true)
    expect(Object.isFrozen(parsed.permission_ids)).toBe(true)
    expect(parsed.service_authority).toBe('separate')
  })
  it.each(['public','kiosk'] as const)('does not invent a human on %s',audience=>{
    const value={...access(),audience,permission_ids:[],allowed_operation_ids:[],delegated_operation_ids:[],
      actor:{kind:audience==='public'?'anonymous':'kiosk',user_id:null,subject_id:null,
        terminal_id:audience==='kiosk'?'e'.repeat(32):null,platform_administrator:false}}
    expect(readActorAccess(value,{...binding,audience}).actor.subject_id).toBeNull()
    expect(()=>readActorAccess({...value,permission_ids:['read']},{...binding,audience})).toThrow()
    expect(()=>readActorAccess({...value,actor:{...value.actor,subject_id:subject}},{...binding,audience})).toThrow()
  })
  it.each(['actor','executor','route','build','grant','unknown','boolean'])('fails closed on malformed or foreign %s',fault=>{
    const value=access()
    if(fault==='actor') value.actor.subject_id='wrong'
    if(fault==='executor') value.executor.module_id='org.example.foreign'
    if(fault==='route') value.entrypoint_id='foreign'
    if(fault==='build') value.built_ui_sha256='e'.repeat(64)
    if(fault==='grant') value.delegated_operation_ids=['write']
    if(fault==='unknown') Object.assign(value,{token:'must-not-escape'})
    if(fault==='boolean') Object.assign(value,{access_version:true})
    expect(()=>readActorAccess(value,binding)).toThrow(ApplicationHostError)
  })
  it('creates once with copied input, fixed route binding and no selected identity',async()=>{
    const s=setup(); const input={n:7}
    const promise=s.delegations.create('read',input,'d'.repeat(32),60); input.n=8
    expect((await promise).status).toBe('pending')
    expect(s.request).toHaveBeenCalledTimes(2)
    expect(s.request.mock.calls[1]).toEqual(['/ui-host/operations/delegations',{
      request_id:'d'.repeat(32),operation_id:'read',payload:{n:7},ttl_seconds:60,
      ui_context:{host_version:1,entrypoint_id:binding.entrypoint,artifact_sha256:binding.artifact,built_ui_sha256:binding.build}}])
  })
  it.each(['lost','malformed','identity'])('never repeats a mutation after %s response',async fault=>{
    const s=setup()
    s.request.mockImplementation(async (_path,data)=>{
      if(data===undefined)return access()
      if(fault==='lost')throw new ApplicationHostError('unavailable')
      const r=receipt()
      if(fault==='malformed')Object.assign(r,{token:'invalid'})
      else r.initiator.subject_id='usr_'+'8'.repeat(32)
      return r
    })
    await expect(s.delegations.create('read',{},'d'.repeat(32))).rejects.toMatchObject({code:'unconfirmed'})
    expect(s.request).toHaveBeenCalledTimes(2)
  })
  it('requires a fresh permitted operator route before creating',async()=>{
    const s=setup(); s.request.mockResolvedValue({...access(),delegated_operation_ids:[]})
    await expect(s.delegations.create('read',{},'d'.repeat(32))).rejects.toMatchObject({code:'access_denied'})
    expect(s.request).toHaveBeenCalledTimes(1)
  })
  it.each([4,301,5.5,NaN])('rejects invalid lifetime %s before any request',async ttl=>{
    const s=setup()
    await expect(s.delegations.create('read',{},'d'.repeat(32),ttl)).rejects.toMatchObject({code:'invalid_request'})
    expect(s.request).not.toHaveBeenCalled()
  })
  it('bounds payload and request identifiers before any network call',async()=>{
    const s=setup()
    await expect(s.delegations.create('read',{text:'x'.repeat(16384)},'d'.repeat(32))).rejects.toMatchObject({code:'invalid_request'})
    await expect(s.delegations.create('read',{},'../foreign')).rejects.toMatchObject({code:'invalid_request'})
    expect(s.request).not.toHaveBeenCalled()
  })
  it.each([{text:'я'.repeat(3000)},{text:'\ud800'},{value:Number.MAX_SAFE_INTEGER+1}] as ApplicationPayload[])('keeps input within the sealed JSON profile',async payload=>{
    const s=setup()
    await expect(s.delegations.create('read',payload,'d'.repeat(32))).rejects.toMatchObject({code:'invalid_request'})
    expect(s.request).not.toHaveBeenCalled()
  })
  it('looks up manually without dispatch and cancels only once',async()=>{
    const s=setup()
    s.request.mockImplementation(async path=>path.includes('/access?')?access():receipt())
    expect((await s.delegations.lookup('d'.repeat(32))).status).toBe('pending')
    expect(s.request.mock.calls[1]).toEqual(['/delegations/'+'d'.repeat(32),undefined])
    await s.delegations.cancel('d'.repeat(32))
    expect(s.request.mock.calls[3]).toEqual(['/delegations/'+'d'.repeat(32)+'/cancel',{}])
  })
  it.each(['retry','result','executor','subject','extra'])('does not expose a false receipt: %s',fault=>{
    const r=receipt()
    if(fault==='retry') r.automatic_retry=true
    if(fault==='result') Object.assign(r,{result:{}})
    if(fault==='executor') r.executor.artifact_sha256='e'.repeat(64)
    if(fault==='subject') r.initiator.subject_id='foreign'
    if(fault==='extra') Object.assign(r,{credentials:'forbidden'})
    expect(()=>readDelegation(r,binding,'d'.repeat(32),copy)).toThrow(ApplicationHostError)
  })
  it('refuses all requests after host disposal',async()=>{
    const s=setup(); s.live.mockImplementation(()=>{throw new ApplicationHostError('disposed')})
    await expect(s.access.getInfo()).rejects.toMatchObject({code:'disposed'})
    await expect(s.delegations.create('read',{},'d'.repeat(32))).rejects.toMatchObject({code:'disposed'})
    expect(s.request).not.toHaveBeenCalled()
  })
})
