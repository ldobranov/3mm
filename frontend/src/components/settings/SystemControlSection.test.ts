import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ post: vi.fn() }))

vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', () => ({
  useI18n: () => ({ t: (_key: string, fallback: string) => fallback }),
}))

import SystemControlSection from './SystemControlSection.vue'

describe('System control settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    http.post.mockResolvedValue({ data: { status: 'queued' } })
    vi.stubGlobal('confirm', vi.fn(() => true))
    vi.stubGlobal('prompt', vi.fn(() => 'FACTORY RESET'))
  })

  it('queues a fixed restart request after confirmation', async () => {
    const wrapper = mount(SystemControlSection)
    await wrapper.findAll('button')[0].trigger('click')
    await flushPromises()

    expect(window.confirm).toHaveBeenCalled()
    expect(http.post).toHaveBeenCalledWith('/api/v1/system-control/restart', {
      confirmation: 'RESTART',
    })
  })

  it('requires the exact factory-reset phrase before queuing the reset', async () => {
    http.post.mockResolvedValueOnce({ status: 202, data: { status: 'queued', action: 'factory_reset' } })
    const wrapper = mount(SystemControlSection)
    await wrapper.findAll('button')[1].trigger('click')
    await flushPromises()

    expect(window.prompt).toHaveBeenCalled()
    expect(http.post).toHaveBeenCalledWith('/api/v1/system-control/factory-reset', {
      confirmation: 'FACTORY RESET',
    })
    expect(wrapper.get('[role="status"]').text()).toContain('Reset requested')
  })

  it('does not restart when the confirmation is cancelled', async () => {
    vi.stubGlobal('confirm', vi.fn(() => false))
    const wrapper = mount(SystemControlSection)
    await wrapper.findAll('button')[0].trigger('click')
    expect(http.post).not.toHaveBeenCalled()
    expect(wrapper.findAll('button').every(button => !button.attributes('disabled'))).toBe(true)
  })

  it.each(['lost reply', 'wrong receipt'])('does not offer a second reset on %s', async scenario => {
    if (scenario === 'lost reply') http.post.mockRejectedValueOnce(new Error('disconnected'))
    else http.post.mockResolvedValueOnce({ status: 202, data: { status: 'queued', action: 'restart' } })
    const wrapper = mount(SystemControlSection)
    const reset = wrapper.findAll('button')[1]
    await reset.trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('Reset was not confirmed')
    expect(wrapper.get('details').element.open).toBe(true)
    expect(reset.element.disabled).toBe(true)
    await reset.trigger('click')
    expect(http.post).toHaveBeenCalledTimes(1)
  })

  it('distinguishes an explicit refusal from a lost reply', async () => {
    http.post.mockRejectedValueOnce({ response: { status: 403, data: { detail: 'Not permitted' } } })
    const wrapper = mount(SystemControlSection)
    const reset = wrapper.findAll('button')[1]
    await reset.trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toBe('Not permitted')
    expect(reset.element.disabled).toBe(false)
    expect(http.post).toHaveBeenCalledTimes(1)
  })

  it.each([null, 'factory reset'])('does not reset with a cancelled or incorrect phrase (%s)', async phrase => {
    vi.stubGlobal('prompt', vi.fn(() => phrase))
    const wrapper = mount(SystemControlSection)
    await wrapper.findAll('button')[1].trigger('click')
    expect(http.post).not.toHaveBeenCalled()
  })
})
