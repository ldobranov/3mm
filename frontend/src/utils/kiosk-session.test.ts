import { beforeEach,afterEach,describe,it,expect,vi,type MockInstance } from 'vitest'
import axios from 'axios'
import { getBackendUrl } from './runtime-config'
vi.mock('./runtime-config',()=>({getBackendUrl:vi.fn(async()=>'http://core.test')}))
const moduleId='org.example.kiosk',SESSION='threeMmKioskSessionV1',PENDING='threeMmKioskClaimV1'
let send:MockInstance<typeof axios.request>
function response(){return {module_id:moduleId,terminal_id:'a'.repeat(32),installation_incarnation:'b'.repeat(32),
  artifact_sha256:'c'.repeat(64),built_ui_sha256:'d'.repeat(64),access_token:token(),expires_in_seconds:900,
  credential:'e'.repeat(43)}}
function token(claims:Record<string,unknown>={}){return 'e30.'+btoa(JSON.stringify({token_type:'application_kiosk',sub:'kiosk:'+'a'.repeat(32),module_id:moduleId,terminal_id:'a'.repeat(32),incarnation:'b'.repeat(32),...claims})).replace(/=/g,'')+'.signature'}
async function controller(){return import('./kiosk-session')}
async function pair(){const c=await controller();await c.beginKioskClaim(moduleId,'x'.repeat(32));return c}
beforeEach(()=>{vi.resetModules();localStorage.clear();sessionStorage.clear();vi.mocked(getBackendUrl).mockResolvedValue('http://core.test');send=vi.spyOn(axios,'request').mockResolvedValue({data:response()})})
afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers()})
describe('Core kiosk identity controller',()=>{
  it('persists the original proof before sending and exposes only metadata',async()=>{
    send.mockImplementation(async config=>{
      const pending=JSON.parse(localStorage.getItem(PENDING)!)
      expect(config.data).toEqual({request_id:pending.request_id,recovery_proof:pending.recovery_proof,code:pending.code})
      expect(pending.backend).toBe('http://core.test')
      return {data:response()}
    })
    const c=await pair()
    expect(c.kioskState.value).toBe('ready');expect(send).toHaveBeenCalledTimes(1)
    expect(c.kioskIdentity()).toEqual({module:moduleId,terminal:'a'.repeat(32),artifact:'c'.repeat(64),build:'d'.repeat(64)})
    expect(localStorage.getItem(PENDING)).toBeNull()
    expect(Object.isFrozen(c.kioskIdentity())).toBe(true)
    expect(c.kioskRouteAvailable(moduleId)).toBe(true)
    expect(c.kioskRouteAvailable('org.example.foreign')).toBe(false)
  })
  it('recovers exactly the same claim after lost response and reload, without an automatic request',async()=>{
    send.mockRejectedValueOnce(new Error('lost response'))
    const first=await controller()
    await expect(first.beginKioskClaim(moduleId,'x'.repeat(32))).rejects.toMatchObject({code:'unavailable'})
    const original=send.mock.calls[0]![0].data as {request_id:string;recovery_proof:string;code:string}
    expect(localStorage.getItem(SESSION)).toBeNull()
    vi.resetModules();const reloaded=await controller()
    expect(send).toHaveBeenCalledTimes(1)
    expect(reloaded.kioskClaimInfo()?.request_id).toBe(original.request_id)
    await reloaded.recoverKioskClaim()
    expect(send.mock.calls[1]![0].data).toEqual(original)
    expect(send).toHaveBeenCalledTimes(2)
  })
  it('refuses another connection while an unresolved original request exists',async()=>{
    const c=await controller();send.mockRejectedValueOnce(new Error('lost'))
    await expect(c.beginKioskClaim(moduleId,'x'.repeat(32))).rejects.toThrow()
    await expect(c.beginKioskClaim(moduleId,'y'.repeat(32))).rejects.toMatchObject({code:'conflict'})
    expect(send).toHaveBeenCalledTimes(1)
  })
  it('renews once for parallel callers and sends no business operation',async()=>{
    const c=await pair();send.mockClear()
    const tokens=await Promise.all(Array.from({length:5},()=>c.getKioskTokenFor(moduleId,true)))
    expect(tokens).toEqual(Array(5).fill(response().access_token));expect(send).toHaveBeenCalledTimes(1)
    expect(send.mock.calls[0]![0].url).toBe('http://core.test/api/v1/application-extensions/'+moduleId+'/kiosk/sessions')
    expect(send.mock.calls[0]![0].data).toEqual({terminal_id:response().terminal_id,credential:response().credential})
  })
  it.each([401,403])('revocation %i clears only the kiosk identity',async status=>{
    localStorage.setItem('authToken','human-login');localStorage.setItem('role','admin')
    const c=await pair();send.mockRejectedValueOnce({isAxiosError:true,response:{status}})
    await expect(c.getKioskTokenFor(moduleId,true)).rejects.toMatchObject({code:'denied'})
    expect(c.kioskState.value).toBe('revoked');expect(c.kioskIdentity()).toBeNull()
    expect(c.kioskRouteAvailable(moduleId)).toBe(false)
    expect(localStorage.getItem('authToken')).toBe('human-login');expect(localStorage.getItem('role')).toBe('admin')
  })
  it('retains identity on network loss and only retries authentication when asked',async()=>{
    const c=await pair();send.mockRejectedValueOnce(new Error('offline'))
    await expect(c.getKioskTokenFor(moduleId,true)).rejects.toMatchObject({code:'unavailable'})
    expect(c.kioskState.value).toBe('offline');expect(c.kioskIdentity()?.module).toBe(moduleId)
    expect(send).toHaveBeenCalledTimes(2)
    await c.getKioskTokenFor(moduleId,true)
    expect(c.kioskState.value).toBe('ready');expect(send).toHaveBeenCalledTimes(3)
  })
  it('stops the mounted identity on revocation even if browser cleanup fails',async()=>{
    const c=await pair();send.mockRejectedValueOnce({isAxiosError:true,response:{status:401}})
    vi.spyOn(Storage.prototype,'removeItem').mockImplementation(()=>{throw new Error('blocked storage')})
    await expect(c.getKioskTokenFor(moduleId,true)).rejects.toMatchObject({code:'storage'})
    expect(c.kioskState.value).toBe('revoked');expect(c.kioskIdentity()).toBeNull()
  })
  it('does not send credentials to another backend or module',async()=>{
    const c=await pair();send.mockClear()
    await expect(c.getKioskTokenFor('org.example.foreign')).rejects.toMatchObject({code:'denied'})
    vi.mocked(getBackendUrl).mockResolvedValue('http://foreign.test')
    await expect(c.getKioskTokenFor(moduleId,true)).rejects.toMatchObject({code:'unavailable'})
    expect(send).not.toHaveBeenCalled()
  })
  it.each(['module','terminal','incarnation'])('refuses a renewal with foreign %s',async fault=>{
    const c=await pair();const v=response()
    if(fault==='module')v.module_id='org.example.other'
    if(fault==='terminal')v.terminal_id='f'.repeat(32)
    if(fault==='incarnation')v.installation_incarnation='f'.repeat(32)
    send.mockResolvedValueOnce({data:v})
    await expect(c.getKioskTokenFor(moduleId,true)).rejects.toThrow()
    expect(c.kioskState.value).not.toBe('ready')
  })
  it('does not send anything when proof storage fails',async()=>{
    const c=await controller();vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('quota')})
    await expect(c.beginKioskClaim(moduleId,'x'.repeat(32))).rejects.toMatchObject({code:'storage'})
    expect(send).not.toHaveBeenCalled()
  })
  it.each(['human','foreignModule','foreignTerminal','foreignIncarnation'])('rejects a %s token even when response metadata looks valid',async fault=>{
    const c=await controller(),v=response()
    v.access_token=token(fault==='human'?{token_type:'user',sub:'1'}:fault==='foreignModule'?{module_id:'org.example.foreign'}:fault==='foreignTerminal'?{terminal_id:'f'.repeat(32)}:{incarnation:'f'.repeat(32)})
    send.mockResolvedValueOnce({data:v})
    await expect(c.beginKioskClaim(moduleId,'x'.repeat(32))).rejects.toMatchObject({code:'unavailable'})
    expect(localStorage.getItem(SESSION)).toBeNull()
    expect(c.kioskClaimInfo()).not.toBeNull()
  })
  it('captures codes only in fragments on the Core bootstrap route and removes history',async()=>{
    const c=await controller();history.replaceState({},'','/kiosk/connect#module='+moduleId+'&code='+'x'.repeat(32)+'&returnUrl=https://foreign.test')
    c.captureKioskLink()
    expect(location.hash).toBe('');expect(c.takeKioskLink()).toEqual({module:moduleId,code:'x'.repeat(32)})
    expect(c.takeKioskLink()).toBeNull();expect(send).not.toHaveBeenCalled()
    history.replaceState({},'','/')
  })
  it('forgetting a kiosk never signs out the administrator',async()=>{
    const c=await pair();localStorage.setItem('authToken','human-login');c.forgetKioskConnection()
    expect(localStorage.getItem(SESSION)).toBeNull();expect(localStorage.getItem('authToken')).toBe('human-login')
    expect(c.kioskState.value).toBe('unpaired')
  })
})
