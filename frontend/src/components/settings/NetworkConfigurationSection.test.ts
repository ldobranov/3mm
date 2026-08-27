import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  setBackendUrlOverride: vi.fn(),
  clearBackendUrlOverride: vi.fn(),
}))

vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', () => ({
  useI18n: () => ({
    t: (_key: string, fallback: string, params?: Record<string, string>) =>
      Object.entries(params || {}).reduce(
        (value, [key, replacement]) => value.replace(`{${key}}`, replacement),
        fallback,
      ),
  }),
}))

import NetworkConfigurationSection from './NetworkConfigurationSection.vue'

const recovery = {
  automatic_setup_enabled: true,
  offline_after_seconds: 300,
  local_link_state: 'connected',
  wifi_connected: true,
  ethernet_connected: false,
  setup_active: false,
  setup_network: '3mm Setup E794',
  setup_url: 'http://10.42.0.1:8895/setup',
  device_hostname: 'rasp-3mm',
  local_url: 'http://rasp-3mm.local',
}

describe('Network recovery settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    http.get.mockImplementation((url: string) => Promise.resolve({
      data: url.includes('/network-recovery/')
        ? recovery
        : { backend_url: 'http://192.168.1.88:8887' },
    }))
    http.put.mockResolvedValue({
      data: { ...recovery, automatic_setup_enabled: false },
    })
    http.post.mockResolvedValue({
      data: {
        status: 'queued',
        setup_network: recovery.setup_network,
        setup_url: recovery.setup_url,
      },
    })
    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  it('shows the default-enabled local-link policy and saves the checkbox', async () => {
    const wrapper = mount(NetworkConfigurationSection)
    await flushPromises()

    const checkbox = wrapper.find('.recovery-toggle input')
    expect((checkbox.element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.text()).toContain('Wi-Fi connected')

    await checkbox.setValue(false)
    await flushPromises()

    expect(http.put).toHaveBeenCalledWith('/api/v1/network-recovery/policy', {
      automatic_setup_enabled: false,
    })
    expect(wrapper.text()).toContain('Manual setup remains available')
  })

  it('requires confirmation before starting the open setup network', async () => {
    const wrapper = mount(NetworkConfigurationSection)
    await flushPromises()

    await wrapper.find('.recovery-button').trigger('click')
    await flushPromises()

    expect(window.confirm).toHaveBeenCalled()
    expect(http.post).toHaveBeenCalledWith('/api/v1/network-recovery/setup', {
      confirmation: 'START SETUP',
    })
    expect(wrapper.text()).toContain('3mm Setup E794')
    expect(wrapper.text()).toContain('10.42.0.1:8895/setup')
  })

  it('offers the working local hostname for the frontend and backend URLs', async () => {
    const wrapper = mount(NetworkConfigurationSection)
    await flushPromises()

    expect(wrapper.find('.local-access-link').attributes('href')).toBe(
      'http://rasp-3mm.local',
    )
    await wrapper.find('.local-access-card button').trigger('click')

    expect((wrapper.find('#backendUrl').element as HTMLInputElement).value).toBe(
      'http://rasp-3mm.local:8887',
    )
    expect((wrapper.find('#frontendUrl').element as HTMLInputElement).value).toBe(
      'http://rasp-3mm.local',
    )
  })
})
