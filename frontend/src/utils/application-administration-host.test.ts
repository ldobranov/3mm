import { afterEach, beforeEach, expect, it, vi, type MockInstance } from 'vitest'
import axios from 'axios'
import { createApplicationHost } from './application-host'
import { getBackendUrl } from './runtime-config'

vi.mock('./runtime-config', () => ({ getBackendUrl: vi.fn(async () => 'https://core.test') }))
vi.mock('./auth', () => ({ getToken: () => 'private-core-token' }))
const hash = 'a'.repeat(64), build = 'b'.repeat(64), id = 'dev_' + 'c'.repeat(32)
const pkg = { module_id: 'org.example.inventory', version: '1.0.0', name: 'Inventory',
  source_sha256: hash, built_ui_sha256: build, styles: [], entrypoints: [] }
const entry = { entrypoint_id: 'overview', kind: 'route' as const, source: 'source/Devices.vue',
  label: { en: 'Devices' }, asset_url: '/devices.mjs', application_audience: 'administrator' as const }
const information = () => ({ host_version: 1, module_id: pkg.module_id, active_version: pkg.version,
  artifact_sha256: hash, built_ui_sha256: build, entrypoint_id: entry.entrypoint_id, audience: 'administrator',
  features: { operations: true, resource_authority: 'separate', browser_isolation: false,
    administration_reads: ['devices.list', 'devices.detail'] }, operations: [] })
const item = () => ({ device_id: id, display_name: 'Node', role: 'node', protocol_version: '1.0',
  approved_at: '2026-10-25T00:00:00Z', revoked_at: null, last_seen_at: null, online: false, latest_inventory: null })
let send: MockInstance<typeof axios.request>
beforeEach(() => {
  vi.mocked(getBackendUrl).mockResolvedValue('https://core.test')
  send = vi.spyOn(axios, 'request').mockImplementation(async config => ({ data: config.url?.includes('/devices?')
    ? { items: [item()], total: 1 } : config.url?.includes(`/devices/${id}?`)
      ? { ...item(), modules: [] } : information() }))
})
afterEach(() => vi.restoreAllMocks())

it('uses only bound read routes, pagination and Core-owned credentials', async () => {
  const { host } = createApplicationHost(pkg, entry)
  expect(await host.administration.devices.list({ limit: 10, offset: 20 })).toEqual({ items: [item()], total: 1 })
  expect(await host.administration.devices.detail(id)).toEqual({ ...item(), modules: [] })
  expect(send).toHaveBeenCalledTimes(4)
  for (const [config] of send.mock.calls) {
    expect(config.method).toBe('GET')
    expect(config.url).toContain(`artifact_sha256=${hash}&built_ui_sha256=${build}`)
    expect(config.headers).toEqual({ Authorization: 'Bearer private-core-token' })
  }
  expect(send.mock.calls[1][0].url).toContain('offset=20&limit=10')
  expect(JSON.stringify(host)).not.toContain('private-core-token')
})
it.each([{ limit: 101 }, { offset: -1 }, { limit: NaN }, { offset: 1.1 }])('rejects invalid paging %s before transport', async options => {
  await expect(createApplicationHost(pkg, entry).host.administration.devices.list(options)).rejects.toMatchObject({ code: 'invalid_request' })
  expect(send).not.toHaveBeenCalled()
})
it.each(['../user', '', 'dev_test'])('refuses identity injection %s', async value => {
  await expect(createApplicationHost(pkg, entry).host.administration.devices.detail(value)).rejects.toMatchObject({ code: 'invalid_request' })
  expect(send).not.toHaveBeenCalled()
})
it('does not reuse an earlier allowed declaration', async () => {
  const { host } = createApplicationHost(pkg, entry)
  await host.getInfo()
  send.mockResolvedValue({ data: { ...information(), features: { ...information().features, administration_reads: [] } } })
  await expect(host.administration.devices.list()).rejects.toMatchObject({ code: 'access_denied' })
  expect(send.mock.calls.every(([c]) => !c.url?.includes('/devices?'))).toBe(true)
})
it('rejects reads without a reviewed build, and hosts outside the administrator audience', async () => {
  await expect(createApplicationHost({ ...pkg, built_ui_sha256: undefined }, entry).host.administration.devices.list()).rejects.toMatchObject({ code: 'access_denied' })
  expect(send).not.toHaveBeenCalled()
  send.mockResolvedValue({ data: { ...information(), audience: 'operator' } })
  await expect(createApplicationHost(pkg, { ...entry, application_audience: 'operator' }).host.getInfo()).rejects.toMatchObject({ code: 'unavailable' })
})
it.each([401, 403, 404, 409, undefined])('does not retry a failed read or expose the server body (%s)', async status => {
  send.mockImplementation(async config => {
    if (config.url?.includes('/devices?')) throw Object.assign(new Error('private data'), { isAxiosError: true, response: { status } })
    return { data: information() }
  })
  await expect(createApplicationHost(pkg, entry).host.administration.devices.list()).rejects.toMatchObject({
    code: status === 401 || status === 403 ? 'access_denied' : status === 404 ? 'not_found' : 'unavailable',
  })
  expect(send).toHaveBeenCalledTimes(2)
})
it('rejects a detail for another device and strips unexpected projection fields', async () => {
  send.mockImplementation(async config => ({ data: config.url?.includes('/devices/')
    ? { ...item(), device_id: 'dev_' + 'd'.repeat(32), modules: [], token: 'server-secret' } : information() }))
  await expect(createApplicationHost(pkg, entry).host.administration.devices.detail(id)).rejects.toMatchObject({ code: 'unavailable' })
  send.mockImplementation(async config => ({ data: config.url?.includes('/devices?')
    ? { items: [{ ...item(), token: 'server-secret' }], total: 1, credentials: 'server-secret' } : information() }))
  expect(JSON.stringify(await createApplicationHost(pkg, entry).host.administration.devices.list())).not.toContain('server-secret')
})
it('does not switch origins or keep a disposed read interface alive', async () => {
  const { host, dispose } = createApplicationHost(pkg, entry)
  send.mockImplementation(async () => { vi.mocked(getBackendUrl).mockResolvedValue('https://other.test'); return { data: information() } })
  await expect(host.administration.devices.list()).rejects.toMatchObject({ code: 'unavailable' })
  expect(send).toHaveBeenCalledTimes(1)
  dispose()
  await expect(host.administration.devices.detail(id)).rejects.toMatchObject({ code: 'disposed' })
})

const accepted = (requestId = 'd'.repeat(32)) => ({ request_id: requestId, command_id: 'cmd_' + 'e'.repeat(32), device_id: id, status: 'queued' })
const managementInfo = () => ({ ...information(), features: { ...information().features,
  administration_reads: ['devices.list', 'devices.detail', 'modules.list', 'capabilities.list', 'capabilities.state', 'commands.get'],
  administration_actions: ['modules.install', 'modules.disable', 'capabilities.invoke'] } })
it('binds a single module install to this UI, device, package and durable request identity', async () => {
  send.mockImplementation(async config => ({ data: config.method === 'POST' ? accepted() : managementInfo() }))
  const host = createApplicationHost(pkg, entry).host
  expect(await host.administration.modules.install(id, 'f'.repeat(64), 'd'.repeat(32))).toEqual(accepted())
  expect(send).toHaveBeenCalledTimes(2)
  expect(send.mock.lastCall?.[0].url).toBe(`https://core.test/api/v1/application-extensions/${pkg.module_id}/ui-host/overview/modules/install`)
  expect(send.mock.lastCall?.[0].data).toEqual({ device_id: id, package_sha256: 'f'.repeat(64), request_id: 'd'.repeat(32), artifact_sha256: hash, built_ui_sha256: build })
})
it.each([401, 403, 409, undefined])('never retries an uncertain administrator action (%s)', async status => {
  send.mockImplementation(async config => {
    if (config.method === 'POST') throw Object.assign(new Error('private response'), { isAxiosError: true, response: { status } })
    return { data: managementInfo() }
  })
  await expect(createApplicationHost(pkg, entry).host.administration.modules.install(id, 'f'.repeat(64), 'd'.repeat(32)))
    .rejects.toMatchObject({ code: status === 401 || status === 403 ? 'access_denied' : 'unconfirmed' })
  expect(send.mock.calls.filter(([c]) => c.method === 'POST')).toHaveLength(1)
})
it('does not allow actions from a read-only route or guess a successful malformed reply', async () => {
  send.mockResolvedValue({ data: information() })
  const host = createApplicationHost(pkg, entry).host
  await expect(host.administration.modules.disable(id, 'org.example.sensor', 'd'.repeat(32))).rejects.toMatchObject({ code: 'access_denied' })
  expect(send).toHaveBeenCalledTimes(1)
  send.mockImplementation(async config => ({ data: config.method === 'POST' ? { command_id: 'foreign' } : managementInfo() }))
  await expect(host.administration.modules.disable(id, 'org.example.sensor', 'd'.repeat(32))).rejects.toMatchObject({ code: 'unconfirmed' })
  expect(send.mock.calls.filter(([c]) => c.method === 'POST')).toHaveLength(1)
})
it('captures capability arguments before asynchronous preflight and checks status using GET only', async () => {
  send.mockImplementation(async config => ({ data: config.method === 'POST' ? accepted() : config.url?.includes('/commands/')
    ? { ...accepted(), command_type: 'capability.invoke', created_at: 'now', expires_at: 'later', result: null, error: null } : managementInfo() }))
  const host = createApplicationHost(pkg, entry).host
  const invocation = { capability_id: 'org.example.output', provider_type: 'agent_module', provider_id: 'org.example.provider',
    declaration_digest: 'a'.repeat(64), contract_version: '1.0', action: 'set', arguments: { channel: 'one', value: true } }
  const task = host.administration.capabilities.invoke(id, invocation, 'd'.repeat(32))
  invocation.arguments.value = false
  await task
  expect(send.mock.lastCall?.[0].data).toMatchObject({ arguments: { value: true } })
  expect((await host.administration.commands.get('d'.repeat(32))).status).toBe('queued')
  expect(send.mock.lastCall?.[0].method).toBe('GET')
})
