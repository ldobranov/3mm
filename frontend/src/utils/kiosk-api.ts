// Core-internal transport. Never exported from the application SDK.
import axios from 'axios'
import { getBackendUrl } from './runtime-config'
import { getToken } from './auth'
export const kioskModule = /^[a-z0-9]+(?:[.-][a-z0-9]+)+$/
export class KioskError extends Error {
  constructor(public code:'denied'|'unavailable'|'conflict'|'expired'|'storage'|'invalid',public status?:number){super(code)}
}
export async function kioskRequest(module:string,path:string,data?:unknown,admin=false,method?:string,expectedBackend?:string):Promise<unknown>{
  if(!kioskModule.test(module))throw new KioskError('invalid')
  const base=await getBackendUrl()
  if(expectedBackend!==undefined && expectedBackend!==base)throw new KioskError('unavailable')
  try {
    const token=admin?getToken():''
    if(admin&&!token)throw new KioskError('denied')
    const result=await axios.request({url:`${base}/api/v1/application-extensions/${encodeURIComponent(module)}/kiosk/${path}`,
      method:method??(data===undefined?'GET':'POST'),data,headers:{Authorization:token?`Bearer ${token}`:undefined},timeout:8000,withCredentials:false})
    return result.data
  }catch(error){
    if(error instanceof KioskError)throw error
    const status=axios.isAxiosError(error)?error.response?.status:undefined
    throw new KioskError(status===401||status===403?'denied':status===409?'conflict':status===410?'expired':status===400||status===422?'invalid':'unavailable',status)
  }
}
