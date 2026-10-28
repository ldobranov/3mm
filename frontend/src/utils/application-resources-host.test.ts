import { afterEach, beforeEach, expect, it, vi, type MockInstance } from 'vitest'
import axios from 'axios'
import { createApplicationHost } from './application-host'
vi.mock('./runtime-config', () => ({getBackendUrl:vi.fn(async () => 'https://core.test')}))
vi.mock('./auth', () => ({getToken:()=>'private-core-token'}))
const hash = 'a'.repeat(64), build = 'b'.repeat(64)
const pkg = {module_id:'org.example.inspector',version:'1.0.0',name:'Inspector',source_sha256:hash,
  built_ui_sha256:build,styles:[],entrypoints:[]}
const entry = {entrypoint_id:'overview',kind:'route' as const,source:'source/Inspector.vue',
  label:{en:'Inspector'},asset_url:'/inspector.js',application_route_id:'overview',application_path:'/overview',application_audience:'administrator' as const}
const info = () => ({host_version:1,module_id:pkg.module_id,active_version:pkg.version,artifact_sha256:hash,
  built_ui_sha256:build,entrypoint_id:'overview',audience:'administrator',features:{operations:true,
    resource_authority:'separate',browser_isolation:false,administration_reads:['resources.inspect']},operations:[]})
const observation = () => ({discovery_version:1,instance_id:'c'.repeat(24),artifact_sha256:hash,
  observed_at:'2026-10-27T12:00:00Z',admission_required:true,resources:[{scope:'command:pulse',
    required:true,declared:true,configured:true,access:'granted',readiness:'unknown',reasons:['runtime_not_observed'],
    provider:null,selected_resource_id:null}]})
let send: MockInstance<typeof axios.request>
beforeEach(() => { send = vi.spyOn(axios,'request').mockImplementation(async c =>
  ({data:c.url?.endsWith('/resources/inspect') ? observation() : info()})) })
afterEach(() => vi.restoreAllMocks())
it('uses an explicitly reviewed admin route and returns only resource metadata',async () => {
  const {host} = createApplicationHost(pkg,entry)
  const value = await host.administration.resources.inspect(['command:pulse'])
  expect(value.resources[0]?.readiness).toBe('unknown')
  const request = send.mock.calls.find(([c])=>c.url?.endsWith('/resources/inspect'))![0]
  expect(request.method).toBe('POST')
  expect(request.data).toEqual({scopes:['command:pulse'],artifact_sha256:hash,built_ui_sha256:build})
  expect(JSON.stringify(value)).not.toContain('private-core-token')
})
it.each([[],['command:pulse','command:pulse'],['../../other'],['x'.repeat(193)]].map(scopes => ({scopes})))('rejects malformed scope batches',async ({scopes}) => {
  await expect(createApplicationHost(pkg,entry).host.administration.resources.inspect(scopes)).rejects.toMatchObject({code:'invalid_request'})
  expect(send).not.toHaveBeenCalled()
})
it('requires the exact current read declaration',async () => {
  send.mockResolvedValue({data:{...info(),features:{...info().features,administration_reads:[]}}})
  await expect(createApplicationHost(pkg,entry).host.administration.resources.inspect(['command:pulse'])).rejects.toMatchObject({code:'access_denied'})
  expect(send.mock.calls.some(([c])=>c.url?.endsWith('/resources/inspect'))).toBe(false)
})
it.each(['artifact','scope','secret','denied','admission'])('rejects uncorrelated or overbroad metadata (%s)',async fault => {
  send.mockImplementation(async c => {
    if (!c.url?.endsWith('/resources/inspect')) return {data:info()}
    const value = observation()
    if (fault==='artifact') value.artifact_sha256 = 'd'.repeat(64)
    if (fault==='scope') value.resources[0]!.scope = 'command:other'
    if (fault==='secret') Object.assign(value.resources[0]!,{credential:'not-public'})
    if (fault==='denied') Object.assign(value.resources[0]!,{access:'required',configured:true})
    if (fault==='admission') value.admission_required = false
    return {data:value}
  })
  await expect(createApplicationHost(pkg,entry).host.administration.resources.inspect(['command:pulse'])).rejects.toMatchObject({code:'unavailable'})
})
it('does not replay a failed resource observation',async () => {
  send.mockImplementation(async c => {
    if (c.url?.endsWith('/resources/inspect')) throw Object.assign(new Error('private'),{isAxiosError:true,response:{status:403}})
    return {data:info()}
  })
  await expect(createApplicationHost(pkg,entry).host.administration.resources.inspect(['command:pulse'])).rejects.toMatchObject({code:'access_denied'})
  expect(send.mock.calls.filter(([c])=>c.url?.endsWith('/resources/inspect'))).toHaveLength(1)
})
