import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CapabilityAdminError, createDeviceCapabilitiesClient, readDeviceProvider } from '@/utils/device-capabilities'
import DeviceCapabilitiesPanel from './DeviceCapabilitiesPanel.vue'
import Devices from '@/views/Devices.vue'

const { request, backendUrl, http } = vi.hoisted(() => ({ request: vi.fn(), backendUrl: vi.fn(),
  http: { get: vi.fn(), post: vi.fn() } }))
vi.mock('axios', () => ({ default: { request, isAxiosError: (e: unknown) => !!e && typeof e === 'object' && 'response' in e } }))
vi.mock('@/utils/runtime-config', () => ({ getBackendUrl: backendUrl }))
vi.mock('@/utils/auth', () => ({ getToken: () => localStorage.getItem('authToken') || '' }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/i18n', () => ({ useI18n: () => ({ t: (_key: string, fallback: string) => fallback }) }))

const DEVICE = 'dev_' + '1'.repeat(32)
const SOURCE = 'adapter.alpha', CAPABILITY = 'example.measurement.v1'
const provider = (extra = {}) => ({ schema_version: 2, device_id: DEVICE, provider_type: 'agent_adapter', provider_id: SOURCE,
  provider_version: '1.0.0', revision: 4, enabled: true, capabilities: [{ capability_id: CAPABILITY }],
  configured_capability_ids: [] as string[], reported_at: '2026-10-28T09:00:00Z', ...extra })
const offer = (extra = {}) => ({ capability_id: CAPABILITY, provider_type: 'agent_adapter', provider_id: SOURCE,
  provider_version: '1.0.0', registered: false, available: false, unavailable_reason: 'not_configured', ...extra })
const props = { deviceId: DEVICE, name: 'Test device' }
let current: ReturnType<typeof provider>, offered: ReturnType<typeof offer>[]
function panel() { return mount(DeviceCapabilitiesPanel, { props }) }
const posts = () => request.mock.calls.map(c => c[0]).filter(c => c.method === 'POST')

enableAutoUnmount(afterEach)
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear(); localStorage.setItem('role', 'admin'); localStorage.setItem('authToken', 'test-token')
  backendUrl.mockResolvedValue('http://core.test'); current = provider(); offered = [offer()]
  request.mockImplementation(async config => {
    if (config.method === 'GET') return { data: config.url.endsWith('/capability-providers') ? [current] : offered }
    current = { ...current, revision: current.revision + 1,
      ...(config.url.endsWith('/configuration') ? { configured_capability_ids: config.data.capability_ids } : { enabled: config.data.enabled }) }
    offered = [offer({ registered: current.enabled && current.configured_capability_ids.length > 0,
      available: current.enabled && current.configured_capability_ids.length > 0,
      unavailable_reason: current.enabled && current.configured_capability_ids.length > 0 ? null : 'not_configured' })]
    return { data: current }
  })
})

describe('owner capability administration', () => {
  it('starts unselected and saves only an explicit choice, then shows actual readiness', async () => {
    const wrapper = panel(); await flushPromises()
    expect(wrapper.text()).toContain('Not selected'); expect(posts()).toEqual([])
    expect((wrapper.get('input').element as HTMLInputElement).checked).toBe(false)
    await wrapper.get('input').setValue(true)
    expect(wrapper.text()).not.toContain('Change confirmed')
    await wrapper.get('.save-selection').trigger('click'); await flushPromises()
    expect(posts()).toHaveLength(1)
    expect(posts()[0]).toMatchObject({ url: `http://core.test/api/v1/devices/${DEVICE}/capability-providers/agent_adapter/${SOURCE}/configuration`,
      data: { expected_revision: 4, capability_ids: [CAPABILITY] }, headers: { Authorization: 'Bearer test-token' } })
    expect(wrapper.text()).toContain('Selected · Ready')
    expect(wrapper.text()).toContain('Applications require separate approval')
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(posts().some(c => c.url.includes('/authority/'))).toBe(false)
    await wrapper.get('.toggle-provider').trigger('click'); await flushPromises()
    expect(posts()[1].data).toEqual({ expected_revision: 5, enabled: false })
    expect(wrapper.text()).toContain('Provider disabled')
    expect((wrapper.get('input').element as HTMLInputElement).checked).toBe(true)
  })

  it.each([409, 403, 'timeout'])('blocks subsequent changes until refresh after %s', async failure => {
    const wrapper = panel(); await flushPromises()
    request.mockRejectedValueOnce(failure === 'timeout' ? new Error('timeout') : { response: { status: failure } })
    await wrapper.get('input').setValue(true); await wrapper.get('.save-selection').trigger('click'); await flushPromises()
    expect(posts()).toHaveLength(1)
    expect(wrapper.get('.save-selection').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.toggle-provider').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    if (failure === 'timeout') expect(wrapper.text()).toContain('could not be confirmed')
    await wrapper.get('.refresh-sources').trigger('click'); await flushPromises()
    expect(posts()).toHaveLength(1)
    expect((wrapper.get('input').element as HTMLInputElement).checked).toBe(false)
    expect(wrapper.get('.toggle-provider').attributes('disabled')).toBeUndefined()
  })

  it('keeps choices separate from stale health and preserves other provider drafts', async () => {
    request.mockImplementation(async config => config.method === 'GET'
      ? { data: config.url.endsWith('/capability-providers') ? [current, provider({ provider_id: 'adapter.beta' })] : [offer({ unavailable_reason: 'health_stale' })] }
      : { data: { ...current, revision: 5, configured_capability_ids: [CAPABILITY] } })
    const wrapper = panel(); await flushPromises()
    expect(wrapper.text()).toContain('Readiness report expired')
    const cards = wrapper.findAll('.provider-card')
    await cards[0]!.get('input').setValue(true); await cards[1]!.get('input').setValue(true)
    await cards[0]!.get('.save-selection').trigger('click'); await flushPromises()
    expect((cards[1]!.get('input').element as HTMLInputElement).checked).toBe(true)
    expect(cards[1]!.get('.save-selection').attributes('disabled')).toBeUndefined()
  })

  it('does not fabricate configuration controls for inventory or module-managed sources', async () => {
    request.mockResolvedValueOnce({ data: [] }).mockResolvedValueOnce({ data: [offer({ provider_type: null, provider_id: null,
      provider_version: null, unavailable_reason: 'inventory_only' })] })
    const wrapper = panel(); await flushPromises()
    expect(wrapper.text()).toContain('Inventory only')
    expect(wrapper.find('input').exists()).toBe(false); expect(wrapper.find('.toggle-provider').exists()).toBe(false)
    expect(posts()).toHaveLength(0)
  })

  it('shows retained withdrawn selections without silently dropping them', async () => {
    current = provider({ capabilities: [], configured_capability_ids: [CAPABILITY] })
    const wrapper = panel(); await flushPromises()
    expect(wrapper.text()).toContain('Previously selected, no longer offered')
    expect(wrapper.get('.save-selection').attributes('disabled')).toBeDefined()
    await wrapper.get('input').setValue(false)
    await wrapper.get('.save-selection').trigger('click'); await flushPromises()
    expect(posts()[0].data.capability_ids).toEqual([])
  })

  it('exposes the editor through the actual Devices page button for the chosen device', async () => {
    http.get.mockImplementation(async (path: string) => ({ data: path.startsWith('/api/v1/devices?')
      ? { items: [{ device_id: DEVICE, display_name: 'Test device', role: 'hub', latest_inventory: null, online: true, last_seen_at: null }] }
      : path.includes('/commands') ? { items: [] } : path.includes('/state')
        ? { desired: { revision: 1 }, reported_revision: 1, synchronized: true } : [] }))
    const wrapper = mount(Devices, { global: { stubs: { FleetPairing: true, DeviceInventorySummary: true } } })
    await flushPromises(); expect(request).not.toHaveBeenCalled()
    await wrapper.get('.capability-settings').trigger('click'); await flushPromises()
    expect(wrapper.findComponent(DeviceCapabilitiesPanel).props('deviceId')).toBe(DEVICE)
    expect(wrapper.text()).toContain(SOURCE)
    await wrapper.get('.capability-choice input').setValue(true)
    await wrapper.get('.save-selection').trigger('click'); await flushPromises()
    expect(posts()).toHaveLength(1)
    expect(wrapper.text()).toContain('Selected · Ready')
  })

  it.each(['registered', 'guest'])('does not fetch or mutate for %s', async role => {
    localStorage.setItem('role', role)
    if (role === 'guest') localStorage.removeItem('authToken')
    const wrapper = panel(); await flushPromises()
    expect(wrapper.text()).toContain('administrator login'); expect(request).not.toHaveBeenCalled()
  })
})

describe('capability admin transport boundaries', () => {
  it('refuses a foreign device or malformed provider and never adopts its authority', async () => {
    expect(() => readDeviceProvider(provider({ device_id: 'dev_' + '2'.repeat(32) }), DEVICE)).toThrow(CapabilityAdminError)
    expect(() => readDeviceProvider(provider({ configured_capability_ids: [CAPABILITY, CAPABILITY] }), DEVICE)).toThrow(CapabilityAdminError)
    expect(() => readDeviceProvider(provider({ revision: true }), DEVICE)).toThrow(CapabilityAdminError)
  })

  it('treats a foreign mutation acknowledgement as unconfirmed without retry', async () => {
    request.mockResolvedValue({ data: provider({ provider_id: 'foreign', revision: 5, configured_capability_ids: [CAPABILITY] }) })
    await expect(createDeviceCapabilitiesClient(DEVICE).configure(readDeviceProvider(current, DEVICE), [CAPABILITY]))
      .rejects.toMatchObject({ code: 'unconfirmed' })
    expect(posts()).toHaveLength(1)
  })

  it('does not send configuration to a different Core after discovery', async () => {
    const client = createDeviceCapabilitiesClient(DEVICE); await client.inspect()
    backendUrl.mockResolvedValue('http://different.test')
    await expect(client.configure(readDeviceProvider(current, DEVICE), [CAPABILITY])).rejects.toMatchObject({ code: 'unavailable' })
    expect(posts()).toHaveLength(0)
  })
})
