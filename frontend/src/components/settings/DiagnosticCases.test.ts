import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_key: string, fallback: string) => fallback }) }))
import Cases from './DiagnosticCases.vue'
import { clearBrowserDiagnostics, recordBrowserFailure } from '@/utils/diagnostic-client'
const trace = 'invoke_' + 'a'.repeat(32)
const payload = () => ({ schema_version: 1, status: 'ready', generated_at: '2026-11-11T20:00:00Z',
  cases: [{ case_id: trace, operation: 'session.ticket', summary: 'This resource has an unfinished session.',
    next_check: 'inspect_session_recovery', next_check_help: 'Read recovery status; do not reconnect.',
    execution: 'not_dispatched', trace_records: [], evidence: { occurrences: 3, trace_ids: [trace],
      timestamp: 1794427200, duration_ms: 10, method: 'POST', route: '/session-host/{entrypoint_id}/ticket',
      stage: 'session.capacity', reason: 'session_binding_busy', status: 403, transport: 'http' } }],
  failure_history: { dropped: { rate: 0 } }, coverage: [{ boundary: 'browser', status: 'not_collected' }],
  limitations: ['History is bounded.'] })
const views: ReturnType<typeof mount>[] = []
function view() { const wrapper = mount(Cases); views.push(wrapper); return wrapper }
beforeEach(() => { vi.clearAllMocks(); clearBrowserDiagnostics(); http.get.mockResolvedValue({ data: payload() }) })
afterEach(() => { views.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks(); vi.unstubAllGlobals() })
it('collects useful 403 evidence through a read-only API without polling or opening a session', async () => {
  const wrapper = view(); await flushPromises()
  expect(http.get).toHaveBeenCalledExactlyOnceWith('/api/v1/diagnostics/cases')
  expect(wrapper.text()).toContain('unfinished session')
  expect(wrapper.text()).toContain('403 · × 3')
  expect(wrapper.text()).toContain('not a replay instruction')
  expect(http.post).not.toHaveBeenCalled()
  await wrapper.find('.case-reference').trigger('click')
  expect(wrapper.emitted('trace')).toEqual([[trace]])
  await wrapper.findAll('button').find(button => button.text().includes('Record next user'))!.trigger('click')
  expect(wrapper.emitted('record')).toEqual([['session.ticket']])
  expect(http.post).not.toHaveBeenCalled()
})
it('includes safe browser-before-Core observations without calling them server receipts', async () => {
  recordBrowserFailure({ code: 'ERR_NETWORK', message: 'password=SECRET' }, 'session.targets')
  const wrapper = view(); await flushPromises()
  expect(wrapper.text()).toContain('Browser observation only')
  expect(wrapper.text()).toContain('does not establish DNS failure')
  expect(wrapper.text()).not.toContain('SECRET')
})
it('shows a handled Core refusal without calling HTTP200 a successful session or changing access', async () => {
  const data = payload()
  Object.assign(data.cases[0]!.evidence, { handled_refusal: true, status: 200, method: 'GET', reason: 'session_permission_denied' })
  http.get.mockResolvedValueOnce({ data })
  const wrapper = view(); await flushPromises()
  expect(wrapper.text()).toContain('http 200')
  expect(wrapper.text()).toContain('HTTP succeeded, but a resource check was refused')
  expect(wrapper.text()).toContain('not a successful session opening')
  expect(http.post).not.toHaveBeenCalled()
})
it('distinguishes local refusal after HTTP success and exposes the first failed and last passed checks', async () => {
  recordBrowserFailure(new Error('SECRET'), 'session.targets', { stage: 'session.resolve', cause: 'target_not_found',
    last_passed_stage: 'session.targets.response', response_observed: true, trace_id: trace })
  const wrapper = view(); await flushPromises()
  const row = wrapper.find('.case-browser')
  expect(row.text()).toContain('No target matched')
  expect(row.text()).toContain('First failed check')
  expect(row.text()).toContain('Last passed check')
  expect(row.text()).toContain('session.targets.response')
  expect(row.text()).toContain('HTTP response received; local check refused')
  expect(row.text()).not.toMatch(/no HTTP response observed|SECRET/)
  await row.find('.case-reference').trigger('click')
  expect(wrapper.emitted('trace')).toEqual([[trace]])
})
it('marks stale or partial results explicitly and never displays caught error payloads', async () => {
  const wrapper = view(); await flushPromises()
  http.get.mockRejectedValueOnce({ response: { data: { detail: 'password=SECRET' } } })
  await wrapper.findAll('button').find(button => button.text() === 'Collect observations')!.trigger('click')
  await flushPromises()
  expect(wrapper.find('[role="alert"]').text()).toContain('may be stale')
  expect(wrapper.text()).toContain(trace); expect(wrapper.text()).not.toContain('SECRET')
})
it('saves the same collected snapshot and browser observations without a second API action', async () => {
  const create = vi.fn(() => 'blob:case'), revoke = vi.fn()
  vi.stubGlobal('URL', { createObjectURL: create, revokeObjectURL: revoke })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const wrapper = view(); await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === 'Save diagnostic bundle')!.trigger('click')
  expect(create).toHaveBeenCalled(); expect(click).toHaveBeenCalled()
  expect(revoke).toHaveBeenCalledWith('blob:case'); expect(http.get).toHaveBeenCalledTimes(1)
})
it('does not treat missing history as success and ignores a late unmounted response', async () => {
  http.get.mockResolvedValueOnce({ data: { ...payload(), status: 'partial', cases: [] } })
  const wrapper = view(); await flushPromises()
  expect(wrapper.text()).toContain('not proof that everything succeeded')
  let resolve: (value: unknown) => void = () => {}
  http.get.mockImplementation(() => new Promise(done => { resolve = done }))
  const late = view(); late.unmount(); resolve({ data: payload() }); await flushPromises()
  expect(late.emitted('trace')).toBeUndefined()
})
