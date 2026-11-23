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
  failure_history: { history_id: 'a'.repeat(32), dropped: { rate: 0 } }, coverage: [{ boundary: 'browser', status: 'not_collected' }],
  limitations: ['History is bounded.'] })
const views: ReturnType<typeof mount>[] = []
it('does not attribute the latest measured delay to an older request ID', async () => {
  const older = 'invoke_' + 'b'.repeat(32)
  const data = payload()
  data.cases[0].evidence.trace_ids.push(older)
  Object.assign(data.cases[0].evidence, { failed_step_ms: 345, last_passed_stage: 'device.credential' })
  http.get.mockResolvedValueOnce({ data })
  const wrapper = view(); await flushPromises()
  await wrapper.get('input').setValue(older)
  expect(wrapper.text()).toContain('not retained for this request')
  expect(wrapper.text()).not.toContain('345 ms')
  expect(wrapper.text()).not.toContain('device.credential')
  await wrapper.get('input').setValue(trace)
  expect(wrapper.text()).toContain('345 ms')
  expect(wrapper.text()).toContain('device.credential')
})
it('requires confirmation, preserves evidence on an uncertain clear and reads fresh state on success', async () => {
  http.get.mockResolvedValue({ data: payload() })
  http.delete.mockRejectedValueOnce(new Error('uncertain'))
  const w = view(); await flushPromises()
  const click = async (label: string) => {
    await w.findAll('button').find(b => b.text() === label)!.trigger('click'); await flushPromises()
  }
  await click('Clear history'); await click('Cancel')
  expect(http.delete).not.toHaveBeenCalled()
  await click('Clear history'); await click('Yes, clear history')
  expect(w.text()).toContain('Clearing was not confirmed')
  expect(w.text()).toContain('This resource has an unfinished session.')
  await click('Collect observations')
  http.delete.mockResolvedValueOnce({ data: { status: 'cleared' } })
  http.get.mockResolvedValueOnce({ data: { ...payload(), cases: [] } })
  await click('Clear history'); await click('Yes, clear history')
  expect(http.delete).toHaveBeenLastCalledWith('/api/v1/diagnostics/cases/history', { params: { history_id: 'a'.repeat(32) } })
  expect(w.text()).not.toContain('This resource has an unfinished session.')
})
function view(recordableOperations = ['session.ticket']) { const wrapper = mount(Cases, {props: {recordableOperations}}); views.push(wrapper); return wrapper }
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
  expect(wrapper.emitted('record')).toEqual([['session.ticket', null]])
  expect(http.post).not.toHaveBeenCalled()
})
it('includes safe browser-before-Core observations without calling them server receipts', async () => {
  recordBrowserFailure({ code: 'ERR_NETWORK', message: 'password=SECRET' }, 'session.targets')
  const wrapper = view(); await flushPromises()
  expect(wrapper.text()).toContain('Browser observation only')
  expect(wrapper.text()).toContain('does not establish DNS failure')
  expect(wrapper.text()).not.toContain('SECRET')
})
it('does not offer an unfiltered recording when the failed operation cannot be recorded', async () => {
  const wrapper = view([]); await flushPromises()
  expect(wrapper.text()).toContain('unfinished session')
  expect(wrapper.text()).toContain('latest occurrence')
  expect(wrapper.text()).not.toContain('Record next user attempt')
  expect(http.post).not.toHaveBeenCalled()
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

it('summarizes repeated reasons in compact mode but preserves all evidence in the download', async () => {
  const data = payload()
  data.status = 'partial'
  const second = structuredClone(data.cases[0]!)
  second.case_id = 'invoke_' + 'f'.repeat(32)
  second.evidence.occurrences = 7
  data.cases.push(second)
  http.get.mockResolvedValueOnce({data})
  const wrapper = mount(Cases, { props: { compact: true } }); views.push(wrapper)
  await flushPromises()
  expect(wrapper.text()).toContain('Recorded Core failures: 10')
  expect(wrapper.text()).toContain('report is incomplete')
  expect(wrapper.findAll('.compact-reason')).toHaveLength(1)
  expect(wrapper.text()).not.toContain(second.case_id)
  const create = vi.fn(() => 'blob:case')
  vi.stubGlobal('URL', { createObjectURL: create, revokeObjectURL: vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  await wrapper.get('.ui-button--primary').trigger('click')
  expect(create).toHaveBeenCalledOnce()
  expect(http.get).toHaveBeenCalledTimes(1)
  await wrapper.setProps({compact:false})
  expect(wrapper.text()).toContain(second.case_id)
  expect(wrapper.findAll('.case-card')).toHaveLength(2)
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
