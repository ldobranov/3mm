import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import axios from 'axios'
import * as publicHost from '../extension-ui/application-v1'
import { createApplicationHost, withApplicationHost } from './application-host'
import { getBackendUrl } from './runtime-config'
import type { CompiledUiPackage, CompiledUiEntrypoint } from './compiled-ui'

vi.mock('./runtime-config', () => ({ getBackendUrl: vi.fn(async () => 'https://api.test') }))
vi.mock('./auth', () => ({ getToken: () => 'core-secret' }))
const pkg: CompiledUiPackage = { module_id: 'org.example.neutral', version: '1.0.0', name: 'Neutral',
  source_sha256: 'a'.repeat(64), styles: [], entrypoints: [] }
const entry = (audience: publicHost.ApplicationAudience = 'operator'): CompiledUiEntrypoint => ({
  entrypoint_id: 'operations', kind: 'route', source: 'source/frontend/Operations.vue',
  label: { en: 'Operations' }, asset_url: '/asset.mjs', application_audience: audience,
})
function info(audience: publicHost.ApplicationAudience = 'operator') {
  return { host_version: 1, module_id: pkg.module_id, active_version: pkg.version,
    artifact_sha256: pkg.source_sha256, entrypoint_id: 'operations', audience,
    features: { operations: true, resource_authority: 'separate', browser_isolation: false },
    operations: [{ operation_id: 'read', kind: 'query', idempotency: 'forbidden' },
      { operation_id: 'write', kind: 'command', idempotency: 'required' }],
  }
}
let send: MockInstance<typeof axios.request>
beforeEach(() => {
  localStorage.setItem('applicationKioskToken', 'kiosk-secret')
  vi.mocked(getBackendUrl).mockResolvedValue('https://api.test')
  send = vi.spyOn(axios, 'request').mockImplementation(async config => ({ data: config.method === 'GET' ? info() : { result: 'ok' } }))
})
afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })

describe('public module-bound application host', () => {
  it('exports no HTTP client, stores, router, credentials or host factory', () => {
    expect(Object.keys(publicHost).sort()).toEqual(['APPLICATION_HOST_VERSION', 'ApplicationHostError', 'applicationHostKey', 'useApplicationHost'])
    expect(Object.keys(createApplicationHost(pkg, entry()).host)).toEqual(['getInfo', 'invoke'])
  })
  it.each(['public', 'kiosk', 'operator', 'administrator'] as const)('uses only %s credentials and audience path', async audience => {
    send.mockImplementation(async config => ({ data: config.method === 'GET' ? info(audience) : { result: 'ok' } }))
    const { host } = createApplicationHost(pkg, entry(audience))
    expect(await host.invoke('read', {})).toEqual({ result: 'ok' })
    const segment = audience === 'administrator' ? '' : `/${audience}`
    expect(send.mock.calls[1][0].url).toBe(`https://api.test/api/v1/application-extensions/${pkg.module_id}${segment}/operations/read`)
    for (const [request] of send.mock.calls) {
      expect(request.headers).toEqual(audience === 'public' ? {} : { Authorization: `Bearer ${audience === 'kiosk' ? 'kiosk-secret' : 'core-secret'}` })
      expect(request.withCredentials).toBe(false)
    }
    expect(send.mock.calls[1][0].data).toMatchObject({ payload: {}, ui_context: {
      host_version: 1, entrypoint_id: 'operations', artifact_sha256: pkg.source_sha256,
    } })
  })
  it('does not leak unexpected server fields and freezes access snapshots', async () => {
    send.mockResolvedValue({ data: { ...info(), token: 'server-secret', configuration: { private: true } } })
    const result = await createApplicationHost(pkg, entry()).host.getInfo()
    expect(JSON.stringify(result)).not.toMatch(/server-secret|configuration/)
    expect(Object.isFrozen(result)).toBe(true)
    expect(Object.isFrozen(result.operations[0])).toBe(true)
  })
  it.each(['module_id', 'artifact_sha256', 'active_version', 'entrypoint_id', 'audience', 'host_version'])('rejects foreign or stale %s', async key => {
    send.mockResolvedValue({ data: { ...info(), [key]: 'foreign' } })
    await expect(createApplicationHost(pkg, entry()).host.invoke('read', {})).rejects.toMatchObject({ code: 'unavailable' })
    expect(send).toHaveBeenCalledTimes(1)
  })
  it.each(['../admin', '/user', 'org.other:read', 'READ'])('rejects operation path injection %s before transport', async id => {
    await expect(createApplicationHost(pkg, entry()).host.invoke(id, {})).rejects.toMatchObject({ code: 'invalid_request' })
    expect(send).not.toHaveBeenCalled()
  })
  it.each([undefined, NaN, Infinity, new Date(), () => 'not-json'])('rejects lossy/non-JSON payload values before transport (%s)', async value => {
    const payload = { value } as unknown as publicHost.ApplicationPayload
    await expect(createApplicationHost(pkg, entry()).host.invoke('read', payload)).rejects.toMatchObject({ code: 'invalid_request' })
    expect(send).not.toHaveBeenCalled()
  })
  it('bounds cyclic and oversized payloads before transport', async () => {
    const payload: publicHost.ApplicationPayload = {}
    payload.loop = payload
    const { host } = createApplicationHost(pkg, entry())
    await expect(host.invoke('read', payload)).rejects.toMatchObject({ code: 'invalid_request' })
    await expect(host.invoke('read', { text: 'я'.repeat(300_000) })).rejects.toMatchObject({ code: 'invalid_request' })
    expect(send).not.toHaveBeenCalled()
  })
  it('requires explicit keys for commands and forbids them for queries', async () => {
    const { host } = createApplicationHost(pkg, entry())
    await expect(host.invoke('write', {})).rejects.toMatchObject({ code: 'invalid_request' })
    await expect(host.invoke('read', {}, { idempotencyKey: 'command-key' })).rejects.toMatchObject({ code: 'invalid_request' })
    await host.invoke('write', {}, { idempotencyKey: 'command-key' })
    expect(send.mock.calls.filter(([c]) => c.method === 'POST')).toHaveLength(1)
    expect(send.mock.lastCall?.[0].data).toMatchObject({ idempotency_key: 'command-key' })
  })
  it.each([401, 403, 409, undefined])('never retries/refreshes/promotes a failed POST (%s)', async status => {
    send.mockImplementation(async config => {
      if (config.method === 'POST') throw Object.assign(new Error('secret backend body'), { isAxiosError: true, response: status ? { status } : undefined })
      return { data: info() }
    })
    await expect(createApplicationHost(pkg, entry()).host.invoke('write', {}, { idempotencyKey: 'request-1' }))
      .rejects.toMatchObject({ code: status === 401 || status === 403 ? 'access_denied' : 'unconfirmed' })
    expect(send).toHaveBeenCalledTimes(2)
  })
  it('refreshes access on every call and does not use a previous allowed snapshot', async () => {
    const { host } = createApplicationHost(pkg, entry())
    await host.getInfo()
    send.mockResolvedValue({ data: { ...info(), operations: [] } })
    await expect(host.invoke('read', {})).rejects.toMatchObject({ code: 'access_denied' })
    expect(send.mock.calls.every(([c]) => c.method === 'GET')).toBe(true)
  })
  it('never switches Core origins between preflight and dispatch', async () => {
    const { host } = createApplicationHost(pkg, entry())
    send.mockImplementation(async () => { vi.mocked(getBackendUrl).mockResolvedValue('https://foreign.test'); return { data: info() } })
    await expect(host.invoke('read', {})).rejects.toMatchObject({ code: 'unavailable' })
    expect(send).toHaveBeenCalledTimes(1)
  })
  it('captures package and payload before asynchronous preflight', async () => {
    const mutable = structuredClone(pkg)
    const payload = { message: 'original' }
    const { host } = createApplicationHost(mutable, entry())
    const task = host.invoke('read', payload)
    payload.message = 'changed'
    mutable.module_id = 'org.other.app'
    await task
    expect(send.mock.lastCall?.[0].url).toContain(pkg.module_id)
    expect(send.mock.lastCall?.[0].data).toMatchObject({ payload: { message: 'original' } })
  })
  it('binds the reviewed build to preflight, public info and exactly one dispatch', async () => {
    const build = 'b'.repeat(64)
    const mutable = { ...pkg, built_ui_sha256: build }
    send.mockImplementation(async config => ({ data: config.method === 'GET'
      ? { ...info(), built_ui_sha256: build } : { result: 'ok' } }))
    const { host } = createApplicationHost(mutable, entry())
    mutable.built_ui_sha256 = 'c'.repeat(64)
    expect((await host.getInfo()).built_ui_sha256).toBe(build)
    await host.invoke('write', {}, { idempotencyKey: 'build-test-0001' })
    expect(send.mock.calls[0][0].url).toContain(`&built_ui_sha256=${build}`)
    expect(send.mock.lastCall?.[0].data).toMatchObject({ ui_context: { built_ui_sha256: build } })
    expect(send.mock.calls.filter(([config]) => config.method === 'POST')).toHaveLength(1)
  })
  it.each([undefined, 'c'.repeat(64)])('refuses a missing or changed build without dispatch (%s)', async build => {
    send.mockResolvedValue({ data: { ...info(), built_ui_sha256: build } })
    await expect(createApplicationHost({ ...pkg, built_ui_sha256: 'b'.repeat(64) }, entry())
      .host.invoke('read', {})).rejects.toMatchObject({ code: 'unavailable' })
    expect(send).toHaveBeenCalledOnce()
    expect(send.mock.calls[0][0].method).toBe('GET')
  })
  it('rejects malformed build identity before any transport', () => {
    expect(() => createApplicationHost({ ...pkg, built_ui_sha256: '../artifact' }, entry()))
      .toThrow(publicHost.ApplicationHostError)
    expect(send).not.toHaveBeenCalled()
  })
  it('unmount aborts pending transport and a retained host cannot dispatch', async () => {
    let captured!: publicHost.ApplicationHost
    const child = defineComponent({ setup() { captured = publicHost.useApplicationHost(); return () => h('p', 'Application') } })
    const wrapper = mount(withApplicationHost(pkg, entry(), child))
    send.mockImplementation(config => new Promise((_resolve, reject) => {
      config.signal?.addEventListener?.('abort', () => reject(new Error('aborted')))
    }))
    const task = captured.getInfo()
    await vi.waitFor(() => expect(send).toHaveBeenCalledOnce())
    wrapper.unmount()
    await expect(task).rejects.toMatchObject({ code: 'disposed' })
    await expect(captured.invoke('read', {})).rejects.toMatchObject({ code: 'disposed' })
    expect(send).toHaveBeenCalledOnce()
  })
})
