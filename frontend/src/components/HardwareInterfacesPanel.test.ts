import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import HardwareInterfacesPanel from './HardwareInterfacesPanel.vue'
import { i18n } from '@/utils/i18n'
import english from '@/locales/en.json'
import bulgarian from '../../../modules/language-bg/language-extension.json'

const { inspect, mutate, ids } = vi.hoisted(() => ({ inspect: vi.fn(), mutate: vi.fn(), ids: vi.fn() }))
vi.mock('@/utils/hardware-interfaces', () => ({ hardwareClient: () => ({ inspect, mutate }), newHardwareRequestId: ids }))
const DEVICE = 'dev_'+'a'.repeat(32)
const snapshot = () => ({ device_id: DEVICE, supported: true, reason: null, revision: 'c'.repeat(64),
  can_enable: true, configured: false, ready: false, changes: ['/boot/firmware/config.txt'], operation: null,
  live: { adapter_present: false, device_node_present: false, agent_running: true, agent_access: false } })
const pending = () => ({ ...snapshot(), can_enable: false, configured: true, reboot_required: true,
  operation: { request_id: 'b'.repeat(32), state: 'pending_reboot', restart_request_id: null, restart_state: null } })
const panel = () => mount(HardwareInterfacesPanel, { props: { deviceId: DEVICE, name: 'Test device' } })
enableAutoUnmount(afterEach)
beforeEach(async () => {
  inspect.mockReset(); mutate.mockReset(); ids.mockReset()
  sessionStorage.clear(); ids.mockReturnValue('b'.repeat(32)); inspect.mockResolvedValue(snapshot())
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.open = true } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.open = false } })
  await i18n.setLanguage('en', false)
})

describe('reviewed I²C and separate restart', () => {
  it('opens read-only, requires acknowledgment, then shows pending reboot without restarting', async () => {
    const wrapper = panel(); await flushPromises()
    expect(mutate).not.toHaveBeenCalled()
    await wrapper.get('.enable-i2c').trigger('click'); await flushPromises()
    expect(wrapper.get('.confirm-hardware').attributes('disabled')).toBeDefined()
    await wrapper.get('.acknowledgment input').setValue(true)
    mutate.mockResolvedValue(undefined); inspect.mockResolvedValue(pending())
    await wrapper.get('.confirm-hardware').trigger('click'); await flushPromises()
    expect(mutate).toHaveBeenCalledTimes(1)
    expect(mutate.mock.calls[0]![0]).toBe('enable')
    expect(wrapper.text()).toContain('Configured — restart required')
    expect(wrapper.find('.restart-i2c').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('I²C ready')
  })
  it('requires a new explicit restart confirmation, never a side effect of refresh', async () => {
    inspect.mockResolvedValue(pending())
    const wrapper = panel(); await flushPromises()
    await wrapper.get('.refresh-hardware').trigger('click'); await flushPromises()
    expect(mutate).not.toHaveBeenCalled()
    await wrapper.get('.restart-i2c').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('local workloads will briefly be unavailable')
    await wrapper.get('.acknowledgment input').setValue(true)
    ids.mockReturnValue('d'.repeat(32)); mutate.mockResolvedValue(undefined)
    inspect.mockResolvedValue({ ...pending(), operation: { ...pending().operation,
      restart_request_id: 'd'.repeat(32), restart_state: 'requested' } })
    await wrapper.get('.confirm-hardware').trigger('click'); await flushPromises()
    expect(mutate.mock.calls[0]![0]).toBe('restart')
    expect(wrapper.find('.restart-i2c').exists()).toBe(false)
  })
  it('preserves a lost operation ID across remount and never creates a retry', async () => {
    const wrapper = panel(); await flushPromises()
    mutate.mockRejectedValue(new Error('lost acknowledgment'))
    await wrapper.get('.enable-i2c').trigger('click'); await flushPromises()
    await wrapper.get('.acknowledgment input').setValue(true)
    await wrapper.get('.confirm-hardware').trigger('click'); await flushPromises()
    expect(wrapper.get('.enable-i2c').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('do not resubmit')
    expect(sessionStorage.getItem('hardware-request:'+DEVICE)).toBe('b'.repeat(32))
    wrapper.unmount()
    const again = panel(); await flushPromises()
    expect(again.get('.enable-i2c').attributes('disabled')).toBeDefined()
    expect(mutate).toHaveBeenCalledTimes(1)
  })
  it('never offers local enable/reboot for a remote or unsupported target', async () => {
    inspect.mockResolvedValue({ device_id: DEVICE, supported: false, can_enable: false,
      reason: 'remote_device_unsupported', operation: null })
    const wrapper = panel(); await flushPromises()
    expect(wrapper.text()).toContain('not supported')
    expect(wrapper.find('.enable-i2c').exists()).toBe(false)
    expect(wrapper.find('.restart-i2c').exists()).toBe(false)
    expect(mutate).not.toHaveBeenCalled()
  })
  it('has complete BG labels and switches presentation without an operation', async () => {
    expect(Object.keys(bulgarian.frontend.hardwareInterfaces).sort()).toEqual(Object.keys(english.hardwareInterfaces).sort())
    inspect.mockResolvedValue(pending())
    const wrapper = panel(); await flushPromises()
    i18n.addTranslations('bg', bulgarian.frontend)
    // Existing i18n loading reads language packs; avoid a network fixture here.
    const loader = vi.spyOn(i18n, 'loadTranslations').mockResolvedValue(undefined)
    await i18n.setLanguage('bg', false); await flushPromises()
    expect(wrapper.text()).toContain('Конфигурирано — изисква рестарт')
    expect(mutate).not.toHaveBeenCalled()
    await i18n.setLanguage('en', false); loader.mockRestore()
  })
})
