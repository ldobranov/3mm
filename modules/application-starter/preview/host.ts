// Project-owned UI simulation. Never import the real Core transport or credentials.
import { ApplicationHostError, type ApplicationHost, type ApplicationHostInfo,
  type ApplicationPayload, type ApplicationPresentationInfo } from '@3mm/application-ui/v1'

export function createPreview(info: ApplicationHostInfo) {
  const scenarios = [
    { id: 'normal', label: 'Normal access' },
    { id: 'read_only', label: 'No edit permission / revoked access' },
    { id: 'provider_unavailable', label: 'Provider unavailable' },
    { id: 'access_required', label: 'Resource approval missing' },
    { id: 'unconfirmed', label: 'Save completed, acknowledgement lost' },
    { id: 'conflict', label: 'Another editor changed the saved revision' },
  ]
  let scenario = 'normal', locale = 'en', saved = { text: 'Sample note', revision: 0 }
  const receipts = new Map<string, { payload: string; result: typeof saved }>()
  const listeners = new Set<(info: ApplicationPresentationInfo) => void>()
  const denied = () => { throw new ApplicationHostError('access_denied') }
  const operationAllowed = (id: string) => info.operations.some(op => op.operation_id === id)
    && !(scenario === 'read_only' && ['save_note', 'lookup_save'].includes(id))
  const host: ApplicationHost = {
    // These public-host families are deliberately not simulated by this example.
    get access(): never { throw new ApplicationHostError('unavailable') },
    get delegations(): never { throw new ApplicationHostError('unavailable') },
    get administration(): never { throw new ApplicationHostError('unavailable') },
    get files(): never { throw new ApplicationHostError('unavailable') },
    presentation: { version: 1 as const, getInfo: () => ({ locale }),
      subscribe(listener: (value: ApplicationPresentationInfo) => void) { listeners.add(listener); return () => { listeners.delete(listener) } } },
    async getInfo() { return { ...info, operations: info.operations.filter(op => operationAllowed(op.operation_id)) } },
    async invoke(id: string, payload: ApplicationPayload, options?: { readonly idempotencyKey?: string }): Promise<ApplicationPayload> {
      if (!operationAllowed(id)) return denied()
      if (id === 'read_note') return { ...saved }
      if (id === 'observe_resource') return { state: scenario === 'provider_unavailable' ? 'unavailable'
        : scenario === 'access_required' ? 'access_required' : 'ready' }
      if (id === 'lookup_save') {
        const old = receipts.get(String(payload.request_id))
        return { status: old ? 'found' : 'not_found', revision: old?.result.revision ?? null }
      }
      if (id !== 'save_note' || typeof payload.text !== 'string' || payload.text.length > 200
          || !Number.isSafeInteger(payload.revision) || !/^[a-f0-9]{32}$/.test(options?.idempotencyKey || '')) {
        throw new ApplicationHostError('invalid_request')
      }
      const key = options!.idempotencyKey!, canonical = JSON.stringify({ text: payload.text, revision: payload.revision })
      const old = receipts.get(key)
      if (old) {
        if (old.payload !== canonical) throw new ApplicationHostError('unconfirmed')
        return { ...old.result }
      }
      if (saved.revision !== payload.revision) throw new ApplicationHostError('unconfirmed')
      saved = { text: payload.text, revision: saved.revision + 1 }
      receipts.set(key, { payload: canonical, result: { ...saved } })
      if (scenario === 'unconfirmed') throw new ApplicationHostError('unconfirmed')
      return { ...saved }
    },
  }
  return {
    // This minimal mock exposes only the note's getInfo/invoke/presentation surface.
    host,
    scenarios,
    selectScenario(value: string) {
      if (!scenarios.some(item => item.id === value)) throw new Error('Unknown preview scenario')
      scenario = value
      if (value === 'conflict') saved = { text: 'Changed in another simulated editor', revision: saved.revision + 1 }
    },
    reset() { scenario = 'normal'; saved = { text: 'Sample note', revision: 0 }; receipts.clear() },
    setLocale(value: string) {
      if (!['en', 'bg'].includes(value)) throw new Error('Unsupported preview locale')
      locale = value; listeners.forEach(listener => listener({ locale }))
    },
    dispose() { listeners.clear() },
  }
}
