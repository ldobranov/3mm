import { ApplicationHostError, type ApplicationFiles, type ApplicationFileMetadata, type ApplicationPayload } from '../extension-ui/application-v1'
import { FileChecksum } from './file-checksum'

const CHUNK = 256 * 1024
const id = /^[a-z][a-z0-9_]{0,63}$/
const digest = /^[0-9a-f]{64}$/
function random(size = 16) {
  if (!globalThis.crypto?.getRandomValues) throw new ApplicationHostError('unavailable')
  return Array.from(crypto.getRandomValues(new Uint8Array(size)), b => b.toString(16).padStart(2, '0')).join('')
}
export function createApplicationFiles(deps: {
  request(path: string, data?: unknown): Promise<unknown>; live(): void; ui: object
  raw(path: string, content?: Blob): Promise<{ bytes: Uint8Array; headers: Headers }>
  sharePath(linkId: string): Promise<string>
}): ApplicationFiles {
  const query = new URLSearchParams(Object.entries(deps.ui).filter(([key]) => key !== 'host_version').map(([key,value]) => [key,String(value)])).toString()
  async function control(operation: string, fields: object = {}, requestId = random()): Promise<ApplicationPayload> {
    deps.live()
    let result: unknown
    try {
      result = await deps.request('/files/control', { ui_context: deps.ui,
        file_request: { file_request_version: 2, request_id: requestId, operation, ...fields } })
    } catch(error) {
      if (error instanceof ApplicationHostError && error.code === 'unconfirmed') throw new ApplicationHostError('unconfirmed', requestId)
      throw error
    }
    if (!result || typeof result !== 'object' || (result as {ok?: unknown}).ok !== true) throw new ApplicationHostError('unconfirmed')
    return result as ApplicationPayload
  }
  async function stat(fileId: string) {
    if (!id.test(fileId)) throw new ApplicationHostError('invalid_request')
    return (await control('stat', { file_id: fileId })).file as unknown as ApplicationFileMetadata
  }
  async function checksum(file: Blob) {
    if (file.size > 1073741824) throw new ApplicationHostError('invalid_request')
    const hash = new FileChecksum()
    for (let offset=0; offset<file.size; offset+=CHUNK) {
      deps.live(); hash.update(new Uint8Array(await file.slice(offset,offset+CHUNK).arrayBuffer()))
    }
    return hash.digest()
  }
  return Object.freeze({
    checksum, stat, control,
    async list(after = '') { return control('list', {after}) },
    async begin(fileId, file, options) {
      if (!id.test(fileId) || !digest.test(options.sha256)) throw new ApplicationHostError('invalid_request')
      return control('begin', {file_id:fileId, size_bytes:file.size, sha256:options.sha256,
        filename:options.filename, content_type:options.contentType, expected_sha256:options.expectedSha256 ?? null}, options.requestId)
    },
    async append(uploadId, offset, chunk) {
      if (!/^[0-9a-f]{32}$/.test(uploadId) || !Number.isSafeInteger(offset) || offset < 0 || !chunk.size || chunk.size > CHUNK) throw new ApplicationHostError('invalid_request')
      const {bytes} = await deps.raw(`/files/uploads/${uploadId}/chunks?${query}&offset=${offset}`, chunk)
      const result = JSON.parse(new TextDecoder().decode(bytes))
      if (result.ok !== true || result.offset !== offset+chunk.size) throw new ApplicationHostError('unconfirmed')
      return result as ApplicationPayload
    },
    async uploadStatus(uploadId) { return control('upload_status', {upload_id:uploadId}) },
    async finalize(uploadId, requestId) { return control('finalize', {upload_id:uploadId}, requestId) },
    async cancel(uploadId, requestId) { return control('cancel', {upload_id:uploadId}, requestId) },
    async remove(fileId, sha256, requestId) { return control('delete', {file_id:fileId, expected_sha256:sha256}, requestId) },
    async download(fileId) {
      const metadata = await stat(fileId), hash = new FileChecksum()
      let offset = 0
      return new ReadableStream<Uint8Array>({ async pull(controller) {
        try {
          deps.live()
          if (offset === metadata.size_bytes) {
            if (hash.digest() !== metadata.sha256) throw new ApplicationHostError('unavailable')
            controller.close(); return
          }
          const {bytes,headers} = await deps.raw(`/files/${fileId}/chunks?${query}&sha256=${metadata.sha256}&offset=${offset}&length=${CHUNK}`)
          if (!bytes.length || bytes.length>CHUNK || offset+bytes.length>metadata.size_bytes
              || headers.get('X-Content-SHA256') !== metadata.sha256
              || new FileChecksum().update(bytes).digest() !== headers.get('X-Chunk-SHA256')) throw new ApplicationHostError('unavailable')
          hash.update(bytes); offset+=bytes.length; controller.enqueue(bytes)
        } catch (error) { controller.error(error) }
      } })
    },
    async createLink(fileId, sha256, options) {
      const token = random(32)
      const value = await control('link', {file_id:fileId,sha256,token,ttl_seconds:options.ttlSeconds,max_downloads:options.maxDownloads}, options.requestId)
      if (typeof value.link_id !== 'string' || !/^[0-9a-f]{32}$/.test(value.link_id)) throw new ApplicationHostError('unconfirmed')
      return Object.freeze({linkId:value.link_id, expiresAt:Number(value.expires_at), url:await deps.sharePath(value.link_id)+'#'+token})
    },
    async revokeLink(linkId, requestId) { return control('unlink', {link_id:linkId}, requestId) },
    async transform(fileId, sha256, options) { return control('transform', {file_id:fileId,sha256,output_id:options.outputId,width:options.width,height:options.height,format:options.format}, options.requestId) },
    async job(jobId) { return control('job', {job_id:jobId}) },
    async operationStatus(requestId) {
      if (!/^[0-9a-f]{32}$/.test(requestId)) throw new ApplicationHostError('invalid_request')
      return await deps.request(`/files/requests/${requestId}?${query}`) as ApplicationPayload
    },
  } satisfies ApplicationFiles)
}
