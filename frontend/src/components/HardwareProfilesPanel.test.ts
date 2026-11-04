import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import HardwareProfilesPanel from './HardwareProfilesPanel.vue'
import { i18n } from '@/utils/i18n'
import english from '@/locales/en.json'
import bulgarian from '../../../modules/language-bg/language-extension.json'
const { inspect, mutate, upload, prepare, ids } = vi.hoisted(() => ({ inspect: vi.fn(), mutate: vi.fn(), upload: vi.fn(), prepare: vi.fn(), ids: vi.fn() }))
vi.mock('@/utils/hardware-profiles', async importOriginal => ({
  ...await importOriginal<typeof import('@/utils/hardware-profiles')>(),
  hardwareProfilesClient: () => ({ inspect, mutate, upload, prepare }), newHardwareRequestId: ids,
}))
const DEVICE = 'dev_'+'a'.repeat(32)
const templates = [{ template_id: 'example.display', name: 'Display driver', simulated: false, fields: [
  { key: 'columns', label: 'Columns', type: 'number' as const, default: 16, min: 1, max: 40 },
  { key: 'rows', label: 'Rows', type: 'select' as const, default: 2, options: [{ value: '2', label: '2' }, { value: '4', label: '4' }] },
  { key: 'address', label: 'Address', type: 'select' as const, default: 39, options: [{ value: '39', label: '0x27' }] },
  { key: 'backlight_active_high', label: 'Backlight', type: 'checkbox' as const, default: true },
] }]
const catalog = () => ({ device_id: DEVICE, approval_supported: true, templates, items: [{ module_id: 'org.example.hardware',
  name: 'Example provider', version: '1.0.0', sha256: 'b'.repeat(64), profile: { schema_version: 1,
    profile_sha256: 'c'.repeat(64), simulated: false, configuration: { bus: 1, address: 39, columns: 20, rows: 2 } },
  installation: null as null | { status: string; enabled: boolean; command_id: string; error: null },
  installed_exact: false, request_id: null as string | null }] })
const panel = () => mount(HardwareProfilesPanel, { props: { deviceId: DEVICE, name: 'Selected device' } })
enableAutoUnmount(afterEach)
beforeEach(async () => {
  inspect.mockReset(); mutate.mockReset(); upload.mockReset(); prepare.mockReset(); ids.mockReset(); sessionStorage.clear()
  inspect.mockResolvedValue(catalog()); ids.mockReturnValue('d'.repeat(32))
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.open = true } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.open = false } })
  await i18n.setLanguage('en', false)
})
describe('reviewed hardware provider installation', () => {
  it('prepares numeric settings without an upload, approval, installation or request ID', async () => {
    const wrapper = panel(); await flushPromises()
    expect(prepare).not.toHaveBeenCalled()
    await wrapper.get('.provider-setup input[type="number"]').setValue('24')
    prepare.mockResolvedValue('b'.repeat(64))
    await wrapper.get('.provider-setup form').trigger('submit'); await flushPromises()
    expect(prepare).toHaveBeenCalledExactlyOnceWith('example.display', {
      columns: 24, rows: 2, address: 39, backlight_active_high: true })
    expect(upload).not.toHaveBeenCalled(); expect(mutate).not.toHaveBeenCalled(); expect(ids).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Nothing was installed or approved')
    await wrapper.get('.review-profile').trigger('click'); await flushPromises()
    expect(wrapper.get('.confirm-profile').attributes('disabled')).toBeDefined()
  })
  it('does not install or retry a refused preparation, and keeps the settings for correction', async () => {
    const wrapper = panel(); await flushPromises()
    prepare.mockRejectedValue(new Error('invalid topology'))
    await wrapper.get('.provider-setup input[type="number"]').setValue('25')
    await wrapper.get('.provider-setup form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('No installation was requested')
    expect(prepare).toHaveBeenCalledTimes(1); expect(mutate).not.toHaveBeenCalled()
    await wrapper.get('.refresh-profiles').trigger('click'); await flushPromises()
    expect((wrapper.get('.provider-setup input[type="number"]').element as HTMLInputElement).value).toBe('25')
    expect(prepare).toHaveBeenCalledTimes(1)
  })
  it('blocks invalid settings and preserves the existing package review path', async () => {
    const wrapper = panel(); await flushPromises()
    await wrapper.get('.provider-setup input[type="number"]').setValue('1.5')
    await wrapper.get('.provider-setup form').trigger('submit'); await flushPromises()
    expect(prepare).not.toHaveBeenCalled(); expect(mutate).not.toHaveBeenCalled()
    expect(wrapper.get('.review-profile').attributes('disabled')).toBeUndefined()
  })
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
    expect(again.get('.prepare-provider').attributes('disabled')).toBeDefined()
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
