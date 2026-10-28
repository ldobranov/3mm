import { describe, expect, it, vi } from 'vitest'
import { createHash } from 'node:crypto'
import { Blob as NodeBlob } from 'node:buffer'
import { FileChecksum } from './file-checksum'
import { createApplicationFiles } from './application-files-host'
import { ApplicationHostError } from '../extension-ui/application-v1'

const hash = (bytes:Uint8Array) => createHash('sha256').update(bytes).digest('hex')
describe('incremental file integrity on HTTP LAN', () => {
  it.each([0,3,55,56,63,64,65,1000000])('matches standard SHA-256 for %i bytes in uneven chunks', size => {
    const bytes=Uint8Array.from({length:size},(_,i)=>i%251), checksum=new FileChecksum()
    for(let offset=0;offset<bytes.length;offset+=91)checksum.update(bytes.subarray(offset,offset+91))
    expect(checksum.digest()).toBe(hash(bytes))
    expect(()=>checksum.digest()).toThrow()
  })
})

describe('public file SDK', () => {
  function environment(bytes=new Uint8Array([1,2,3])) {
    const ui={host_version:1,entrypoint_id:'files',artifact_sha256:'a'.repeat(64),built_ui_sha256:'b'.repeat(64)}
    const request=vi.fn(async(_path:string,data?:unknown):Promise<unknown>=> {
      const operation=(data as {file_request:{operation:string}})?.file_request.operation
      if(operation==='stat')return {ok:true,file:{file_id:'sample',size_bytes:bytes.length,sha256:hash(bytes),filename:'sample.bin',content_type:'application/octet-stream',origin:null,created_at:1}}
      if(operation==='link')return {ok:true,link_id:'d'.repeat(32),expires_at:60}
      return {ok:true}
    })
    const raw=vi.fn(async(path:string,chunk?:Blob)=> {
      const offset=Number(new URL(path,'https://local/').searchParams.get('offset'))
      if(chunk)return {bytes:new TextEncoder().encode(JSON.stringify({ok:true,offset:offset+chunk.size})),headers:new Headers()}
      const part=bytes.slice(offset,offset+256*1024)
      return {bytes:part,headers:new Headers({'X-Chunk-SHA256':hash(part),'X-Content-SHA256':hash(bytes)})}
    })
    const live=vi.fn(), sharePath=vi.fn(async(id:string)=>'http://device/files/links/'+id+'/open')
    return {files:createApplicationFiles({request,raw,live,ui,sharePath}),request,raw,live}
  }
  it('hashes and downloads >1 MiB without SubtleCrypto, verifies final bytes',async()=> {
    const bytes=Uint8Array.from({length:1200000},(_,i)=>i%251), s=environment(bytes)
    expect(await s.files.checksum(new NodeBlob([bytes]) as Blob)).toBe(hash(bytes))
    const stream=await s.files.download('sample'), reader=stream.getReader(), chunks:Uint8Array[]=[]
    for(;;){const part=await reader.read();if(part.done)break;chunks.push(part.value)}
    expect(chunks.every(c=>c.length<=256*1024)).toBe(true)
    expect(hash(Buffer.concat(chunks))).toBe(hash(bytes))
    expect(s.raw).toHaveBeenCalledTimes(5)
  })
  it('refuses corrupt chunks and does not retry failed mutations',async()=> {
    const s=environment()
    s.raw.mockResolvedValueOnce({bytes:new Uint8Array([9]),headers:new Headers({'X-Chunk-SHA256':'a'.repeat(64),'X-Content-SHA256':'b'.repeat(64)})})
    const stream=await s.files.download('sample')
    await expect(stream.getReader().read()).rejects.toMatchObject({code:'unavailable'})
    s.request.mockRejectedValueOnce(new ApplicationHostError('unconfirmed'))
    await expect(s.files.finalize('d'.repeat(32),'e'.repeat(32))).rejects.toMatchObject({code:'unconfirmed',requestId:'e'.repeat(32)})
    expect(s.request).toHaveBeenCalledTimes(2)
  })
  it('sends chunks as raw Blob, persists upload identity for explicit resume',async()=> {
    const s=environment(),chunk=new NodeBlob([new Uint8Array([1,2,3])]) as Blob
    await s.files.append('d'.repeat(32),5,chunk)
    expect(s.raw.mock.calls[0]![1]).toBe(chunk)
    await s.files.uploadStatus('d'.repeat(32))
    expect(s.request.mock.calls[0]![1]).toMatchObject({file_request:{operation:'upload_status',upload_id:'d'.repeat(32)}})
    await expect(s.files.append('d'.repeat(32),0,new NodeBlob([new Uint8Array(256*1024+1)]) as Blob)).rejects.toMatchObject({code:'invalid_request'})
    expect(s.raw).toHaveBeenCalledTimes(1)
  })
  it('keeps public capability secret in fragment and out of public host transport',async()=> {
    const s=environment(),link=await s.files.createLink('sample','a'.repeat(64),{ttlSeconds:60,maxDownloads:1})
    expect(link.url).toMatch(/\/open#[0-9a-f]{64}$/)
    expect(new URL(link.url).search).toBe('')
    expect(Object.keys(s.files)).not.toContain('token')
    expect(JSON.stringify(s.files)).not.toContain('device')
  })
  it('stops requests after host disposal',async()=> {
    const s=environment()
    s.live.mockImplementation(()=>{throw new ApplicationHostError('disposed')})
    await expect(s.files.list()).rejects.toMatchObject({code:'disposed'})
    expect(s.request).not.toHaveBeenCalled()
  })
})
