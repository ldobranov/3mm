// Browser observations are untrusted metadata, not Core receipts or authority.
// No URLs, bodies, headers (apart from a validated trace), exception text or disk.
export type BrowserOperation = 'core.request' | 'application.request' | 'session.targets' | 'session.ticket' | 'session.stream'
export const BROWSER_STAGES = ['host.context', 'host.binding', 'host.request', 'host.response', 'host.features', 'host.operations', 'host.identity',
  'session.ui', 'session.targets.request', 'session.targets.response', 'session.resolve', 'session.request',
  'session.ticket.request', 'session.ticket.response', 'session.socket', 'session.opening', 'session.stream'] as const
export type BrowserStage = typeof BROWSER_STAGES[number]
export const BROWSER_CAUSES = {
  host_context_missing: 'The application host was not provided to this component.',
  host_binding_invalid: 'The application UI binding was rejected locally.',
  host_response_mismatch: 'The received host description does not match this UI.',
  host_features_invalid: 'The received host features were rejected locally.',
  host_operations_invalid: 'The received operation list was rejected locally.',
  host_identity_changed: 'The browser connection or account changed during the check.',
  ui_build_missing: 'The session adapter has no compiled UI identity.',
  targets_response_invalid: 'The received session target list is invalid.',
  target_schema_invalid: 'A received session target is invalid.',
  target_binding_duplicate: 'The received list repeats a session binding.',
  targets_empty: 'Core returned an empty session target list; inspect the matching Core discovery checks.',
  target_not_found: 'No target matched the requested binding or device.',
  target_ambiguous: 'More than one target matched the requested binding or device.',
  session_request_invalid: 'The session request was rejected before ticket dispatch.',
  session_request_mismatch: 'The request does not match one available reviewed target.',
  session_recovery_required: 'An earlier session outcome requires review.',
  ticket_response_invalid: 'The received session ticket response is invalid.',
  socket_backend_unset: 'The browser adapter refused its current backend configuration.',
  socket_audience_denied: 'This UI audience cannot open a session socket.',
  socket_url_invalid: 'The browser adapter rejected its session socket address.',
  socket_construction_failed: 'The browser could not construct the session socket.',
  session_protocol_invalid: 'A received session message was rejected locally.',
  session_callback_failed: 'The application callback could not consume the received session data.',
  session_outcome_unconfirmed: 'The browser did not confirm the original session outcome.',
} as const
export type BrowserCause = keyof typeof BROWSER_CAUSES
export type BrowserFailureDetail = { stage: BrowserStage; cause?: BrowserCause; last_passed_stage?: BrowserStage;
  trace_id?: string; response_observed?: boolean }
type BrowserFailure = { case_id: string; source: 'browser_observation'; trace_id: string | null;
  operation: BrowserOperation; reason: 'transport_unavailable' | 'deadline_exceeded' | 'http_refused' | 'client_rejected';
  stage: BrowserStage | null; cause: BrowserCause | null; last_passed_stage: BrowserStage | null; response_observed: boolean;
  status: number | null; first_timestamp: number; timestamp: number; occurrences: number; execution: 'unknown' }
const TRACE = /^(invoke|platform)_[0-9a-f]{32}$/
const OPERATIONS = new Set<BrowserOperation>(['core.request', 'application.request', 'session.targets', 'session.ticket', 'session.stream'])
const MAX = 100, TTL = 900_000
let sequence = 0
let epoch = newId(), dropped = 0
const rows: BrowserFailure[] = []
let observed = new WeakSet<object>()
const reference = (value: unknown): value is object => value !== null && (typeof value === 'object' || typeof value === 'function')
// Preserve the first boundary when an HTTP error is wrapped for the public API.
export function inheritBrowserFailure<T extends object>(original: unknown, wrapped: T): T {
  if (reference(original) && observed.has(original)) observed.add(wrapped)
  return wrapped
}
function newId() {
  const bytes = new Uint8Array(16)
  try {
    globalThis.crypto.getRandomValues(bytes)
    return 'browser_' + Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
  } catch {
    // A diagnostic identifier is never a credential or an idempotency key.
    return 'browser_' + Date.now().toString(16).padStart(16, '0') + (++sequence).toString(16).padStart(16, '0')
  }
}
function expire(now: number) { while (rows.length && now - rows[0]!.timestamp * 1000 >= TTL) { rows.shift(); dropped++ } }
export function serverTrace(error: any): string | undefined {
  const value = error?.response?.headers?.['x-3mm-trace-id'] ?? error?.requestId
  return typeof value === 'string' && TRACE.test(value) ? value : undefined
}
export function applicationDiagnosticOperation(path: string): BrowserOperation {
  const route = path.split('?')[0] || ''
  return route.startsWith('/session-host/') ? route.endsWith('/ticket') ? 'session.ticket'
    : route.endsWith('/ws') ? 'session.stream' : 'session.targets' : 'application.request'
}
export function recordBrowserFailure(error: any, operation: BrowserOperation = 'core.request', detail?: BrowserFailureDetail) {
  try {
    if (!OPERATIONS.has(operation) || error?.code === 'ERR_CANCELED' || error?.code === 'disposed') return
    if (reference(error) && observed.has(error)) return
    const now = Date.now(); expire(now)
    const status = Number.isInteger(error?.response?.status) && error.response.status >= 400 && error.response.status <= 599
      ? error.response.status as number : null
    const trace = serverTrace(error) || serverTrace({ requestId: detail?.trace_id }) || null
    const stage = detail && BROWSER_STAGES.includes(detail.stage) ? detail.stage : null
    const cause = typeof detail?.cause === 'string' && Object.prototype.hasOwnProperty.call(BROWSER_CAUSES, detail.cause) ? detail.cause : null
    const last = detail?.last_passed_stage && BROWSER_STAGES.includes(detail.last_passed_stage) ? detail.last_passed_stage : null
    const response = detail?.response_observed === true || status !== null
    const reason = status ? 'http_refused' : ['ECONNABORTED', 'ETIMEDOUT'].includes(error?.code) ? 'deadline_exceeded'
      : ['ERR_NETWORK', 'ECONNREFUSED'].includes(error?.code) ? 'transport_unavailable' : 'client_rejected'
    // Group repetitions in a short window; keep unrelated causes visible.
    const index = rows.findIndex(row => row.operation === operation && row.reason === reason && row.status === status
      && row.stage === stage && row.cause === cause && row.last_passed_stage === last && row.response_observed === response
      && now - row.timestamp * 1000 < 30_000)
    const old = index < 0 ? undefined : rows.splice(index, 1)[0]
    rows.push({ case_id: newId(), source: 'browser_observation', trace_id: trace, operation, reason, status,
      stage, cause, last_passed_stage: last, response_observed: response,
      first_timestamp: old?.first_timestamp ?? now / 1000, timestamp: now / 1000,
      occurrences: Math.min(Number.MAX_SAFE_INTEGER, (old?.occurrences || 0) + 1), execution: 'unknown' })
    if (rows.length > MAX) { rows.shift(); dropped++ }
    if (reference(error)) observed.add(error)
  } catch { /* Optional diagnostics must not alter the original operation. */ }
}
export function browserDiagnosticSnapshot() {
  expire(Date.now())
  return { schema_version: 1, source: 'browser_observation', page_epoch: epoch,
    status: 'collected', retention_seconds: TTL / 1000, max_records: MAX, dropped,
    records: rows.map(row => ({ ...row })),
    limitations: ['Client observations are not authenticated Core outcomes.',
      'Page reload or logout clears browser history.', 'Network failure does not prove that Core never received a request.'] }
}
export function clearBrowserDiagnostics() { rows.length = 0; dropped = 0; epoch = newId(); observed = new WeakSet() }
