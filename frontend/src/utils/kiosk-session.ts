// One Core-owned browser kiosk identity, separate from the human login. No
// credential/controller method is an application host export.
import { shallowRef, readonly } from 'vue'
import { getBackendUrl } from './runtime-config'
import { kioskRequest, kioskModule, KioskError } from './kiosk-api'
const SESSION='threeMmKioskSessionV1', PENDING='threeMmKioskClaimV1'
type Identity={version:1;module:string;terminal:string;credential:string;incarnation:string;token:string;expires:number;artifact:string;build:string|null;backend:string}
type Claim={version:1;module:string;request_id:string;recovery_proof:string;code:string;backend:string}
type State='unpaired'|'claiming'|'ready'|'renewing'|'offline'|'revoked'
const state=shallowRef<State>('unpaired')
export const kioskState=readonly(state)
const hex=(v:unknown,n:number):v is string=>typeof v==='string'&&new RegExp(`^[a-f0-9]{${n}}$`).test(v)
const secret=(v:unknown):v is string=>typeof v==='string'&&/^[A-Za-z0-9_-]{43}$/.test(v)
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v)
let current:Identity|null=null, initialized=false, generation=0, checked=0, flight:Promise<string>|null=null, claimBusy=false
let initialLink:{module:string;code:string}|null=null
function write(key:string,value:unknown){try{localStorage.setItem(key,JSON.stringify(value))}catch{throw new KioskError('storage')}}
function read(key:string):unknown{try{const v=localStorage.getItem(key);return v?JSON.parse(v):null}catch{throw new KioskError('storage')}}
function clear(key:string){try{localStorage.removeItem(key)}catch{throw new KioskError('storage')}}
function initialize(){
  if(initialized)return
  const v=read(SESSION)
  if(v!==null){
    if(!object(v)||v.version!==1||typeof v.module!=='string'||!kioskModule.test(v.module)||!hex(v.terminal,32)||!secret(v.credential)
      ||!hex(v.incarnation,32)||typeof v.token!=='string'||v.token.length>4096||typeof v.expires!=='number'||!Number.isFinite(v.expires)
      ||!hex(v.artifact,64)||(v.build!==null&&!hex(v.build,64))||typeof v.backend!=='string')throw new KioskError('storage')
    current=v as unknown as Identity
  }
  initialized=true
}
export function kioskIdentity(){initialize();return current?Object.freeze({module:current.module,terminal:current.terminal,artifact:current.artifact,build:current.build}):null}
export function kioskRouteAvailable(module:unknown){return ['ready','renewing'].includes(state.value)&&kioskIdentity()?.module===module}
function pendingKioskClaim(){
  const v=read(PENDING)
  if(v===null)return null
  if(!object(v)||v.version!==1||typeof v.module!=='string'||!kioskModule.test(v.module)||!hex(v.request_id,32)||!secret(v.recovery_proof)
    ||typeof v.code!=='string'||!/^[A-Za-z0-9_-]{32}$/.test(v.code)||typeof v.backend!=='string')throw new KioskError('storage')
  return v as unknown as Claim
}
export function kioskClaimInfo(){const v=pendingKioskClaim();return v?Object.freeze({module:v.module,request_id:v.request_id}):null}
export function kioskRandomId(){return Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join('')}
function proof(){return btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(32)))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'')}
function tokenMatches(token:string,module:string,terminal:string,incarnation:string){
  // Consistency only. The server verifies signature and live authority on every
  // admission; this parser must never turn browser claims into permissions.
  try{
    const parts=token.split('.')
    if(parts.length!==3||!parts.every(p=>/^[A-Za-z0-9_-]+$/.test(p)))return false
    const claims=JSON.parse(atob(parts[1]!.replace(/-/g,'+').replace(/_/g,'/')))
    return object(claims)&&claims.token_type==='application_kiosk'&&claims.module_id===module
      &&claims.terminal_id===terminal&&claims.incarnation===incarnation&&claims.sub==='kiosk:'+terminal
  }catch{return false}
}
function response(v:unknown,module:string,backend:string,credential:string):Identity{
  if(!object(v)||v.module_id!==module||!hex(v.terminal_id,32)||!hex(v.installation_incarnation,32)||!hex(v.artifact_sha256,64)
      ||v.built_ui_sha256!==null&&!hex(v.built_ui_sha256,64)||typeof v.access_token!=='string'||v.access_token.length>4096
      ||!tokenMatches(v.access_token,module,v.terminal_id,v.installation_incarnation)||v.expires_in_seconds!==900)throw new KioskError('unavailable')
  return {version:1,module,backend,terminal:v.terminal_id,credential,incarnation:v.installation_incarnation,
    artifact:v.artifact_sha256,build:v.built_ui_sha256 as string|null,token:v.access_token,expires:Date.now()+900000}
}
export async function beginKioskClaim(module:string,code:string){
  if(claimBusy)throw new KioskError('conflict')
  claimBusy=true
  try {
  initialize()
  if(pendingKioskClaim()||current)throw new KioskError('conflict')
  if(!kioskModule.test(module)||!/^[A-Za-z0-9_-]{32}$/.test(code))throw new KioskError('invalid')
  const pending:Claim={version:1,module,code,request_id:kioskRandomId(),recovery_proof:proof(),backend:await getBackendUrl()}
  write(PENDING,pending) // Persist proof + exact request before the only send.
  return await recoverClaim()
  }finally{claimBusy=false}
}
export async function recoverKioskClaim(){
  if(claimBusy)throw new KioskError('conflict')
  claimBusy=true
  try{return await recoverClaim()}finally{claimBusy=false}
}
async function recoverClaim(){
  initialize();const pending=pendingKioskClaim()
  if(!pending)throw new KioskError('invalid')
  if(flight)throw new KioskError('conflict')
  const epoch=++generation;state.value='claiming'
  try{
    const value=await kioskRequest(pending.module,'enrollments/claim',{
      request_id:pending.request_id,recovery_proof:pending.recovery_proof,code:pending.code},false,undefined,pending.backend)
    if(!object(value)||!secret(value.credential))throw new KioskError('unavailable')
    const session=response(value,pending.module,pending.backend,value.credential)
    if(epoch!==generation)throw new KioskError('conflict')
    write(SESSION,session);current=session;checked=Date.now();clear(PENDING);state.value='ready'
    return kioskIdentity()
  }catch(error){if(epoch===generation)state.value='offline';throw error}
}
export async function getKioskTokenFor(module:string,force=false):Promise<string>{
  initialize()
  if(!current||current.module!==module)throw new KioskError('denied')
  const owned=current
  if(owned.backend!==await getBackendUrl())throw new KioskError('unavailable')
  if(!force&&state.value==='ready'&&owned.expires>Date.now()+60000&&Date.now()-checked<25000)return owned.token
  if(flight)return flight
  const epoch=generation;state.value='renewing'
  const pending=(async()=>{
    try{
      const value=await kioskRequest(module,'sessions',{terminal_id:owned.terminal,credential:owned.credential},false,undefined,owned.backend)
      if(epoch!==generation||current?.terminal!==owned.terminal)throw new KioskError('conflict')
      const session=response(value,module,owned.backend,owned.credential)
      if(session.terminal!==owned.terminal||session.incarnation!==owned.incarnation)throw new KioskError('denied')
      write(SESSION,session);current=session;checked=Date.now();state.value='ready';return session.token
    }catch(error){
      if(epoch===generation){
        if(error instanceof KioskError&&error.code==='denied'){current=null;state.value='revoked';clear(SESSION)}
        else state.value='offline'
      }
      throw error
    }
  })()
  flight=pending
  try{return await pending}finally{if(flight===pending)flight=null}
}
export async function getKioskCatalogToken(){
  initialize();if(!current)return null
  try{return await getKioskTokenFor(current.module)}catch{return null}
}
export function forgetKioskConnection(){
  ++generation;current=null;flight=null;checked=0;clear(SESSION);clear(PENDING);state.value='unpaired'
  // Remove only the obsolete Core kiosk flag. Human login is a separate owner.
  localStorage.removeItem('applicationKioskToken')
}
export function captureKioskLink(){
  if(location.pathname!=='/kiosk/connect'||!location.hash)return
  const fields=new URLSearchParams(location.hash.slice(1));const module=fields.get('module')||'',code=fields.get('code')||''
  history.replaceState(history.state,'',location.pathname+location.search)
  if(kioskModule.test(module)&&/^[A-Za-z0-9_-]{32}$/.test(code))initialLink={module,code}
}
export function takeKioskLink(){const value=initialLink;initialLink=null;return value}
if(typeof window!=='undefined')window.addEventListener('storage',event=>{
  if(event.key===SESSION){++generation;current=null;initialized=false;checked=0;state.value='unpaired'}
})
