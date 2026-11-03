import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import HardwareProfilesPanel from './HardwareProfilesPanel.vue'
import { i18n } from '@/utils/i18n'
import english from '@/locales/en.json'
import bulgarian from '../../../modules/language-bg/language-extension.json'
const { inspect, mutate, upload, ids } = vi.hoisted(() => ({ inspect: vi.fn(), mutate: vi.fn(), upload: vi.fn(), ids: vi.fn() }))
vi.mock('@/utils/hardware-profiles', () => ({ hardwareProfilesClient: () => ({ inspect, mutate, upload }), newHardwareRequestId: ids }))
const DEVICE = 'dev_'+'a'.repeat(32)
const catalog = () => ({ device_id: DEVICE, approval_supported: true, items: [{ module_id: 'org.example.hardware',
  name: 'Example provider', version: '1.0.0', sha256: 'b'.repeat(64), profile: { schema_version: 1,
    profile_sha256: 'c'.repeat(64), simulated: false, configuration: { bus: 1, address: 39, columns: 20, rows: 2 } },
  installation: null as null | { status: string; enabled: boolean; command_id: string; error: null },
  installed_exact: false, request_id: null as string | null }] })
const panel = () => mount(HardwareProfilesPanel, { props: { deviceId: DEVICE, name: 'Selected device' } })
enableAutoUnmount(afterEach)
beforeEach(async () => {
  inspect.mockReset(); mutate.mockReset(); upload.mockReset(); ids.mockReset(); sessionStorage.clear()
  inspect.mockResolvedValue(catalog()); ids.mockReturnValue('d'.repeat(32))
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.open = true } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.open = false } })
  await i18n.setLanguage('en', false)
})
describe('reviewed hardware provider installation', () => {
  it('starts read-only and requires an explicit review with exact hashes and acknowledgment', async () => {
    const wrapper = panel(); await flushPromises()
    expect(mutate).not.toHaveBeenCalled()
    await wrapper.get('.review-profile').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('b'.repeat(64)); expect(wrapper.text()).toContain('c'.repeat(64))
    expect(wrapper.text()).toContain('No test frame is sent')
    expect(wrapper.get('.confirm-profile').attributes('disabled')).toBeDefined()
    await wrapper.get('.acknowledge input').setValue(true)
    const queued = catalog(); queued.items[0]!.request_id = 'd'.repeat(32)
    queued.items[0]!.installed_exact = true
    queued.items[0]!.installation = { status: 'queued', enabled: true, command_id: 'cmd_test', error: null }
    mutate.mockResolvedValue(undefined); inspect.mockResolvedValue(queued)
    await wrapper.get('.confirm-profile').trigger('click'); await flushPromises()
    expect(mutate).toHaveBeenCalledTimes(1)
    expect(mutate.mock.calls[0]![0]).toBe('install')
    expect(wrapper.get('.review-profile').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('queued')
  })
  it('does not fabricate consent or repeat installation after a lost acknowledgment or remount', async () => {
    const wrapper = panel(); await flushPromises()
    mutate.mockRejectedValue(new Error('lost'))
    await wrapper.get('.review-profile').trigger('click'); await flushPromises()
    await wrapper.get('.acknowledge input').setValue(true)
    await wrapper.get('.confirm-profile').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('do not repeat')
    expect(wrapper.get('.review-profile').attributes('disabled')).toBeDefined()
    wrapper.unmount()
    const again = panel(); await flushPromises()
    expect(again.get('.review-profile').attributes('disabled')).toBeDefined()
    expect(mutate).toHaveBeenCalledTimes(1)
  })
  it('fences older Agents without advertised approval support', async () => {
    inspect.mockResolvedValue({ ...catalog(), approval_supported: false })
    const wrapper = panel(); await flushPromises()
    expect(wrapper.text()).toContain('Update Agent')
    expect(wrapper.get('.review-profile').attributes('disabled')).toBeDefined()
    expect(mutate).not.toHaveBeenCalled()
  })
  it('requires a separate confirmation to disable an installed provider', async () => {
    const active = catalog(); active.items[0]!.installed_exact = true
    active.items[0]!.installation = { status: 'succeeded', enabled: true, command_id: 'cmd_test', error: null }
    inspect.mockResolvedValue(active)
    const wrapper = panel(); await flushPromises()
    await wrapper.get('.disable-profile').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('may retain its last contents')
    expect(wrapper.get('.confirm-profile').attributes('disabled')).toBeDefined()
    await wrapper.get('.acknowledge input').setValue(true)
    await wrapper.get('.confirm-profile').trigger('click'); await flushPromises()
    expect(mutate).toHaveBeenCalledTimes(1); expect(mutate.mock.calls[0]![0]).toBe('disable')
  })
  it('delivers matching BG keys without granting or executing anything on a language switch', async () => {
    expect(Object.keys(bulgarian.frontend.hardwareProfiles).sort()).toEqual(Object.keys(english.hardwareProfiles).sort())
    const wrapper = panel(); await flushPromises()
    i18n.addTranslations('bg', bulgarian.frontend)
    const loader = vi.spyOn(i18n, 'loadTranslations').mockResolvedValue(undefined)
    await i18n.setLanguage('bg', false); await flushPromises()
    expect(wrapper.text()).toContain('Хардуерни доставчици')
    expect(mutate).not.toHaveBeenCalled(); expect(upload).not.toHaveBeenCalled()
    await i18n.setLanguage('en', false); loader.mockRestore()
  })
})
