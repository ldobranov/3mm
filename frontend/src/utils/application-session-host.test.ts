import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createApplicationSessions } from './application-session-host'
import type { ApplicationSessionOpen } from '../extension-ui/application-v1'
import { ApplicationHostError } from '../extension-ui/application-v1'
import { browserDiagnosticSnapshot, clearBrowserDiagnostics } from './diagnostic-client'
const DEVICE = 'dev_' + 'a'.repeat(32), SESSION = 'ses_' + 'b'.repeat(32)
const target = { bindingId: 'console', deviceId: DEVICE, providerId: 'org.example.provider', capabilityIds: ['example.console'], accessMode: 'write', controlActions: ['resize'], options: { cols: 80, rows: 24 }, available: true }
const request: ApplicationSessionOpen = { session_request_version: 1, request_id: 'console_1', provider_id: target.providerId, device_id: DEVICE, capability_id: target.capabilityIds[0]!, access_mode: 'write', options: { cols: 80, rows: 24 } }
const ui = { host_version: 1, entrypoint_id: 'operations', artifact_sha256: 'c'.repeat(64), built_ui_sha256: 'd'.repeat(64) }
class Socket {
  static instances: Socket[] = []
  sent: Array<string | Uint8Array> = []
  onopen?: () => void
  onmessage?: (event: { data: unknown }) => void
  onerror?: () => void
  onclose?: (event: { code: number }) => void
  bufferedAmount = 0
  binaryType = ''
  close = vi.fn(() => { this.onclose?.({ code: 1006 }) })
  constructor(readonly url: string) { Socket.instances.push(this) }
  send(value: string | Uint8Array) { this.sent.push(value) }
  receive(value: unknown) { this.onmessage?.({ data: value }) }
}
const send = vi.fn()
let live = true
const make = () => createApplicationSessions({ ui, live() { if (!live) throw new Error('disposed') }, request: send, socketUrl: path => 'wss://core.example' + path })
const trace = 'invoke_' + 'e'.repeat(32)
const diagnosed = (extra = {}) => createApplicationSessions({ ui, live() {}, request: send,
  socketUrl: path => 'wss://core.example' + path, traceId: () => trace, ...extra })
beforeEach(() => {
  clearBrowserDiagnostics()
  live = true; Socket.instances = []; vi.stubGlobal('WebSocket', Socket)
  send.mockReset().mockImplementation(async (path: string) => path.endsWith('/ticket')
    ? { session_host_version: 1, session_id: SESSION, request_id: request.request_id, ticket: 't'.repeat(43), expires_in_seconds: 15 }
    : { session_host_version: 1, targets: [structuredClone(target)] })
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })
async function opened() {
  const host = make(), task = host.sessions.open(request)
  await vi.waitFor(() => expect(Socket.instances).toHaveLength(1))
  const socket = Socket.instances[0]!
  socket.onopen?.()
  socket.receive(JSON.stringify({ op: 'opened', acceptance: { ...request, session_id: SESSION, state: 'active' } }))
  const accepted = await task
  return { ...host, socket, accepted }
}
function frame(seq: number, sessionId = SESSION, payload = 'hello') {
  const encoder = new TextEncoder(), bytes = encoder.encode(payload)
  const header = encoder.encode(JSON.stringify({ schema_version: 1, op: 'data', seq, session_id: sessionId, payload_kind: 'binary', payload_length: bytes.length }))
  const frame = new Uint8Array(9 + header.length + bytes.length)
  frame.set(encoder.encode('3MMS')); frame[4] = 1; new DataView(frame.buffer).setUint32(5, header.length)
  frame.set(header, 9); frame.set(bytes, 9 + header.length)
  return frame.buffer
}
it('binds the exact UI and target, exposes no ticket/socket/credential to the extension', async () => {
  const { sessions, socket, accepted, dispose } = await opened()
  expect(Object.keys(sessions).sort()).toEqual(['targets', 'resolveTarget', 'open', 'sendData', 'control', 'close', 'observe'].sort())
  expect(send.mock.calls[1]![1]).toEqual({ ui_context: ui, binding_id: 'console', request })
  expect(socket.url).toBe('wss://core.example/session-host/operations/ws')
  expect(socket.sent[0]).toBe(JSON.stringify({ op: 'authenticate', ticket: 't'.repeat(43) }))
  expect(JSON.stringify(accepted)).not.toContain('ticket')
  expect(Object.keys(accepted).sort()).toEqual(['request_id', 'session_id', 'state', 'device_id', 'provider_id', 'capability_id'].sort())
  expect(browserDiagnosticSnapshot().records).toHaveLength(0)
  dispose()
})
it('records a missing build before HTTP without inferring any physical execution outcome', async () => {
  const host = diagnosed({ ui: { ...ui, built_ui_sha256: undefined } })
  await expect(host.sessions.targets()).rejects.toMatchObject({ code: 'unavailable' })
  expect(send).not.toHaveBeenCalled()
  expect(browserDiagnosticSnapshot().records[0]).toMatchObject({ stage: 'session.ui', cause: 'ui_build_missing', response_observed: false, execution: 'unknown' })
})
it.each([
  ['targets_response_invalid', { session_host_version: 2, targets: [] }],
  ['target_schema_invalid', { session_host_version: 1, targets: [{ ...target, options: { secret: Infinity } }] }],
  ['target_binding_duplicate', { session_host_version: 1, targets: [target, target] }],
])('records %s after HTTP success outside open, without target contents', async (cause, value) => {
  send.mockResolvedValue(value)
  await expect(diagnosed().sessions.targets()).rejects.toBeInstanceOf(ApplicationHostError)
  expect(browserDiagnosticSnapshot().records).toHaveLength(1)
  expect(browserDiagnosticSnapshot().records[0]).toMatchObject({ stage: 'session.targets.response', cause,
    last_passed_stage: 'session.targets.request', trace_id: trace, response_observed: true })
  expect(JSON.stringify(browserDiagnosticSnapshot())).not.toMatch(/secret|example.provider|cols|capabilityIds/)
  expect(send).toHaveBeenCalledTimes(1); expect(Socket.instances).toHaveLength(0)
})
it.each([false, true])('records a missing/ambiguous resolved target (ambiguous=%s), never dispatching a ticket', async ambiguous => {
  send.mockResolvedValue({ session_host_version: 1, targets: ambiguous ? [target, { ...target, bindingId: 'other' }] : [] })
  await expect(diagnosed().sessions.resolveTarget(DEVICE)).rejects.toMatchObject({ code: 'unavailable' })
  expect(browserDiagnosticSnapshot().records[0]).toMatchObject({ stage: 'session.resolve', cause: ambiguous ? 'target_ambiguous' : 'targets_empty',
    last_passed_stage: 'session.targets.response', trace_id: trace, response_observed: true })
  expect(send).toHaveBeenCalledTimes(1); expect(Socket.instances).toHaveLength(0)
})
it('distinguishes a caller ID mismatch from an empty target list, without collecting either identity', async () => {
  await expect(diagnosed().sessions.resolveTarget('SECRET_mismatched_id')).rejects.toMatchObject({ code: 'unavailable' })
  expect(browserDiagnosticSnapshot().records[0]).toMatchObject({ stage: 'session.resolve', cause: 'target_not_found',
    last_passed_stage: 'session.targets.response', trace_id: trace, response_observed: true })
  expect(JSON.stringify(browserDiagnosticSnapshot())).not.toMatch(/SECRET|console|example.provider|dev_/)
  expect(send).toHaveBeenCalledTimes(1); expect(Socket.instances).toHaveLength(0)
})
it('records exact-request refusal once, before ticket dispatch, without consuming a replacement request', async () => {
  await expect(diagnosed().sessions.open({ ...request, options: { cols: 99, rows: 24 } })).rejects.toMatchObject({ code: 'unavailable' })
  expect(browserDiagnosticSnapshot().records).toHaveLength(1)
  expect(browserDiagnosticSnapshot().records[0]).toMatchObject({ stage: 'session.request', cause: 'session_request_mismatch', trace_id: trace })
  expect(send).toHaveBeenCalledTimes(1); expect(Socket.instances).toHaveLength(0)
})
it('records invalid request before transport, keeping the original public error', async () => {
  await expect(diagnosed().sessions.open({ ...request, request_id: '../SECRET' })).rejects.toMatchObject({ code: 'invalid_request' })
  expect(send).not.toHaveBeenCalled()
  expect(browserDiagnosticSnapshot().records[0]).toMatchObject({ stage: 'session.request', cause: 'session_request_invalid', response_observed: false })
  expect(JSON.stringify(browserDiagnosticSnapshot())).not.toContain('SECRET')
})
it('captures a malformed non-object request without replacing its existing exception or dispatching', async () => {
  await expect(diagnosed().sessions.open(null as any)).rejects.toBeInstanceOf(TypeError)
  expect(send).not.toHaveBeenCalled()
  expect(browserDiagnosticSnapshot().records[0]).toMatchObject({ stage: 'session.request', cause: 'session_request_invalid' })
})
it.each(['protocol', 'callback'])('distinguishes %s failure during streaming without recording data or replaying', async kind => {
  const host = await opened()
  if (kind === 'callback') {
    host.sessions.observe(SESSION, { onData() { throw new Error('SECRET') }, onClosed() {} })
    host.socket.receive(frame(1))
  } else host.socket.receive('SECRET malformed message')
  const rows = browserDiagnosticSnapshot().records
  expect(rows).toHaveLength(1)
  expect(rows[0]).toMatchObject({ stage: 'session.stream', last_passed_stage: 'session.opening',
    cause: kind === 'protocol' ? 'session_protocol_invalid' : 'session_callback_failed', execution: 'unknown' })
  expect(JSON.stringify(rows)).not.toContain('SECRET')
  expect(Socket.instances).toHaveLength(1); host.dispose()
})
it('records a malformed ticket once and keeps the uncertainty fence without replay', async () => {
  send.mockImplementation(async path => path.endsWith('/ticket') ? { ticket: 'SECRET' } : { session_host_version: 1, targets: [target] })
  const host = diagnosed()
  await expect(host.sessions.open(request)).rejects.toMatchObject({ code: 'unconfirmed' })
  expect(browserDiagnosticSnapshot().records).toHaveLength(1)
  expect(browserDiagnosticSnapshot().records[0]).toMatchObject({ stage: 'session.ticket.response', cause: 'ticket_response_invalid', trace_id: trace })
  await expect(host.sessions.open({ ...request, request_id: 'replacement' })).rejects.toMatchObject({ code: 'unconfirmed' })
  expect(send).toHaveBeenCalledTimes(2); expect(Socket.instances).toHaveLength(0)
  expect(JSON.stringify(browserDiagnosticSnapshot())).not.toContain('SECRET')
})
it('captures a socket constructor failure without swallowing or retrying it, correlated with the ticket response', async () => {
  const error = new Error('SECRET url and ticket')
  vi.stubGlobal('WebSocket', class { constructor() { throw error } })
  await expect(diagnosed().sessions.open(request)).rejects.toBe(error)
  expect(browserDiagnosticSnapshot().records).toHaveLength(1)
  expect(browserDiagnosticSnapshot().records[0]).toMatchObject({ stage: 'session.socket', cause: 'socket_construction_failed',
    last_passed_stage: 'session.ticket.response', trace_id: trace, response_observed: true, execution: 'unknown' })
  expect(send).toHaveBeenCalledTimes(2)
  expect(JSON.stringify(browserDiagnosticSnapshot())).not.toContain('SECRET')
})
it('keeps each concurrent validation failure tied to its own successful response', async () => {
  const a = { session_host_version: 1, targets: [] }, b = { session_host_version: 0, targets: [] }
  let resolve!: (value: unknown) => void
  send.mockImplementationOnce(() => new Promise(done => { resolve = done })).mockResolvedValueOnce(b)
  const host = diagnosed({ traceId: (value: unknown) => value === a ? 'invoke_' + 'a'.repeat(32) : 'invoke_' + 'b'.repeat(32) })
  const first = host.sessions.resolveTarget('missing').catch(error => error)
  await expect(host.sessions.targets()).rejects.toMatchObject({ code: 'unavailable' })
  resolve(a); await first
  const rows = browserDiagnosticSnapshot().records
  expect(rows).toHaveLength(2)
  expect(rows[0]).toMatchObject({ cause: 'targets_response_invalid', trace_id: 'invoke_' + 'b'.repeat(32) })
  expect(rows[1]).toMatchObject({ cause: 'targets_empty', trace_id: 'invoke_' + 'a'.repeat(32) })
})
it('resolves the reviewed binding before opening its exact terminal options', async () => {
  const host = make()
  const selected = await host.sessions.resolveTarget('console')
  expect(selected).toEqual(target)
  const task = host.sessions.open({ ...request, device_id: selected.deviceId,
    provider_id: selected.providerId, capability_id: selected.capabilityIds[0]!,
    access_mode: selected.accessMode, options: { cols: selected.options.cols, rows: selected.options.rows } })
  await vi.waitFor(() => expect(Socket.instances).toHaveLength(1))
  expect(send.mock.calls.map(([path]) => String(path).split('?')[0]))
    .toEqual(['/session-host/operations', '/session-host/operations', '/session-host/operations/ticket'])
  const socket = Socket.instances[0]!
  socket.onopen?.()
  socket.receive(JSON.stringify({ op: 'opened', acceptance: { ...request, session_id: SESSION, state: 'active' } }))
  expect((await task).session_id).toBe(SESSION)
  host.dispose()
})
it('buffers bounded early output and waits for an input acknowledgment before the next frame', async () => {
  const { sessions, socket, dispose } = await opened()
  socket.receive(frame(1))
  const output = vi.fn(), closed = vi.fn()
  sessions.observe(SESSION, { onData: output, onClosed: closed })
  expect(new TextDecoder().decode(output.mock.calls[0]![0])).toBe('hello')
  const first = sessions.sendData(SESSION, new Uint8Array(new TextEncoder().encode('one')))
  const second = sessions.sendData(SESSION, new Uint8Array(new TextEncoder().encode('two')))
  await vi.waitFor(() => expect(socket.sent.filter(item => item instanceof Uint8Array)).toHaveLength(1))
  socket.receive(JSON.stringify({ op: 'input_ack', session_id: SESSION, seq: 1 }))
  await first
  await vi.waitFor(() => expect(socket.sent.filter(item => item instanceof Uint8Array)).toHaveLength(2))
  socket.receive(JSON.stringify({ op: 'input_ack', session_id: SESSION, seq: 2 }))
  await second; dispose(); expect(closed).toHaveBeenCalledOnce()
})
it.each(['duplicate', 'foreign', 'oversize', 'header', 'overflow'])('closes on %s output without replay or replacement connection', async fault => {
  const { sessions, socket, dispose } = await opened()
  const output = vi.fn(), closed = vi.fn()
  if (fault !== 'overflow') sessions.observe(SESSION, { onData: output, onClosed: closed })
  if (fault === 'duplicate') { socket.receive(frame(1)); socket.receive(frame(1)) }
  if (fault === 'foreign') socket.receive(frame(1, 'ses_' + 'f'.repeat(32)))
  if (fault === 'oversize') socket.receive(new ArrayBuffer(65537))
  if (fault === 'header') socket.receive(frame(2))
  if (fault === 'overflow') { socket.receive(frame(1, SESSION, 'x'.repeat(65000))); socket.receive(frame(2, SESSION, 'x'.repeat(65000))) }
  expect(socket.close).toHaveBeenCalledOnce()
  expect(Socket.instances).toHaveLength(1)
  expect(output).toHaveBeenCalledTimes(fault === 'duplicate' ? 1 : 0)
  dispose()
})
it('does not retry uncertain ticket dispatch or silently substitute a wider target', async () => {
  const host = make()
  send.mockImplementation(async path => { if (path.endsWith('/ticket')) throw new ApplicationHostError('unconfirmed'); return { session_host_version: 1, targets: [target] } })
  await expect(host.sessions.open(request)).rejects.toThrow()
  await expect(host.sessions.open(request)).rejects.toMatchObject({ code: 'unconfirmed' })
  await expect(host.sessions.open({ ...request, request_id: 'replacement' })).rejects.toMatchObject({ code: 'unconfirmed' })
  expect(send).toHaveBeenCalledTimes(2)
  expect(Socket.instances).toHaveLength(0)
  host.dispose()
})
it('rejects changed options, unreviewed targets and ambiguous binding selection before issuing a ticket', async () => {
  const host = make()
  await expect(host.sessions.open({ ...request, options: { cols: 120, rows: 24 } })).rejects.toThrow()
  send.mockResolvedValue({ session_host_version: 1, targets: [target, { ...target, bindingId: 'other' }] })
  await expect(host.sessions.resolveTarget(DEVICE)).rejects.toThrow()
  expect(send.mock.calls.every(call => !call[0].endsWith('/ticket'))).toBe(true)
  host.dispose()
})
it('disposal closes an in-flight socket and never reconnects it', async () => {
  const host = make(), task = host.sessions.open(request)
  const result = expect(task).rejects.toMatchObject({ code: 'disposed' })
  await vi.waitFor(() => expect(Socket.instances).toHaveLength(1))
  host.dispose(); await result
  expect(Socket.instances[0]!.close).toHaveBeenCalledOnce()
  expect(Socket.instances).toHaveLength(1)
})
it('confirms explicit close only after the server confirms cleanup with a normal close', async () => {
  const host = await opened()
  let done = false
  const close = host.sessions.close(SESSION).then(() => { done = true })
  await Promise.resolve(); expect(done).toBe(false)
  host.socket.onclose?.({ code: 1000 })
  await close; expect(done).toBe(true)
  host.dispose()
})
it('does not call unconfirmed server cleanup a successful disconnect', async () => {
  const host = await opened()
  const close = expect(host.sessions.close(SESSION)).rejects.toMatchObject({ code: 'unconfirmed' })
  host.socket.onclose?.({ code: 1008 })
  await close; host.dispose()
})


it('bounds a cold opening at two minutes, fences the page and never retries it', async () => {
  vi.useFakeTimers()
  const host = make(), task = host.sessions.open(request)
  let settled = false
  const result = task.then(() => ({ code: 'opened' }), error => ({ code: error.code }))
  void result.then(() => { settled = true })
  await vi.advanceTimersByTimeAsync(0)
  expect(Socket.instances).toHaveLength(1)
  const socket = Socket.instances[0]!
  socket.onopen?.()
  await vi.advanceTimersByTimeAsync(10_000)
  expect(settled).toBe(false)
  expect(socket.close).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(109_999)
  expect(settled).toBe(false)
  await vi.advanceTimersByTimeAsync(1)
  expect(await result).toEqual({ code: 'unconfirmed' })
  expect(socket.close).toHaveBeenCalledOnce()
  expect(socket.sent).toEqual([JSON.stringify({ op: 'authenticate', ticket: 't'.repeat(43) })])
  socket.receive(JSON.stringify({ op: 'opened', acceptance: { ...request, session_id: SESSION, state: 'active' } }))
  await expect(host.sessions.open({ ...request, request_id: 'fresh_after_timeout' })).rejects.toMatchObject({ code: 'unconfirmed' })
  expect(Socket.instances).toHaveLength(1)
  expect(send).toHaveBeenCalledTimes(2)
  host.dispose()
})

it('accepts a slow cold opening before the deadline and clears only its opening timer', async () => {
  vi.useFakeTimers()
  const host = make(), task = host.sessions.open(request)
  await vi.advanceTimersByTimeAsync(0)
  const socket = Socket.instances[0]!
  socket.onopen?.()
  await vi.advanceTimersByTimeAsync(119_000)
  socket.receive(JSON.stringify({ op: 'opened', acceptance: { ...request, session_id: SESSION, state: 'active' } }))
  expect((await task).session_id).toBe(SESSION)
  await vi.advanceTimersByTimeAsync(2_000)
  expect(socket.close).not.toHaveBeenCalled()
  expect(Socket.instances).toHaveLength(1)
  host.dispose()
})

it.each(['input', 'control', 'close'])('keeps the %s acknowledgment deadline at ten seconds', async action => {
  vi.useFakeTimers()
  const host = await opened()
  const operation = action === 'input'
    ? host.sessions.sendData(SESSION, new Uint8Array([1]))
    : action === 'control'
      ? host.sessions.control({ session_id: SESSION, control_id: 'resize_1', action: 'resize', arguments: { cols: 99, rows: 31 } })
      : host.sessions.close(SESSION)
  let settled = false
  const result = operation.then(() => ({ code: 'acknowledged' }), error => ({ code: error.code }))
  void result.then(() => { settled = true })
  await vi.advanceTimersByTimeAsync(0)
  const sentOnce = host.socket.sent.length
  await vi.advanceTimersByTimeAsync(9_999)
  expect(settled).toBe(false)
  expect(host.socket.close).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1)
  expect(await result).toEqual({ code: 'unconfirmed' })
  expect(host.socket.close).toHaveBeenCalledOnce()
  expect(host.socket.sent).toHaveLength(sentOnce)
  expect(Socket.instances).toHaveLength(1)
  host.dispose()
})
