// Private Core browser adapter for interactive-session.v1. No reconnect/replay.
import { ApplicationHostError, type ApplicationPayload, type ApplicationSessions,
  type ApplicationSessionTarget, type ApplicationSessionOpen, type ApplicationSessionAcceptance,
} from '../extension-ui/application-v1'

const SESSION = /^ses_[a-f0-9]{32}$/
const ID = /^[a-z][a-z0-9_]{0,95}$/
const MAX_FRAME = 65536, MAX_PAYLOAD = 65278
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value)
function fail(code: 'unavailable' | 'unconfirmed' | 'invalid_request' = 'unavailable'): never { throw new ApplicationHostError(code) }
const encoder = new TextEncoder()
const same = (a: unknown, b: unknown): boolean => {
  if (Object.is(a, b)) return true
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((value, index) => same(value, b[index]))
  return object(a) && object(b) && Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(key => Object.prototype.hasOwnProperty.call(b, key) && same(a[key], b[key]))
}
function bounded(value: unknown): void {
  let nodes = 0
  const visit = (item: unknown, depth = 0): boolean => {
    if (++nodes > 8192 || depth > 16) return false
    if (item === null || typeof item === 'string' || typeof item === 'boolean') return true
    if (typeof item === 'number') return Number.isFinite(item) && (!Number.isInteger(item) || Number.isSafeInteger(item))
    if (Array.isArray(item)) return item.every(child => visit(child, depth + 1))
    return object(item) && [Object.prototype, null].includes(Object.getPrototypeOf(item))
      && Object.entries(item).every(([key, child]) => visit(key, depth + 1) && visit(child, depth + 1))
  }
  if (!visit(value) || encoder.encode(JSON.stringify(value)).length > 8192) fail('invalid_request')
}
function target(value: unknown): ApplicationSessionTarget {
  if (!object(value) || Object.keys(value).sort().join() !== ['bindingId', 'deviceId', 'providerId', 'capabilityIds', 'available', 'accessMode', 'controlActions', 'options'].sort().join()
    || typeof value.bindingId !== 'string' || !ID.test(value.bindingId) || typeof value.deviceId !== 'string' || !/^dev_[a-f0-9]{32}$/.test(value.deviceId)
    || typeof value.providerId !== 'string' || value.providerId.length > 160 || !/^[a-z0-9]+(?:[.-][a-z0-9]+)+$/.test(value.providerId)
    || typeof value.available !== 'boolean' || !['read', 'write'].includes(String(value.accessMode))
    || !Array.isArray(value.capabilityIds) || value.capabilityIds.length !== 1 || typeof value.capabilityIds[0] !== 'string'
    || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/.test(value.capabilityIds[0])
    || !Array.isArray(value.controlActions) || value.controlActions.length > 16 || new Set(value.controlActions).size !== value.controlActions.length
    || !value.controlActions.every(action => typeof action === 'string' && /^[a-z][a-z0-9_.-]{0,63}$/.test(action)) || !object(value.options)) fail()
  bounded(value.options)
  return Object.freeze({ ...value, capabilityIds: Object.freeze([...value.capabilityIds]), controlActions: Object.freeze([...value.controlActions]), options: structuredClone(value.options) }) as unknown as ApplicationSessionTarget
}

type Pending = { resolve(value?: unknown): void; reject(error: Error): void; timer: ReturnType<typeof setTimeout> }
type LiveSession = {
  socket: WebSocket; id: string; request: ApplicationSessionOpen; seq: number; outSeq: number; closed: boolean
  handlers: Set<{ onData(data: Uint8Array): void; onClosed(reason?: string): void }>
  buffer: Uint8Array[]; bytes: number; pending: Map<string, Pending>
  write: Promise<void>; opening: Pending
  inputBytes: number; inputCount: number
}
export function createApplicationSessions(context: {
  request(path: string, body?: unknown): Promise<unknown>; socketUrl(path: string): string
  ui: Record<string, unknown>; live(): void
}) {
  const prefix = `/session-host/${encodeURIComponent(String(context.ui.entrypoint_id))}`
  const active = new Map<string, LiveSession>()
  const opening = new Set<LiveSession>()
  const spent = new Set<string>()
  let pendingOpens = 0
  let recoveryRequired = false
  function finish(session: LiveSession, code: 'unconfirmed' | 'disposed' | 'unavailable' = 'unconfirmed') {
    if (session.closed) return
    session.closed = true
    if (code === 'unconfirmed') recoveryRequired = true
    opening.delete(session); active.delete(session.id)
    clearTimeout(session.opening.timer); session.opening.reject(new ApplicationHostError(code))
    for (const pending of session.pending.values()) { clearTimeout(pending.timer); pending.reject(new ApplicationHostError(code)) }
    session.pending.clear(); session.buffer.length = 0; session.bytes = 0
    try { session.socket.close() } catch { /* Already closed or never connected. */ }
    for (const handler of session.handlers) { try { handler.onClosed(code) } catch { /* Consumer cannot prevent cleanup. */ } }
    session.handlers.clear()
  }
  function wait(session: LiveSession, key: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { finish(session) }, 10_000)
      session.pending.set(key, { resolve: () => resolve(), reject, timer })
    })
  }
  function ack(session: LiveSession, key: string) {
    const pending = session.pending.get(key)
    if (!pending) fail()
    clearTimeout(pending.timer); session.pending.delete(key); pending.resolve()
  }
  function receive(session: LiveSession, data: unknown) {
    if (session.closed) return
    try {
      context.live()
      if (typeof data === 'string') {
        if (encoder.encode(data).length > MAX_FRAME) fail()
        const value = JSON.parse(data)
        if (!object(value)) fail()
        if (value.op === 'opened') {
          const acceptance = value.acceptance
          if (!opening.has(session) || !object(acceptance) || acceptance.session_id !== session.id || acceptance.state !== 'active'
            || !['request_id', 'device_id', 'provider_id', 'capability_id'].every(key => acceptance[key] === session.request[key as keyof ApplicationSessionOpen])) fail()
          opening.delete(session); active.set(session.id, session)
          clearTimeout(session.opening.timer)
          session.opening.resolve(Object.freeze(Object.fromEntries(['request_id', 'session_id', 'state', 'device_id', 'provider_id', 'capability_id'].map(key => [key, acceptance[key]]))))
        } else if (value.session_id !== session.id || !active.has(session.id)) fail()
        else if (value.op === 'input_ack' && Number.isSafeInteger(value.seq)) ack(session, `data:${value.seq}`)
        else if (value.op === 'control_ack' && typeof value.control_id === 'string') ack(session, `control:${value.control_id}`)
        else fail()
      } else {
        if (!(data instanceof ArrayBuffer) || data.byteLength > MAX_FRAME || data.byteLength < 11 || !active.has(session.id)) fail()
        const bytes = new Uint8Array(data), view = new DataView(data)
        if (String.fromCharCode(...bytes.subarray(0, 4)) !== '3MMS' || bytes[4] !== 1) fail()
        const size = view.getUint32(5)
        if (size < 2 || size > 258 || 9 + size > bytes.length) fail()
        const header = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(9, 9 + size)))
        const payload = bytes.slice(9 + size)
        if (!object(header) || Object.keys(header).sort().join() !== ['schema_version', 'op', 'seq', 'session_id', 'payload_kind', 'payload_length'].sort().join()
          || header.schema_version !== 1 || header.op !== 'data' || header.session_id !== session.id || header.seq !== session.outSeq + 1
          || header.payload_kind !== 'binary' || header.payload_length !== payload.length || !payload.length || payload.length > MAX_PAYLOAD) fail()
        session.outSeq++
        if (!session.handlers.size) {
          if (session.bytes + payload.length > MAX_FRAME) fail()
          session.buffer.push(payload); session.bytes += payload.length
        } else for (const handler of session.handlers) handler.onData(payload.slice())
      }
    } catch { finish(session) }
  }
  const sessions: ApplicationSessions = Object.freeze<ApplicationSessions>({
    async targets() {
      context.live()
      if (!context.ui.built_ui_sha256) fail()
      const response = await context.request(`${prefix}?artifact_sha256=${context.ui.artifact_sha256}&built_ui_sha256=${context.ui.built_ui_sha256}`)
      if (!object(response) || response.session_host_version !== 1 || !Array.isArray(response.targets) || response.targets.length > 32) fail()
      const values = response.targets.map(target)
      if (new Set(values.map(item => item.bindingId)).size !== values.length) fail()
      return Object.freeze(values)
    },
    async resolveTarget(id: string) {
      const matches = (await sessions.targets()).filter(item => item.bindingId === id || item.deviceId === id)
      if (matches.length !== 1) fail()
      return matches[0]!
    },
    async open(request: ApplicationSessionOpen) {
      context.live(); bounded(request)
      if (recoveryRequired) fail('unconfirmed')
      const copy = structuredClone(request)
      if (!/^[a-z][a-z0-9_]{0,95}$/.test(copy.request_id) || copy.session_request_version !== 1
        || spent.has(copy.request_id) || spent.size >= 1024 || active.size + pendingOpens >= 4) fail('invalid_request')
      spent.add(copy.request_id) // Reserve before the first async preflight; never replay.
      pendingOpens++
      try {
      const matches = (await sessions.targets()).filter(item => item.available && item.deviceId === copy.device_id
        && item.providerId === copy.provider_id && item.capabilityIds.includes(copy.capability_id) && item.accessMode === copy.access_mode && same(item.options, copy.options))
      if (matches.length !== 1) fail()
      const issued = await context.request(`${prefix}/ticket`, { ui_context: context.ui, binding_id: matches[0]!.bindingId, request: copy })
      if (!object(issued) || issued.session_host_version !== 1 || issued.request_id !== copy.request_id
        || typeof issued.session_id !== 'string' || !SESSION.test(issued.session_id) || typeof issued.ticket !== 'string'
        || !/^[A-Za-z0-9_-]{43}$/.test(issued.ticket) || issued.expires_in_seconds !== 15) fail('unconfirmed')
      context.live()
      const socket = new WebSocket(context.socketUrl(`${prefix}/ws`))
      socket.binaryType = 'arraybuffer'
      return await new Promise<ApplicationSessionAcceptance>((resolve, reject) => {
        const session: LiveSession = { socket, id: issued.session_id as string, request: copy, seq: 0, outSeq: 0, closed: false,
          handlers: new Set(), buffer: [], bytes: 0, inputBytes: 0, inputCount: 0, pending: new Map(), write: Promise.resolve(),
          // ARMv6 cold imports have a separate, bounded opening window.
          opening: { resolve: value => resolve(value as ApplicationSessionAcceptance), reject, timer: setTimeout(() => finish(session), 120_000) } }
        opening.add(session)
        socket.onopen = () => { try { context.live(); socket.send(JSON.stringify({ op: 'authenticate', ticket: issued.ticket })) } catch { finish(session) } }
        socket.onmessage = event => receive(session, event.data)
        socket.onerror = () => finish(session)
        socket.onclose = event => {
          const closing = session.pending.get('close')
          if (event.code === 1000 && closing) {
            clearTimeout(closing.timer); session.pending.delete('close'); closing.resolve()
          }
          finish(session, event.code === 1000 && closing ? 'unavailable' : 'unconfirmed')
        }
      })
      } catch (error) {
        if (error instanceof ApplicationHostError && error.code === 'unconfirmed') recoveryRequired = true
        throw error
      } finally { pendingOpens-- }
    },
    async sendData(id: string, data: Uint8Array) {
      context.live()
      const session = active.get(id)
      if (!session || !(data instanceof Uint8Array) || !data.length || data.length > MAX_PAYLOAD
        || session.inputCount >= 16 || session.inputBytes + data.length > MAX_FRAME) fail('invalid_request')
      const copy = data.slice()
      session.inputCount++; session.inputBytes += copy.length
      const operation = session.write.then(async () => {
        context.live()
        if (session.closed || session.socket.bufferedAmount > MAX_FRAME || session.seq >= 0xffffffff) fail('unconfirmed')
        const seq = ++session.seq
        const header = encoder.encode(JSON.stringify({ schema_version: 1, op: 'data', seq, session_id: id, payload_kind: 'binary', payload_length: copy.length }))
        const frame = new Uint8Array(9 + header.length + copy.length)
        frame.set(encoder.encode('3MMS')); frame[4] = 1; new DataView(frame.buffer).setUint32(5, header.length)
        frame.set(header, 9); frame.set(copy, 9 + header.length)
        const pending = wait(session, `data:${seq}`)
        try { session.socket.send(frame) } catch { finish(session) }
        await pending
      }).catch(error => { finish(session); throw error })
      session.write = operation.catch(() => {})
      try { await operation } finally { session.inputCount--; session.inputBytes -= copy.length }
    },
    async control(message) {
      context.live(); bounded(message)
      const copy = structuredClone(message), session = active.get(copy.session_id)
      if (!session || !/^[a-z][a-z0-9_]{0,95}$/.test(copy.control_id) || session.pending.size >= 16
        || session.pending.has(`control:${copy.control_id}`) || session.socket.bufferedAmount > MAX_FRAME) fail('invalid_request')
      const pending = wait(session, `control:${copy.control_id}`)
      try { session.socket.send(JSON.stringify({ op: 'control', control: copy })) } catch { finish(session) }
      await pending
    },
    async close(id: string) {
      context.live()
      const session = active.get(id)
      if (!session) return
      if (session.pending.has('close')) fail('unconfirmed')
      const pending = wait(session, 'close')
      try { session.socket.send(JSON.stringify({ op: 'close', session_id: id })) } catch { finish(session) }
      await pending
    },
    observe(id, handlers) {
      context.live()
      const session = active.get(id)
      if (!session) fail()
      session.handlers.add(handlers)
      try { for (const data of session.buffer.splice(0)) handlers.onData(data); session.bytes = 0 }
      catch { finish(session) }
      return () => { session.handlers.delete(handlers) }
    },
  })
  return { sessions, dispose() { for (const session of [...opening, ...active.values()]) finish(session, 'disposed') } }
}
