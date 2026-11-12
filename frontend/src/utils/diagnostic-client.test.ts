import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { browserDiagnosticSnapshot, clearBrowserDiagnostics, inheritBrowserFailure, recordBrowserFailure, serverTrace } from './diagnostic-client'
beforeEach(() => { vi.useFakeTimers(); clearBrowserDiagnostics() })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })
it('retains only closed metadata and a validated server reference, never URL/body/token/error text', () => {
  recordBrowserFailure({ code: 'ERR_NETWORK', message: 'password=SECRET', config: { url: 'https://SECRET', data: 'SECRET' },
    response: { status: 403, data: 'SECRET', headers: { authorization: 'SECRET', 'x-3mm-trace-id': 'invoke_' + 'a'.repeat(32) } } }, 'session.ticket')
  const value = browserDiagnosticSnapshot()
  expect(value.records[0]).toMatchObject({ source: 'browser_observation', operation: 'session.ticket', status: 403,
    trace_id: 'invoke_' + 'a'.repeat(32), execution: 'unknown' })
  expect(JSON.stringify(value)).not.toContain('SECRET')
  expect(serverTrace({ requestId: 'password=SECRET' })).toBeUndefined()
})
it('groups repeated failures, bounds unrelated groups and expires them without network or disk', () => {
  recordBrowserFailure({ code: 'ERR_NETWORK' }); recordBrowserFailure({ code: 'ERR_NETWORK' })
  expect(browserDiagnosticSnapshot().records).toHaveLength(1)
  expect(browserDiagnosticSnapshot().records[0]!.occurrences).toBe(2)
  for (let index = 0; index < 120; index++) { vi.advanceTimersByTime(31_000); recordBrowserFailure({ code: 'ERR_NETWORK' }) }
  expect(browserDiagnosticSnapshot().records.length).toBeLessThanOrEqual(100)
  vi.advanceTimersByTime(900_000)
  expect(browserDiagnosticSnapshot().records).toHaveLength(0)
})
it('ignores disposal and resets history at logout', () => {
  recordBrowserFailure({ code: 'ERR_CANCELED' }); expect(browserDiagnosticSnapshot().records).toHaveLength(0)
  recordBrowserFailure({ code: 'ECONNABORTED' })
  expect(browserDiagnosticSnapshot().records[0]!.reason).toBe('deadline_exceeded')
  const epoch = browserDiagnosticSnapshot().page_epoch
  clearBrowserDiagnostics()
  expect(browserDiagnosticSnapshot().page_epoch).not.toBe(epoch)
  expect(browserDiagnosticSnapshot().records).toHaveLength(0)
})
it('does not let an absent crypto implementation break diagnostic collection', () => {
  vi.stubGlobal('crypto', undefined)
  expect(() => recordBrowserFailure({ code: 'ERR_NETWORK' })).not.toThrow()
  expect(browserDiagnosticSnapshot().records).toHaveLength(1)
})
it('keeps distinct local causes and discards arbitrary diagnostic labels and identifiers', () => {
  recordBrowserFailure(new Error('SECRET'), 'session.targets', { stage: 'session.resolve', cause: 'target_not_found',
    last_passed_stage: 'session.targets.response', response_observed: true, trace_id: 'invoke_' + 'a'.repeat(32) })
  recordBrowserFailure({}, 'session.targets', { stage: 'session.resolve', cause: 'target_ambiguous', response_observed: true })
  recordBrowserFailure({}, 'session.targets', { stage: 'SECRET', cause: { secret: 'SECRET', toString: () => 'target_not_found' },
    last_passed_stage: 'SECRET', trace_id: 'SECRET' } as any)
  const rows = browserDiagnosticSnapshot().records
  expect(rows).toHaveLength(3)
  expect(rows[0]).toMatchObject({ stage: 'session.resolve', cause: 'target_not_found', response_observed: true,
    last_passed_stage: 'session.targets.response', execution: 'unknown', trace_id: 'invoke_' + 'a'.repeat(32) })
  expect(rows[2]).toMatchObject({ stage: null, cause: null, last_passed_stage: null, trace_id: null })
  expect(JSON.stringify(rows)).not.toContain('SECRET')
})
it('records the first boundary once when errors bubble or are wrapped, without retaining exception content', () => {
  const original = new Error('SECRET')
  recordBrowserFailure(original, 'session.ticket', { stage: 'session.ticket.request' })
  const wrapped = inheritBrowserFailure(original, new Error('SECRET'))
  recordBrowserFailure(wrapped, 'session.stream', { stage: 'session.socket' })
  recordBrowserFailure(original, 'core.request')
  expect(browserDiagnosticSnapshot().records).toHaveLength(1)
  expect(browserDiagnosticSnapshot().records[0]!.occurrences).toBe(1)
  clearBrowserDiagnostics(); recordBrowserFailure(wrapped)
  expect(browserDiagnosticSnapshot().records).toHaveLength(1)
})
