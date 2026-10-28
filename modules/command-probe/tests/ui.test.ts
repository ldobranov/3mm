import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { applicationHostKey } from '@3mm/application-ui/v1'
import Button from '../source/frontend/Button.vue'

const resource = { access: 'granted', readiness: 'ready', target_device_id: 'dev_' + '3'.repeat(32), provider_id: 'org.example.first' }
const info = { module_id: 'org.3mm.command-probe', operations: ['observe', 'set_output', 'lookup'].map(operation_id => ({ operation_id })) }
const outcome = (request_id: string, status: string, confirmed_value: boolean | null = null) => ({
  request_id, status, confirmed_value, target_device_id: resource.target_device_id,
})
const storageKey = '3mm.command-probe.pending.v1'
let wrappers: ReturnType<typeof mount>[] = []
function setup(implementation?: (name: string, payload: any, options?: any) => any) {
  const invoke = vi.fn(implementation || ((name, _payload, options) => name === 'observe' ? resource : outcome(options?.idempotencyKey, 'queued')))
  const host = { getInfo: vi.fn().mockResolvedValue(info), invoke }
  const wrapper = mount(Button, { global: { provide: { [applicationHostKey as symbol]: host } } })
  wrappers.push(wrapper)
  return { wrapper, host }
}
const button = (wrapper: ReturnType<typeof mount>, label: string) => wrapper.findAll('button').find(b => b.text() === label)!
beforeEach(() => { localStorage.clear(); vi.useFakeTimers() })
afterEach(() => { wrappers.forEach(w => w.unmount()); wrappers = []; vi.restoreAllMocks(); vi.useRealTimers() })

describe('output button through the public host', () => {
  it('saves the exact request before one send and never presents queued work as confirmation', async () => {
    const { wrapper, host } = setup((name, _payload, options) => {
      if (name === 'observe') return resource
      const stored = JSON.parse(localStorage.getItem(storageKey)!)
      expect(stored).toEqual({ request_id: options.idempotencyKey, value: true })
      return outcome(options.idempotencyKey, 'queued')
    })
    await flushPromises()
    await button(wrapper, 'Switch on').trigger('click'); await flushPromises()
    expect(host.invoke.mock.calls.filter(c => c[0] === 'set_output')).toHaveLength(1)
    expect(wrapper.text()).toContain('waiting for device confirmation')
    expect(wrapper.text()).not.toContain('Confirmed by the device')
    expect(button(wrapper, 'Switch off').attributes('disabled')).toBeDefined()
  })
  it('reloads an unresolved request using lookup only, then accepts a confirmed result', async () => {
    const id = 'a'.repeat(32)
    localStorage.setItem(storageKey, JSON.stringify({ request_id: id, value: false }))
    const { wrapper, host } = setup(name => name === 'observe' ? resource : outcome(id, 'succeeded', false))
    await flushPromises()
    expect(host.invoke.mock.calls.map(c => c[0])).toEqual(['observe', 'lookup'])
    expect(wrapper.text()).toContain('Confirmed by the device')
    expect(wrapper.text()).toContain('Off')
    expect(localStorage.getItem(storageKey)).toBeNull()
    expect(button(wrapper, 'Switch on').attributes('disabled')).toBeUndefined()
  })
  it('keeps a lost reply locked and checks its UUID without resending', async () => {
    const { wrapper, host } = setup(name => {
      if (name === 'observe') return resource
      if (name === 'set_output') throw new Error('lost reply')
      return outcome(JSON.parse(localStorage.getItem(storageKey)!).request_id, 'not_found')
    })
    await flushPromises(); await button(wrapper, 'Switch off').trigger('click'); await flushPromises()
    const original = localStorage.getItem(storageKey)
    await button(wrapper, 'Check status').trigger('click'); await flushPromises()
    expect(localStorage.getItem(storageKey)).toBe(original)
    expect(host.invoke.mock.calls.filter(c => c[0] === 'set_output')).toHaveLength(1)
    expect(button(wrapper, 'Switch on').attributes('disabled')).toBeDefined()
    expect(button(wrapper, 'Clear this request').attributes('disabled')).toBeDefined()
    await wrapper.find('input[type=checkbox]').setValue(true)
    await button(wrapper, 'Clear this request').trigger('click')
    expect(localStorage.getItem(storageKey)).toBeNull()
  })
  it('blocks sending when durable browser storage is unavailable', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage denied') })
    const { wrapper, host } = setup(); await flushPromises()
    expect(button(wrapper, 'Switch on').attributes('disabled')).toBeDefined()
    expect(host.invoke.mock.calls.map(c => c[0])).toEqual(['observe'])
    expect(wrapper.text()).toContain('Sending is blocked')
  })
  it('clears stale resource information when current access fails', async () => {
    const { wrapper, host } = setup(); await flushPromises()
    expect(wrapper.text()).toContain(resource.target_device_id)
    host.getInfo.mockRejectedValue(new Error('revoked'))
    await vi.advanceTimersByTimeAsync(3000); await flushPromises()
    expect(wrapper.text()).not.toContain(resource.target_device_id)
    expect(button(wrapper, 'Switch on').attributes('disabled')).toBeDefined()
  })
  it('does not trust a foreign or malformed command receipt', async () => {
    const { wrapper } = setup(name => name === 'observe' ? resource : outcome('f'.repeat(32), 'succeeded', true))
    await flushPromises(); await button(wrapper, 'Switch on').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('Outcome unconfirmed')
    expect(wrapper.text()).not.toContain('Confirmed by the device')
    expect(localStorage.getItem(storageKey)).not.toBeNull()
  })
  it('requires declared operations and current resource access', async () => {
    const { wrapper, host } = setup(name => name === 'observe' ? { ...resource, access: 'required', target_device_id: null, provider_id: null } : {})
    host.getInfo.mockResolvedValue({ ...info, operations: [{ operation_id: 'observe' }] })
    await flushPromises()
    expect(button(wrapper, 'Switch on').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).not.toContain(resource.target_device_id)
  })
  it('stops status polling on unmount', async () => {
    const { wrapper, host } = setup(); await flushPromises(); wrapper.unmount(); wrappers = []
    const count = host.invoke.mock.calls.length
    await vi.advanceTimersByTimeAsync(6000)
    expect(host.invoke).toHaveBeenCalledTimes(count)
  })
  it('keeps idle controls usable while a background observation is in flight', async () => {
    const { wrapper, host } = setup(); await flushPromises()
    let resolveObservation: (value: unknown) => void = () => {}
    host.invoke.mockImplementationOnce(() => new Promise(resolve => { resolveObservation = resolve }))
    await vi.advanceTimersByTimeAsync(3000)
    expect(button(wrapper, 'Switch on').attributes('disabled')).toBeUndefined()
    resolveObservation(resource); await flushPromises()
  })
})
