import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_key: string, fallback: string) => fallback }) }))
import Recent from './RecentHttpFailures.vue'
const trace = 'invoke_' + 'a'.repeat(32)
const row = (id = trace) => ({ trace_id: id, timestamp: 1000, status: 409, method: 'POST',
  route: '/api/v1/application-extensions/{module_id}/operations/{operation_id}', duration_ms: 250,
  stage: 'authority.key_acquire', reason: 'review_key_busy', phase: 'not_dispatched', retryable: false })
const payload = (records: ReturnType<typeof row>[] = []) => ({ status: 'ready', records, dropped: { rate: 0, expired: 0 } })
const wrappers: ReturnType<typeof mount>[] = []
function mountView() { const view = mount(Recent); wrappers.push(view); return view }
beforeEach(() => { vi.clearAllMocks(); http.get.mockResolvedValue({ data: payload() }) })
afterEach(() => { wrappers.splice(0).forEach(view => view.unmount()); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('loads recent failures without starting or polling a diagnostic session', async () => {
  const view = mountView(); await flushPromises()
  expect(http.get).toHaveBeenCalledTimes(1)
  expect(http.get).toHaveBeenCalledWith('/api/v1/diagnostics/failures')
  expect(view.text()).toContain('100 failures for 15 minutes')
  expect(view.text()).toContain('Requests that never reached Core are not included')
  expect(http.post).not.toHaveBeenCalled(); expect(http.delete).not.toHaveBeenCalled()
})

it('groups repetitions but retains each trace and emits the exact selected reference', async () => {
  const other = 'invoke_' + 'b'.repeat(32)
  http.get.mockResolvedValue({ data: payload([row(), row(other)]) })
  const view = mountView(); await flushPromises()
  expect(view.findAll('tbody tr')).toHaveLength(1)
  expect(view.text()).toContain('× 2')
  expect(view.text()).toContain('Application was not dispatched')
  await view.findAll('.trace-link').find(button => button.text().includes(other))!.trigger('click')
  expect(view.emitted('trace')).toEqual([[other]])
  await view.find('input').setValue(other)
  expect(view.findAll('tbody tr')).toHaveLength(1)
  expect(view.text()).not.toContain(trace)
})

it('does not turn a post-dispatch refusal into a retry or an unsent request', async () => {
  http.get.mockResolvedValue({ data: payload([{ ...row(), phase: 'execution_unconfirmed' }]) })
  const view = mountView(); await flushPromises()
  expect(view.text()).toContain('do not resend')
  expect(view.text()).not.toContain('Application was not dispatched')
  expect(http.post).not.toHaveBeenCalled()
})

it('marks stale observations after a busy or denied refresh without exposing server detail', async () => {
  http.get.mockResolvedValueOnce({ data: payload([row()]) })
  const view = mountView(); await flushPromises()
  http.get.mockRejectedValueOnce({ response: { data: { detail: 'password=secret' } } })
  await view.findAll('button').find(button => button.text() === 'Refresh failures')!.trigger('click')
  await flushPromises()
  expect(view.find('[role="alert"]').text()).toContain('Previously loaded rows may be stale')
  expect(view.text()).toContain(trace)
  expect(view.text()).not.toContain('password=secret')
  http.get.mockResolvedValueOnce({ data: { status: 'busy', records: [] } })
  await view.findAll('button').find(button => button.text() === 'Refresh failures')!.trigger('click')
  await flushPromises()
  expect(view.text()).toContain(trace)
})

it('exports the server snapshot without invoking a business operation', async () => {
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const create = vi.fn(() => 'blob:failures'), revoke = vi.fn()
  vi.stubGlobal('URL', { createObjectURL: create, revokeObjectURL: revoke })
  const view = mountView(); await flushPromises()
  http.get.mockResolvedValueOnce({ data: new Blob(['{}']) })
  await view.findAll('button').find(button => button.text() === 'Export recent failures')!.trigger('click')
  await flushPromises()
  expect(http.get).toHaveBeenLastCalledWith('/api/v1/diagnostics/failures/export', { responseType: 'blob' })
  expect(click).toHaveBeenCalled(); expect(revoke).toHaveBeenCalledWith('blob:failures')
  expect(http.post).not.toHaveBeenCalled()
})

it('ignores a response after unmount', async () => {
  let resolve: (value: unknown) => void = () => {}
  http.get.mockImplementation(() => new Promise(done => { resolve = done }))
  const view = mountView(); view.unmount()
  resolve({ data: payload([row()]) }); await flushPromises()
  expect(view.emitted('trace')).toBeUndefined()
  expect(http.post).not.toHaveBeenCalled()
})
