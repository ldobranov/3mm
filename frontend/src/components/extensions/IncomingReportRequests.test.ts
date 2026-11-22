import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import IncomingReportRequests from './IncomingReportRequests.vue'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (key: string) => key.split('.').pop() }) }))

const moduleId = 'org.example.receiver'
const base = '/api/v1/installation-peers/applications/' + moduleId + '/incoming-report-requests'
const card = () => ({
  binding_id: 'peer_' + '1'.repeat(32), sender_id: 'inst_' + '2'.repeat(32),
  sender_key_id: '3'.repeat(64), receiver_artifact: '4'.repeat(64), receiver_incarnation: '5'.repeat(32),
  metadata_hash: '6'.repeat(64), consent_revision: 12, generation: 7, intent: 'fleet_status',
  expires_at: new Date(Date.now() + 60_000).toISOString(),
  consent: { consent_version: 1, summary_fields: ['core_version'], node_ids: [], node_fields: [] },
})
const response = (entry: unknown) => ({ data: { module_id: moduleId, requests: [entry], limited: false } })
const mountView = () => mount(IncomingReportRequests, { props: { moduleId } })
function button(view: ReturnType<typeof mountView>, key: string) {
  return view.findAll('button').find(b => b.text().split(' · ')[0] === key)
}
async function act(view: ReturnType<typeof mountView>, key: string) {
  await button(view, key)!.trigger('click'); await flushPromises()
}

describe('receiving application report requests', () => {
  beforeEach(() => { vi.resetAllMocks() })

  it('requires a manual read and review before approving the exact fields and receiver', async () => {
    const entry = card()
    http.get.mockResolvedValue(response(entry))
    http.post.mockResolvedValue({ status: 204, data: { credential: 'must-not-render' } })
    const view = mountView()
    await view.get('summary').trigger('click')
    expect(http.get).not.toHaveBeenCalled()
    await act(view, 'check')
    expect(http.get).toHaveBeenCalledWith(base, { timeout: 10000 })
    expect(button(view, 'approve')).toBeUndefined()
    await act(view, 'review')
    expect(view.text()).toContain('core_version')
    expect(view.text()).toContain(entry.sender_key_id)
    expect(http.post).not.toHaveBeenCalled()
    await act(view, 'approve')
    expect(http.post).toHaveBeenCalledExactlyOnceWith(base + '/' + entry.binding_id + '/approve', {
      expected_generation: 7, expected_metadata_revision: 12, expected_metadata_hash: entry.metadata_hash,
      expected_receiver_artifact: entry.receiver_artifact, expected_receiver_incarnation: entry.receiver_incarnation,
    }, { timeout: 15000 })
    expect(view.get('[role=status]').text()).toBe('approved')
    expect(view.text()).not.toContain('must-not-render')
    expect(button(view, 'approve')).toBeUndefined()
  })

  it.each([
    { receiver_artifact: ['4'.repeat(64)] }, { consent_revision: 0 },
    { consent: { ...card().consent, node_fields: ['role'] } },
    { consent: { ...card().consent, summary_fields: ['unknown'] } },
  ])('does not offer an approval for invalid disclosure', async change => {
    http.get.mockResolvedValue(response({ ...card(), ...change }))
    const view = mountView()
    await act(view, 'check')
    expect(view.get('[role=status]').text()).toBe('unavailable')
    expect(button(view, 'review')).toBeUndefined()
    expect(http.post).not.toHaveBeenCalled()
  })

  it('ignores a response that arrives after switching to a different application', async () => {
    let settle!: (result: ReturnType<typeof response>) => void
    http.get.mockReturnValue(new Promise(resolve => { settle = resolve }))
    const view = mountView()
    await button(view, 'check')!.trigger('click')
    await view.setProps({ moduleId: 'org.example.other' })
    settle(response(card())); await flushPromises()
    expect(button(view, 'review')).toBeUndefined()
    http.get.mockResolvedValue(response(card()))
    await act(view, 'check')
    expect(view.get('[role=status]').text()).toBe('unavailable')
  })

  it('requires a new read after an unconfirmed decision and never retries it', async () => {
    http.get.mockResolvedValue(response(card()))
    http.post.mockRejectedValue(new Error('conflict'))
    const view = mountView()
    await act(view, 'check'); await act(view, 'review'); await act(view, 'approve')
    expect(view.get('[role=status]').text()).toBe('unconfirmed')
    expect(button(view, 'review')).toBeUndefined()
    await act(view, 'check')
    expect(button(view, 'approve')).toBeUndefined()
    expect(http.post).toHaveBeenCalledTimes(1)
  })

  it('does not send an expired decision', async () => {
    http.get.mockResolvedValue(response({ ...card(), expires_at: new Date(0).toISOString() }))
    const view = mountView()
    await act(view, 'check'); await act(view, 'review'); await act(view, 'approve')
    expect(view.get('[role=status]').text()).toBe('expired')
    expect(http.post).not.toHaveBeenCalled()
  })
})
