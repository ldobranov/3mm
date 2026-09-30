import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import FleetPairing from './FleetPairing.vue'
import http from '@/utils/dynamic-http'

vi.mock('@/utils/dynamic-http', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
const pending = { request_id: 7, device_id: 'dev_123', display_name: 'Zero' }

describe('Fleet pairing', () => {
  beforeEach(() => { vi.useFakeTimers(); vi.mocked(http.get).mockResolvedValue({ data: [pending] }); vi.mocked(http.post).mockResolvedValue({}) })
  afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })

  it('shows the request and approves once, then refreshes and notifies the registry', async () => {
    const wrapper = mount(FleetPairing)
    await flushPromises()
    expect(wrapper.text()).toContain('Zero')
    expect(wrapper.text()).toContain('dev_123')
    vi.mocked(http.get).mockResolvedValue({ data: [] })
    await wrapper.get('.fleet-approve').trigger('click')
    await flushPromises()
    expect(http.post).toHaveBeenCalledWith('/api/v1/pairing/requests/7/approve', undefined, expect.any(Object))
    expect(wrapper.emitted('approved')).toHaveLength(1)
    expect(wrapper.text()).toContain('fleetPairing.approved')
    expect(wrapper.findAll('.fleet-request')).toHaveLength(0)
    wrapper.unmount()
    const calls = vi.mocked(http.get).mock.calls.length
    await vi.advanceTimersByTimeAsync(20000)
    expect(http.get).toHaveBeenCalledTimes(calls)
  })

  it('does not report success when the reply is lost', async () => {
    const wrapper = mount(FleetPairing)
    await flushPromises()
    vi.mocked(http.post).mockRejectedValue(new Error('offline'))
    await wrapper.get('.fleet-approve').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('fleetPairing.failed')
    expect(wrapper.emitted('approved')).toBeUndefined()
    wrapper.unmount()
  })
})
