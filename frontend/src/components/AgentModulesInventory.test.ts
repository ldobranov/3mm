import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Inventory from './AgentModulesInventory.vue'
const { http } = vi.hoisted(() => ({ http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
vi.mock('@/utils/dynamic-http', () => ({ default: http }))
vi.mock('@/utils/hardware-interfaces', () => ({ newHardwareRequestId: () => 'a'.repeat(32) }))
vi.mock('@/utils/i18n', () => ({
  useI18n: () => ({ t: (_: string, fallback: string) => fallback }),
}))
enableAutoUnmount(afterEach)
const device = 'dev_' + 'b'.repeat(32)
const installed = () => ({
  module_id: 'org.example.provider',
  name: 'LCD provider',
  version: '1.0.0',
  sha256: 'c'.repeat(64),
  kind: 'hardware_provider',
  installations: [
    {
      device_id: device,
      display_name: 'Raspberry',
      status: 'succeeded',
      enabled: true,
      command_id: 'cmd_' + 'd'.repeat(32),
      installed_version: '1.0.0' as string | null,
      error: null,
      desired_version: '1.0.0',
      data_retained: true,
      uninstall_supported: true,
    },
  ],
})
beforeEach(() => {
  vi.resetAllMocks()
  sessionStorage.clear()
  http.get.mockResolvedValue({ data: { items: [installed()] } })
  http.post.mockResolvedValue({ data: { status: 'queued' } })
  http.delete.mockResolvedValue({ data: { status: 'deleted' } })
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
    configurable: true,
    value(this: HTMLDialogElement) {
      this.open = true
    },
  })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', {
    configurable: true,
    value(this: HTMLDialogElement) {
      this.open = false
    },
  })
})
function button(wrapper: ReturnType<typeof mount>, name: string) {
  const found = wrapper.findAll('button').find((b) => b.text() === name)
  if (!found) throw new Error('Missing button: ' + name)
  return found
}
async function showDetails(wrapper: ReturnType<typeof mount>) {
  if (!(wrapper.get('.inventory-disclosure').element as HTMLDetailsElement).open) {
    await wrapper.get('.inventory-summary').trigger('click')
  }
  await wrapper.get('.package-summary').trigger('click')
  await flushPromises()
}
it('shows uploaded packages and device installations without invoking mutations', async () => {
  http.get.mockResolvedValue({
    data: {
      items: [
        installed(),
        { ...installed(), sha256: 'e'.repeat(64), name: 'Uploaded only', installations: [] },
      ],
    },
  })
  const view = mount(Inventory)
  await flushPromises()
  expect((view.get('.inventory-disclosure').element as HTMLDetailsElement).open).toBe(false)
  expect(view.get('.inventory-count').text()).toBe('2')
  await view.get('.inventory-summary').trigger('click')
  expect((view.get('.inventory-disclosure').element as HTMLDetailsElement).open).toBe(true)
  const summary = view.findAll('.package-summary')[0]!
  expect(summary.text()).toContain('LCD provider')
  expect(summary.text()).toContain('Raspberry')
  expect(summary.text()).toContain('succeeded · Enabled')
  expect(summary.text()).not.toContain(installed().module_id)
  expect(summary.text()).not.toContain('Remove completely')
  expect((view.get('.agent-package').element as HTMLDetailsElement).open).toBe(false)
  await summary.trigger('click')
  expect((view.get('.agent-package').element as HTMLDetailsElement).open).toBe(true)
  expect(view.text()).toContain('Hardware provider')
  expect(view.text()).toContain('Raspberry')
  expect(view.text()).toContain('No current device installation references')
  expect(http.post).not.toHaveBeenCalled()
  expect(http.delete).not.toHaveBeenCalled()
})
it('requires review and acknowledgement and preserves a lost removal request across remount', async () => {
  http.post.mockRejectedValue(new Error('ack lost'))
  const view = mount(Inventory)
  await flushPromises()
  await showDetails(view)
  expect(button(view, 'Delete uploaded package').attributes('disabled')).toBeDefined()
  await button(view, 'Remove completely from device').trigger('click')
  await flushPromises()
  expect(view.text()).toContain('c'.repeat(64))
  expect(button(view, 'Confirm removal').attributes('disabled')).toBeDefined()
  await view.get('input[type=checkbox]').setValue(true)
  await button(view, 'Confirm removal').trigger('click')
  await flushPromises()
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(http.post.mock.calls[0]![1]).toMatchObject({
    confirmation: 'org.example.provider',
    request_id: 'a'.repeat(32),
    expected_command_id: installed().installations[0]!.command_id,
  })
  view.unmount()
  const again = mount(Inventory)
  await flushPromises()
  expect((again.get('.inventory-disclosure').element as HTMLDetailsElement).open).toBe(true)
  await showDetails(again)
  expect(button(again, 'Remove completely from device').attributes('disabled')).toBeDefined()
  expect(again.text()).toContain('a'.repeat(32))
  http.get.mockImplementation((url: string) =>
    Promise.resolve({
      data: url.includes('uninstall-requests') ? { status: 'queued' } : { items: [installed()] },
    }),
  )
  await button(again, 'Read original removal outcome').trigger('click')
  await flushPromises()
  expect(http.post).toHaveBeenCalledTimes(1)
  expect(again.text()).toContain('pending or unconfirmed')
})
it('never hides pending/offline rows or enables removal for an old Agent', async () => {
  const item = installed()
  item.installations[0]!.status = 'expired'
  item.installations[0]!.uninstall_supported = false
  http.get.mockResolvedValue({ data: { items: [item] } })
  const view = mount(Inventory)
  await flushPromises()
  await showDetails(view)
  expect(view.text()).toContain('expired')
  expect(view.text()).toContain('Update this Agent')
  expect(button(view, 'Remove completely from device').attributes('disabled')).toBeDefined()
})
it('allows a separate reviewed package deletion only after removal', async () => {
  const item = installed()
  item.installations[0]!.status = 'uninstalled'
  item.installations[0]!.installed_version = null
  item.installations[0]!.data_retained = false
  item.installations[0]!.enabled = false
  http.get.mockResolvedValue({ data: { items: [item] } })
  const view = mount(Inventory)
  await flushPromises()
  await showDetails(view)
  await button(view, 'Delete uploaded package').trigger('click')
  await flushPromises()
  await view.get('input[type=checkbox]').setValue(true)
  await button(view, 'Confirm removal').trigger('click')
  await flushPromises()
  expect(http.delete).toHaveBeenCalledWith('/api/v1/modules/agent-packages/' + item.sha256)
  expect(http.post).not.toHaveBeenCalled()
})
it('opens a failed refresh without dropping previously loaded installations', async () => {
  const view = mount(Inventory)
  await flushPromises()
  await showDetails(view)
  await view.get('.inventory-summary').trigger('click')
  http.get.mockRejectedValueOnce(new Error('unavailable'))
  await (view.vm as unknown as { refresh: () => Promise<void> }).refresh()
  await flushPromises()
  expect((view.get('.inventory-disclosure').element as HTMLDetailsElement).open).toBe(true)
  expect(view.get('[role=alert]').text()).toContain('Previously loaded rows may be stale')
  expect(view.get('.package-summary').text()).toContain('Raspberry')
  expect(view.get('.inventory-count').text()).toBe('1')
  expect(http.post).not.toHaveBeenCalled()
  expect(http.delete).not.toHaveBeenCalled()
})
